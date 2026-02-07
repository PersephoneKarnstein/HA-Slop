/**
 * Estrannaise HRT Monitor - Dose Logging Button Card
 *
 * A simple button that logs a dose when clicked via the estrannaise.log_dose service.
 */

const DOSE_BUTTON_VERSION = '1.1.0';

if (!customElements.get('estrannaise-dose-button')) {

  class EstrannaiseDoseButton extends HTMLElement {

    static getConfigElement() {
      return document.createElement('estrannaise-dose-button-editor');
    }

    static getStubConfig() {
      return { entity: '', label: 'Log Dose', icon: 'mdi:needle' };
    }

    setConfig(config) {
      if (!config.entity) throw new Error('Please define an entity');
      this.config = {
        label: 'Log Dose',
        icon: 'mdi:needle',
        confirm: true,
        ...config,
      };
    }

    set hass(hass) {
      this._hass = hass;
      if (!this.shadowRoot) this._buildShadow();
      this._updateState();
    }

    _buildShadow() {
      this.attachShadow({ mode: 'open' });

      const style = document.createElement('style');
      style.textContent = `
        :host { display: block; }
        .card {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,0.1));
          padding: 16px;
          text-align: center;
          cursor: pointer;
          transition: transform 0.1s, box-shadow 0.15s;
          user-select: none;
        }
        .card:hover {
          box-shadow: var(--ha-card-box-shadow, 0 4px 12px rgba(0,0,0,0.15));
        }
        .card:active {
          transform: scale(0.97);
        }
        .card.disabled {
          opacity: 0.4;
          pointer-events: none;
        }
        .card.confirmed {
          background: var(--success-color, #4CAF50);
          color: white;
        }
        ha-icon {
          --mdc-icon-size: 36px;
          color: var(--primary-color);
          display: block;
          margin: 0 auto 8px;
        }
        .card.confirmed ha-icon { color: white; }
        .label {
          font-size: 16px;
          font-weight: 500;
          color: var(--primary-text-color, #212121);
        }
        .card.confirmed .label { color: white; }
        .info {
          font-size: 12px;
          color: var(--secondary-text-color, #757575);
          margin-top: 4px;
        }
        .card.confirmed .info { color: rgba(255,255,255,0.8); }
      `;

      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <ha-icon icon="${this.config.icon}"></ha-icon>
        <div class="label">${this._escapeHtml(this.config.label)}</div>
        <div class="info"></div>
      `;
      card.addEventListener('click', () => this._handleClick());

      this.shadowRoot.appendChild(style);
      this.shadowRoot.appendChild(card);
    }

    _updateState() {
      if (!this._hass || !this.shadowRoot) return;
      const entity = this._hass.states[this.config.entity];
      if (!entity) return;

      const attrs = entity.attributes || {};
      const mode = attrs.mode || 'manual';
      const card = this.shadowRoot.querySelector('.card');
      const info = this.shadowRoot.querySelector('.info');

      // Disable if mode is automatic-only
      if (mode === 'automatic' && !this.config.force_enable) {
        card.classList.add('disabled');
        if (info) info.textContent = 'Automatic dosing enabled';
      } else {
        card.classList.remove('disabled');
        // Card config dose_mg overrides entity attrs
        const doseMg = this.config.dose_mg || attrs.dose_mg || '';
        const model = this.config.model || attrs.model || '';
        // Show friendly ester name if available
        const esters = attrs.esters || {};
        let displayModel = model;
        if (model) {
          const modelParts = model.split(' ');
          const esterName = esters[modelParts[0]];
          if (esterName) displayModel = esterName;
        }
        if (info) info.textContent = doseMg && displayModel ? `${doseMg}mg ${displayModel}` : '';
      }
    }

    async _handleClick() {
      if (!this._hass || this._busy) return;
      const entity = this._hass.states[this.config.entity];
      if (!entity) return;

      const attrs = entity.attributes || {};
      const model = this.config.model || attrs.model || 'EEn im';
      const doseMg = this.config.dose_mg || attrs.dose_mg || 4;

      // Disable button while service call is in-flight
      this._busy = true;
      const card = this.shadowRoot.querySelector('.card');
      card.classList.add('disabled');

      try {
        await this._hass.callService('estrannaise', 'log_dose', {
          entity_id: this.config.entity,
          model: model,
          dose_mg: doseMg,
        });

        // Visual confirmation
        card.classList.remove('disabled');
        const label = this.shadowRoot.querySelector('.label');
        const prevLabel = label.textContent;
        card.classList.add('confirmed');
        label.textContent = 'Dose logged!';

        setTimeout(() => {
          card.classList.remove('confirmed');
          label.textContent = prevLabel;
          this._busy = false;
        }, 2000);
      } catch (err) {
        console.error('Failed to log dose:', err);
        card.classList.remove('disabled');
        const label = this.shadowRoot.querySelector('.label');
        const prevLabel = label.textContent;
        label.textContent = 'Error!';
        setTimeout(() => {
          label.textContent = prevLabel;
          this._busy = false;
        }, 2000);
      }
    }

    _escapeHtml(text) {
      const el = document.createElement('span');
      el.textContent = text;
      return el.innerHTML;
    }

    getCardSize() {
      return 2;
    }
  }

  customElements.define('estrannaise-dose-button', EstrannaiseDoseButton);
}

// ── Editor ──────────────────────────────────────────────────────────────────

if (!customElements.get('estrannaise-dose-button-editor')) {

  class EstrannaiseDoseButtonEditor extends HTMLElement {

    setConfig(config) {
      this.config = { ...config };
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this._form) this._form.hass = hass;
    }

    _render() {
      if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
      this.shadowRoot.innerHTML = '';

      const form = document.createElement('ha-form');
      form.hass = this._hass;
      form.schema = [
        { name: 'entity', selector: { entity: { domain: 'sensor' } } },
        { name: 'dose_mg', label: 'Dose amount (mg)', selector: { number: { min: 0.1, max: 100, step: 0.5, mode: 'box' } } },
        { name: 'label', label: 'Button label', selector: { text: {} } },
        { name: 'icon', label: 'Icon', selector: { icon: {} } },
      ];
      form.data = {
        entity: this.config.entity || '',
        dose_mg: this.config.dose_mg || '',
        label: this.config.label || 'Log Dose',
        icon: this.config.icon || 'mdi:needle',
      };
      form.computeLabel = (schema) => {
        const labels = {
          entity: 'Entity',
          dose_mg: 'Dose amount (mg)',
          label: 'Button label',
          icon: 'Icon',
        };
        return labels[schema.name] || schema.name;
      };
      form.addEventListener('value-changed', (ev) => {
        const newData = ev.detail.value;
        this.config = { ...this.config, ...newData };
        // Remove empty dose_mg so it falls back to entity default
        if (!this.config.dose_mg) delete this.config.dose_mg;
        const event = new Event('config-changed', { bubbles: true, composed: true });
        event.detail = { config: this.config };
        this.dispatchEvent(event);
      });

      this._form = form;
      this.shadowRoot.appendChild(form);
    }
  }

  customElements.define('estrannaise-dose-button-editor', EstrannaiseDoseButtonEditor);
}

// ── Register ────────────────────────────────────────────────────────────────

if (!window.customCards) window.customCards = [];
if (!window.customCards.some(c => c.type === 'estrannaise-dose-button')) {
  window.customCards.push({
    type: 'estrannaise-dose-button',
    name: 'Estrannaise Dose Button',
    description: 'Button to log an estrogen dose',
  });
}
