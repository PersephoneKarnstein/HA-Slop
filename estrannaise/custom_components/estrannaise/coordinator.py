"""DataUpdateCoordinator for Estrannaise HRT Monitor."""

from __future__ import annotations

import logging
import math
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    AVAILABLE_UNITS,
    CONF_AUTO_REGIMEN,
    CONF_DOSE_MG,
    CONF_DOSE_TIME,
    CONF_ENABLE_CALENDAR,
    CONF_ESTER,
    CONF_INTERVAL_DAYS,
    CONF_METHOD,
    CONF_MODE,
    CONF_PHASE_DAYS,
    CONF_TARGET_TYPE,
    CONF_UNITS,
    DEFAULT_AUTO_REGIMEN,
    DEFAULT_DOSE_MG,
    DEFAULT_DOSE_TIME,
    DEFAULT_ENABLE_CALENDAR,
    DEFAULT_ESTER,
    DEFAULT_INTERVAL_DAYS,
    DEFAULT_METHOD,
    DEFAULT_MODE,
    DEFAULT_PHASE_DAYS,
    DEFAULT_TARGET_TYPE,
    DEFAULT_UNITS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_AUTOMATIC,
    MODE_BOTH,
    PK_PARAMETERS,
    compute_e2_at_time,
    compute_suggested_regimen,
    resolve_model_key,
)
from .database import EstrannaisDatabase

_LOGGER = logging.getLogger(__name__)


class EstrannaisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage estrannaise data from SQLite."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        database: EstrannaisDatabase,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )
        self.config_entry = entry
        self.database = database

    def _get_config(self) -> dict[str, Any]:
        """Get merged config from entry data + options."""
        data = self.config_entry.data
        opts = self.config_entry.options
        return {
            "ester": opts.get(CONF_ESTER, data.get(CONF_ESTER, DEFAULT_ESTER)),
            "method": opts.get(CONF_METHOD, data.get(CONF_METHOD, DEFAULT_METHOD)),
            "dose_mg": opts.get(CONF_DOSE_MG, data.get(CONF_DOSE_MG, DEFAULT_DOSE_MG)),
            "interval_days": opts.get(
                CONF_INTERVAL_DAYS,
                data.get(CONF_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS),
            ),
            "mode": opts.get(CONF_MODE, data.get(CONF_MODE, DEFAULT_MODE)),
            "units": opts.get(CONF_UNITS, data.get(CONF_UNITS, DEFAULT_UNITS)),
            "enable_calendar": opts.get(
                CONF_ENABLE_CALENDAR,
                data.get(CONF_ENABLE_CALENDAR, DEFAULT_ENABLE_CALENDAR),
            ),
            "dose_time": opts.get(
                CONF_DOSE_TIME,
                data.get(CONF_DOSE_TIME, DEFAULT_DOSE_TIME),
            ),
            "auto_regimen": opts.get(
                CONF_AUTO_REGIMEN,
                data.get(CONF_AUTO_REGIMEN, DEFAULT_AUTO_REGIMEN),
            ),
            "target_type": opts.get(
                CONF_TARGET_TYPE,
                data.get(CONF_TARGET_TYPE, DEFAULT_TARGET_TYPE),
            ),
            "phase_days": opts.get(
                CONF_PHASE_DAYS,
                data.get(CONF_PHASE_DAYS, DEFAULT_PHASE_DAYS),
            ),
        }

    def _get_all_entry_configs(self) -> list[dict[str, Any]]:
        """Get configs from all estrannaise entries."""
        configs = []
        domain_data = self.hass.data.get(DOMAIN, {})
        for key, val in domain_data.items():
            if isinstance(val, EstrannaisCoordinator):
                cfg = val._get_config()
                cfg["entry_id"] = val.config_entry.entry_id
                configs.append(cfg)
        return configs

    @staticmethod
    def _generate_auto_doses_for_config(
        config: dict[str, Any], now: float, lookback_days: float = 90.0
    ) -> list[dict[str, Any]]:
        """Generate synthetic dose records for a config's recurring schedule."""
        from datetime import datetime, timezone

        mode = config["mode"]
        if mode not in (MODE_AUTOMATIC, MODE_BOTH):
            return []

        ester = config["ester"]
        method = config["method"]
        dose_mg = config["dose_mg"]
        interval_days = config["interval_days"]

        # Align to time-of-day
        dose_time = config.get("dose_time", "08:00")
        try:
            parts = dose_time.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            hour, minute = 8, 0

        # If auto_regimen is enabled, use suggested regimen values
        cycle_fit = None
        if config.get("auto_regimen", False):
            target_type = config.get("target_type", "target_range")
            suggested = compute_suggested_regimen(ester, method, target_type)
            if suggested:
                if "schedules" in suggested:
                    cycle_fit = suggested
                else:
                    dose_mg = suggested["dose_mg"]
                    interval_days = suggested["interval_days"]

        doses: list[dict[str, Any]] = []
        future_limit = now + lookback_days * 86400.0

        if cycle_fit:
            # Multi-schedule cycle fit: generate future doses per schedule
            epoch_day_now = int(now // 86400)
            cycle_day_now = epoch_day_now % 28
            tod_sec = hour * 3600 + minute * 60

            for sch in cycle_fit["schedules"]:
                sch_dose = sch["dose_mg"]
                sch_interval = sch["interval_days"]
                sch_phase = int(sch["phase_days"])
                sch_model = sch["model_key"]
                sch_interval_sec = sch_interval * 86400.0

                # Anchor to most recent cycle day matching the phase
                days_back = (cycle_day_now - sch_phase) % 28
                anchor_day = epoch_day_now - days_back
                anchor_ts = anchor_day * 86400.0 + tod_sec

                # Step forward to next future dose
                t = anchor_ts
                while t <= now:
                    t += sch_interval_sec

                while t <= future_limit:
                    doses.append(
                        {
                            "id": None,
                            "timestamp": t,
                            "model": sch_model,
                            "dose_mg": sch_dose,
                            "source": "automatic",
                        }
                    )
                    t += sch_interval_sec
        else:
            # Single schedule
            interval_sec = interval_days * 86400.0
            model_key = resolve_model_key(ester, method, interval_days)
            if not model_key:
                return []

            phase_days = config.get("phase_days", 0.0)
            tod_sec = hour * 3600 + minute * 60

            if phase_days and phase_days > 0:
                # Phase-based anchoring (from cycle fit discrete entry)
                epoch_day_now = int(now // 86400)
                cycle_day_now = epoch_day_now % 28
                days_back = (cycle_day_now - int(phase_days)) % 28
                anchor_day = epoch_day_now - days_back
                anchor_ts = anchor_day * 86400.0 + tod_sec

                t = anchor_ts
                while t <= now:
                    t += interval_sec
                while t <= future_limit:
                    doses.append(
                        {
                            "id": None,
                            "timestamp": t,
                            "model": model_key,
                            "dose_mg": dose_mg,
                            "source": "automatic",
                        }
                    )
                    t += interval_sec
            else:
                # Standard anchoring (today's dose time)
                now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
                today_dose = now_dt.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if today_dose > now_dt:
                    anchor = today_dose.timestamp() - interval_sec
                else:
                    anchor = today_dose.timestamp()

                t = anchor + interval_sec
                while t <= future_limit:
                    doses.append(
                        {
                            "id": None,
                            "timestamp": t,
                            "model": model_key,
                            "dose_mg": dose_mg,
                            "source": "automatic",
                        }
                    )
                    t += interval_sec

        return doses

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from SQLite and compute current state."""
        entry_id = self.config_entry.entry_id
        config = self._get_config()
        now = time.time()

        # Prune old doses for this entry
        await self.database.prune_stale_doses(entry_id)

        # Get ALL manual doses from database (cross-entry)
        all_manual_doses = await self.database.get_all_doses()

        # Generate automatic recurring doses for ALL entries
        all_configs = self._get_all_entry_configs()
        all_auto_doses: list[dict[str, Any]] = []
        for cfg in all_configs:
            all_auto_doses.extend(
                self._generate_auto_doses_for_config(cfg, now)
            )

        # Combine all doses for PK computation
        combined_doses = all_manual_doses + all_auto_doses

        # Get ALL blood tests (cross-entry)
        all_blood_tests = await self.database.get_all_blood_tests()

        # Compute scaling factor and variance
        scaling_factor, scaling_variance = await self.database.compute_scaling_factor(
            entry_id, combined_doses
        )

        # Compute current E2 level
        units = config["units"]
        cf = AVAILABLE_UNITS.get(units, {}).get("conversion_factor", 1.0)
        current_e2 = compute_e2_at_time(now, combined_doses, scaling_factor) * cf

        # Compute suggested regimen if auto_regimen is enabled
        suggested_regimen = None
        cycle_fit_regimen = None
        if config.get("auto_regimen", False):
            suggested_regimen = compute_suggested_regimen(
                config["ester"],
                config["method"],
                config.get("target_type", "target_range"),
            )
            # When target is menstrual_range, suggested_regimen IS the cycle fit
            if suggested_regimen and "schedules" in suggested_regimen:
                cycle_fit_regimen = suggested_regimen

        # Blood test baseline (zero-state handling)
        # When predicted E2 is 0 at all test times, multiplicative scaling
        # cannot work. Use the most recent blood test as a baseline anchor
        # that decays forward using the slowest elimination constant.
        baseline_e2 = 0.0
        baseline_test_ts = 0.0
        if (
            all_blood_tests
            and scaling_factor == 1.0
            and scaling_variance == 0.0
        ):
            all_zero = all(
                compute_e2_at_time(bt["timestamp"], combined_doses) <= 0
                for bt in all_blood_tests
            )
            if all_zero:
                latest = max(all_blood_tests, key=lambda t: t["timestamp"])
                test_level = latest["level_pg_ml"]
                age_days = (now - latest["timestamp"]) / 86400.0
                baseline_test_ts = latest["timestamp"]
                model_key = resolve_model_key(
                    config["ester"],
                    config["method"],
                    config["interval_days"],
                )
                if model_key and age_days >= 0:
                    params = PK_PARAMETERS.get(model_key)
                    if params:
                        k3 = params[3]
                        baseline_e2 = test_level * math.exp(-k3 * age_days)

        # Include baseline in displayed E2 value
        if baseline_e2 > 0:
            current_e2 += baseline_e2 * cf

        return {
            "doses": all_manual_doses,
            "auto_doses": all_auto_doses,
            "blood_tests": all_blood_tests,
            "scaling_factor": scaling_factor,
            "scaling_variance": scaling_variance,
            "current_e2": round(current_e2, 1),
            "config": config,
            "all_configs": all_configs,
            "suggested_regimen": suggested_regimen,
            "cycle_fit_regimen": cycle_fit_regimen,
            "baseline_e2": round(baseline_e2, 2),
            "baseline_test_ts": baseline_test_ts,
        }
