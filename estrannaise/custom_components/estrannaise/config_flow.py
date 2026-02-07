"""Config flow for Estrannaise HRT Monitor."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_AUTO_REGIMEN,
    CONF_BACKFILL_DOSES,
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
    DEFAULT_BACKFILL_DOSES,
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
    DOMAIN,
    ESTERS,
    METHODS,
    MODE_AUTOMATIC,
    MODE_BOTH,
    MODE_MANUAL,
    compute_suggested_regimen,
    get_dose_units,
    is_combination_supported,
)


class EstrannaisConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Estrannaise."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._schedules: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1: Ester selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_method()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ESTER, default=DEFAULT_ESTER): vol.In(
                        ESTERS
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_method(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2: Method selection (filtered by chosen ester)."""
        errors: dict[str, str] = {}
        ester = self._data.get(CONF_ESTER, DEFAULT_ESTER)

        if user_input is not None:
            method = user_input.get(CONF_METHOD, DEFAULT_METHOD)

            if not is_combination_supported(ester, method):
                from .const import ESTER_METHOD_TO_MODEL
                if (ester, method) in ESTER_METHOD_TO_MODEL:
                    errors["base"] = "not_yet_supported"
                else:
                    errors["base"] = "invalid_combination"
            else:
                self._data.update(user_input)
                return await self.async_step_setup_mode()

        # Only show methods that are valid for the selected ester
        available_methods = {
            k: v for k, v in METHODS.items()
            if is_combination_supported(ester, k)
        }
        default_method = (
            DEFAULT_METHOD if DEFAULT_METHOD in available_methods
            else next(iter(available_methods))
        )

        return self.async_show_form(
            step_id="method",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_METHOD, default=default_method
                    ): vol.In(available_methods),
                }
            ),
            errors=errors,
        )

    async def async_step_setup_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2: Auto-generate or manual regimen setup."""
        if user_input is not None:
            setup_mode = user_input.get("setup_mode", "auto")
            if setup_mode == "auto":
                return await self.async_step_auto_target()
            else:
                self._data[CONF_AUTO_REGIMEN] = False
                return await self.async_step_regimen()

        return self.async_show_form(
            step_id="setup_mode",
            data_schema=vol.Schema(
                {
                    vol.Required("setup_mode", default="manual"): vol.In(
                        {
                            "manual": "Manual setup (recommended)",
                            "auto": "Auto-generate",
                        }
                    ),
                }
            ),
        )

    async def async_step_auto_target(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2a (auto path): Choose target range."""
        errors: dict[str, str] = {}

        if user_input is not None:
            target_type = user_input.get(CONF_TARGET_TYPE, DEFAULT_TARGET_TYPE)
            self._data[CONF_TARGET_TYPE] = target_type
            self._data[CONF_DOSE_TIME] = DEFAULT_DOSE_TIME

            ester = self._data.get(CONF_ESTER, DEFAULT_ESTER)
            method = self._data.get(CONF_METHOD, DEFAULT_METHOD)

            # Compute the regimen at config flow time
            suggested = compute_suggested_regimen(ester, method, target_type)

            if suggested and "schedules" in suggested:
                # Multi-schedule cycle fit → discrete entries
                self._schedules = suggested["schedules"]
                return await self.async_step_confirm_schedules()
            elif suggested:
                # Single schedule (target_range) → one concrete entry
                self._schedules = [{
                    "dose_mg": suggested["dose_mg"],
                    "interval_days": suggested["interval_days"],
                    "phase_days": 0.0,
                    "model_key": suggested.get("model_key", ""),
                }]
                return await self.async_step_settings()
            else:
                errors["base"] = "invalid_combination"

        return self.async_show_form(
            step_id="auto_target",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TARGET_TYPE, default=DEFAULT_TARGET_TYPE
                    ): vol.In(
                        {
                            "target_range": "Target range (trough ~200 pg/mL)",
                            "menstrual_range": "Menstrual range (avg ~100 pg/mL)",
                        }
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_confirm_schedules(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2b (auto path): Confirm computed schedules."""
        if user_input is not None:
            return await self.async_step_settings()

        ester = self._data.get(CONF_ESTER, DEFAULT_ESTER)
        ester_name = ESTERS.get(ester, "HRT")
        method = self._data.get(CONF_METHOD, DEFAULT_METHOD)
        method_name = METHODS.get(method, "")

        lines = []
        for i, sch in enumerate(self._schedules, 1):
            lines.append(
                f"{i}. {sch['dose_mg']}mg every {sch['interval_days']}d "
                f"(cycle day {int(sch['phase_days'])})"
            )

        return self.async_show_form(
            step_id="confirm_schedules",
            data_schema=vol.Schema({}),
            description_placeholders={
                "ester": ester_name,
                "method": method_name,
                "schedules": ", ".join(lines),
                "count": str(len(self._schedules)),
            },
        )

    async def async_step_regimen(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2b (manual path): Dose, interval, and tracking mode."""
        if user_input is not None:
            self._data.update(user_input)
            self._data[CONF_TARGET_TYPE] = DEFAULT_TARGET_TYPE
            return await self.async_step_settings()

        method = self._data.get(CONF_METHOD, DEFAULT_METHOD)
        dose_unit = get_dose_units(method)

        return self.async_show_form(
            step_id="regimen",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DOSE_MG, default=DEFAULT_DOSE_MG
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.01, max=500)),
                    vol.Required(
                        CONF_INTERVAL_DAYS, default=DEFAULT_INTERVAL_DAYS
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=90)),
                    vol.Required(CONF_MODE, default=DEFAULT_MODE): vol.In(
                        {
                            MODE_MANUAL: "Manual (log each dose)",
                            MODE_AUTOMATIC: "Automatic (recurring schedule)",
                            MODE_BOTH: "Both (recurring + manual extras)",
                        }
                    ),
                    vol.Required(
                        CONF_DOSE_TIME, default=DEFAULT_DOSE_TIME
                    ): str,
                    vol.Optional(
                        CONF_PHASE_DAYS, default=DEFAULT_PHASE_DAYS
                    ): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=27)
                    ),
                }
            ),
            description_placeholders={"dose_unit": dose_unit},
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 3: Units and calendar integration."""
        if user_input is not None:
            self._data.update(user_input)
            ester = self._data.get(CONF_ESTER, DEFAULT_ESTER)
            ester_name = ESTERS.get(ester, "HRT")
            method = self._data.get(CONF_METHOD, DEFAULT_METHOD)
            method_name = METHODS.get(method, "")
            units = user_input.get(CONF_UNITS, DEFAULT_UNITS)
            enable_cal = user_input.get(
                CONF_ENABLE_CALENDAR, DEFAULT_ENABLE_CALENDAR
            )

            if self._schedules:
                # Auto-generated: create discrete entries per schedule
                first = self._schedules[0]
                backfill = self._data.get(
                    CONF_BACKFILL_DOSES, DEFAULT_BACKFILL_DOSES
                )
                first_data = {
                    CONF_ESTER: ester,
                    CONF_METHOD: method,
                    CONF_DOSE_MG: first["dose_mg"],
                    CONF_INTERVAL_DAYS: first["interval_days"],
                    CONF_PHASE_DAYS: first["phase_days"],
                    CONF_MODE: MODE_AUTOMATIC,
                    CONF_DOSE_TIME: self._data.get(
                        CONF_DOSE_TIME, DEFAULT_DOSE_TIME
                    ),
                    CONF_AUTO_REGIMEN: False,
                    CONF_TARGET_TYPE: self._data.get(
                        CONF_TARGET_TYPE, DEFAULT_TARGET_TYPE
                    ),
                    CONF_UNITS: units,
                    CONF_ENABLE_CALENDAR: enable_cal,
                    CONF_BACKFILL_DOSES: backfill,
                }
                title = (
                    f"{ester_name} {first['dose_mg']}mg"
                    f"/{first['interval_days']}d ({method_name})"
                )

                # Spawn import flows for remaining schedules
                for sch in self._schedules[1:]:
                    import_data = {
                        CONF_ESTER: ester,
                        CONF_METHOD: method,
                        CONF_DOSE_MG: sch["dose_mg"],
                        CONF_INTERVAL_DAYS: sch["interval_days"],
                        CONF_PHASE_DAYS: sch["phase_days"],
                        CONF_MODE: MODE_AUTOMATIC,
                        CONF_DOSE_TIME: self._data.get(
                            CONF_DOSE_TIME, DEFAULT_DOSE_TIME
                        ),
                        CONF_AUTO_REGIMEN: False,
                        CONF_TARGET_TYPE: self._data.get(
                            CONF_TARGET_TYPE, DEFAULT_TARGET_TYPE
                        ),
                        CONF_UNITS: units,
                        CONF_ENABLE_CALENDAR: enable_cal,
                        CONF_BACKFILL_DOSES: backfill,
                        "subsidiary": True,
                    }
                    self.hass.async_create_task(
                        self.hass.config_entries.flow.async_init(
                            DOMAIN,
                            context={
                                "source": config_entries.SOURCE_IMPORT,
                            },
                            data=import_data,
                        )
                    )

                return self.async_create_entry(title=title, data=first_data)

            # Manual path: single entry
            dose = self._data.get(CONF_DOSE_MG, DEFAULT_DOSE_MG)
            interval = self._data.get(
                CONF_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS
            )
            title = f"{ester_name} {dose}mg/{interval}d ({method_name})"
            return self.async_create_entry(title=title, data=self._data)

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UNITS, default=DEFAULT_UNITS): vol.In(
                        {"pg/mL": "pg/mL", "pmol/L": "pmol/L"}
                    ),
                    vol.Required(
                        CONF_ENABLE_CALENDAR, default=DEFAULT_ENABLE_CALENDAR
                    ): bool,
                    vol.Required(
                        CONF_BACKFILL_DOSES, default=DEFAULT_BACKFILL_DOSES
                    ): bool,
                }
            ),
        )

    async def async_step_import(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle import of additional auto-generated schedules."""
        if user_input is None:
            return self.async_abort(reason="unknown")

        ester_name = ESTERS.get(
            user_input.get(CONF_ESTER, DEFAULT_ESTER), "HRT"
        )
        method_name = METHODS.get(
            user_input.get(CONF_METHOD, DEFAULT_METHOD), ""
        )
        dose = user_input.get(CONF_DOSE_MG, DEFAULT_DOSE_MG)
        interval = user_input.get(CONF_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS)
        title = f"{ester_name} {dose}mg/{interval}d ({method_name})"

        return self.async_create_entry(title=title, data=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EstrannaisOptionsFlow:
        """Get the options flow handler."""
        return EstrannaisOptionsFlow()


class EstrannaisOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Estrannaise."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage integration options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ester = user_input.get(CONF_ESTER, DEFAULT_ESTER)
            method = user_input.get(CONF_METHOD, DEFAULT_METHOD)

            if not is_combination_supported(ester, method):
                from .const import ESTER_METHOD_TO_MODEL
                if method == "oral" and ester != "E":
                    errors["base"] = "oral_estradiol_only"
                elif (ester, method) in ESTER_METHOD_TO_MODEL:
                    errors["base"] = "not_yet_supported"
                else:
                    errors["base"] = "invalid_combination"
            else:
                # Auto-update entry title from new settings
                ester_name = ESTERS.get(
                    user_input.get(CONF_ESTER, DEFAULT_ESTER), "HRT"
                )
                method_name = METHODS.get(
                    user_input.get(CONF_METHOD, DEFAULT_METHOD), ""
                )
                dose = user_input.get(CONF_DOSE_MG, DEFAULT_DOSE_MG)
                interval = user_input.get(
                    CONF_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS
                )
                title = f"{ester_name} {dose}mg/{interval}d ({method_name})"
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=title
                )
                return self.async_create_entry(data=user_input)

        # Merge options over data so saved changes are reflected
        data = {**self.config_entry.data, **self.config_entry.options}

        method = data.get(CONF_METHOD, DEFAULT_METHOD)
        dose_unit = get_dose_units(method)

        # Only show methods valid for the current ester
        current_ester = data.get(CONF_ESTER, DEFAULT_ESTER)
        available_methods = {
            k: v for k, v in METHODS.items()
            if is_combination_supported(current_ester, k)
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ESTER,
                        default=data.get(CONF_ESTER, DEFAULT_ESTER),
                    ): vol.In(ESTERS),
                    vol.Required(
                        CONF_METHOD,
                        default=data.get(CONF_METHOD, DEFAULT_METHOD),
                    ): vol.In(available_methods),
                    vol.Required(
                        CONF_DOSE_MG,
                        default=data.get(CONF_DOSE_MG, DEFAULT_DOSE_MG),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.01, max=500)),
                    vol.Required(
                        CONF_INTERVAL_DAYS,
                        default=data.get(CONF_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=90)),
                    vol.Required(
                        CONF_MODE,
                        default=data.get(CONF_MODE, DEFAULT_MODE),
                    ): vol.In(
                        {
                            MODE_MANUAL: "Manual (log each dose)",
                            MODE_AUTOMATIC: "Automatic (recurring schedule)",
                            MODE_BOTH: "Both (recurring + manual extras)",
                        }
                    ),
                    vol.Required(
                        CONF_DOSE_TIME,
                        default=data.get(CONF_DOSE_TIME, DEFAULT_DOSE_TIME),
                    ): str,
                    vol.Optional(
                        CONF_PHASE_DAYS,
                        default=data.get(CONF_PHASE_DAYS, DEFAULT_PHASE_DAYS),
                    ): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=27)
                    ),
                    vol.Required(
                        CONF_UNITS,
                        default=data.get(CONF_UNITS, DEFAULT_UNITS),
                    ): vol.In({"pg/mL": "pg/mL", "pmol/L": "pmol/L"}),
                    vol.Required(
                        CONF_ENABLE_CALENDAR,
                        default=data.get(CONF_ENABLE_CALENDAR, DEFAULT_ENABLE_CALENDAR),
                    ): bool,
                    vol.Required(
                        CONF_BACKFILL_DOSES,
                        default=data.get(CONF_BACKFILL_DOSES, DEFAULT_BACKFILL_DOSES),
                    ): bool,
                }
            ),
            description_placeholders={"dose_unit": dose_unit},
            errors=errors,
        )
