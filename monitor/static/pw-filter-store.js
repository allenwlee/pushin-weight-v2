// Shared, versioned homepage preference state and filter event bus.

(function () {
  'use strict';

  var STORAGE_VERSION = 1;
  var STORAGE_PREFIX = 'pushinweight.home.preferences.v1:';
  var MULTI_VALUE_KEYS = [
    'brands', 'discourse', 'post_types', 'role', 'lang', 'sentiment',
    'cn_nationalism', 'us_nationalism',
  ];
  var FILTER_QUERY_KEYS = MULTI_VALUE_KEYS.concat(['unsanctioned', 'window']);
  var ALLOWED_WINDOWS = [1, 7, 30, 365];
  var body = document.body;
  var storageEnabled = Boolean(
    body && body.hasAttribute('data-pw-preferences-namespace')
  );
  var namespace = storageEnabled
    ? (body.getAttribute('data-pw-preferences-namespace') || 'anonymous')
    : 'anonymous';
  var storageKey = STORAGE_PREFIX + namespace;

  function defaultFilters() {
    return {
      brands: '__all__',
      discourse: '__all__',
      post_types: '__all__',
      role: '__all__',
      lang: '__all__',
      sentiment: '__all__',
      cn_nationalism: '__all__',
      us_nationalism: '__all__',
      unsanctioned: 'off',
      window: 1,
    };
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function readInitialFromBody() {
    var initial = defaultFilters();
    var parsed = {};
    if (!body) return initial;
    var raw = body.getAttribute('data-pw-filters');
    if (raw) {
      try {
        parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          Object.keys(initial).forEach(function (key) {
            if (Object.prototype.hasOwnProperty.call(parsed, key)) initial[key] = parsed[key];
          });
        }
      } catch (error) {
        console.warn('pw-filter-store: invalid data-pw-filters JSON', error);
        parsed = {};
      }
    }
    var bodyWindow = Number(body.getAttribute('data-pw-window'));
    if (!Object.prototype.hasOwnProperty.call(parsed, 'window') && bodyWindow) {
      initial.window = bodyWindow;
    }
    return initial;
  }

  function getFilterPanel() {
    return document.getElementById('control-panel') || document.querySelector('.filter-bar');
  }

  function controlsForGroup(_panel, group) {
    // Filter dropdowns are portaled to body while open.
    return Array.prototype.slice.call(
      document.querySelectorAll('[data-pw-filter-group="' + group + '"]')
    );
  }

  function valueFromControls(panel, group) {
    var inputs = controlsForGroup(panel, group);
    if (!inputs.length) return undefined;
    if (group === 'unsanctioned') {
      return inputs.some(function (input) { return input.checked && input.value === 'only'; })
        ? 'only'
        : 'off';
    }
    var selected = inputs.filter(function (input) { return input.checked; })
      .map(function (input) { return input.value; });
    if (selected.length === inputs.length) return '__all__';
    return selected;
  }

  function hydrateFromControlPanel(initial) {
    var panel = getFilterPanel();
    if (!panel) return initial;
    MULTI_VALUE_KEYS.concat(['unsanctioned']).forEach(function (group) {
      var value = valueFromControls(panel, group);
      if (value !== undefined) initial[group] = value;
    });
    return initial;
  }

  function readStoredPreferences() {
    if (!storageEnabled) return null;
    try {
      var raw = window.localStorage.getItem(storageKey);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || parsed.version !== STORAGE_VERSION || typeof parsed !== 'object') {
        return null;
      }
      return parsed;
    } catch (error) {
      console.warn('pw-filter-store: preferences unavailable', error);
      return null;
    }
  }

  function queryHas(key) {
    try { return new URLSearchParams(window.location.search).has(key); }
    catch (_error) { return false; }
  }

  function explicitFilterKeys() {
    var params;
    try { params = new URLSearchParams(window.location.search); }
    catch (_error) { return []; }
    var raw = params.get('filters');
    if (raw) {
      try {
        var parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return FILTER_QUERY_KEYS.filter(function (key) {
            if (!Object.prototype.hasOwnProperty.call(parsed, key)) return false;
            if (MULTI_VALUE_KEYS.indexOf(key) !== -1) {
              return parsed[key] === '__all__' || Array.isArray(parsed[key]) || typeof parsed[key] === 'string';
            }
            if (key === 'unsanctioned') return ['off', 'only', 'any'].indexOf(parsed[key]) !== -1;
            return ALLOWED_WINDOWS.indexOf(Number(parsed[key])) !== -1;
          });
        }
      } catch (_error) { /* malformed JSON is not a valid override */ }
    }
    return FILTER_QUERY_KEYS.filter(function (key) {
      if (!params.has(key)) return false;
      var value = params.get(key);
      if (MULTI_VALUE_KEYS.indexOf(key) !== -1) return Boolean(value);
      if (key === 'unsanctioned') return ['off', 'only', 'any'].indexOf(value) !== -1;
      return ALLOWED_WINDOWS.indexOf(Number(value)) !== -1;
    });
  }

  function normalizeMultiValue(group, value, fallback) {
    if (value === '__all__') return '__all__';
    if (typeof value === 'string' && value) value = [value];
    if (!Array.isArray(value)) return clone(fallback);
    var allowed = controlsForGroup(getFilterPanel(), group)
      .map(function (input) { return input.value; });
    if (!allowed.length) return clone(value);
    var seen = [];
    value.forEach(function (item) {
      if (allowed.indexOf(item) !== -1 && seen.indexOf(item) === -1) seen.push(item);
    });
    if (value.length && !seen.length) return clone(fallback);
    return seen;
  }

  function normalizeFilters(candidate, fallback) {
    var normalized = clone(fallback);
    MULTI_VALUE_KEYS.forEach(function (group) {
      if (Object.prototype.hasOwnProperty.call(candidate, group)) {
        normalized[group] = normalizeMultiValue(group, candidate[group], fallback[group]);
      }
    });
    if (candidate.unsanctioned === 'only' || candidate.unsanctioned === 'off') {
      normalized.unsanctioned = candidate.unsanctioned;
    }
    var windowDays = Number(candidate.window);
    if (ALLOWED_WINDOWS.indexOf(windowDays) !== -1) normalized.window = windowDays;
    return normalized;
  }

  function defaultLenses() {
    var result = { brands: 'open', nationalism: 'us' };
    document.querySelectorAll('[data-lens-pair]').forEach(function (dropdown) {
      var pair = dropdown.getAttribute('data-lens-pair');
      var lensBody = dropdown.querySelector('.dd-lens-body');
      if (pair === 'open,closed' && lensBody) result.brands = lensBody.getAttribute('data-active-lens') || 'open';
      if (pair === 'us,cn' && lensBody) result.nationalism = lensBody.getAttribute('data-active-lens') || 'us';
    });
    return result;
  }

  function normalizeLenses(raw) {
    var result = defaultLenses();
    if (!raw || typeof raw !== 'object') return result;
    if (raw.brands === 'open' || raw.brands === 'closed') result.brands = raw.brands;
    if (raw.nationalism === 'us' || raw.nationalism === 'cn') result.nationalism = raw.nationalism;
    return result;
  }

  function pulseInventory() {
    return Array.prototype.slice.call(document.querySelectorAll('[data-pw-pulse-entry]'))
      .map(function (button) { return button.getAttribute('data-pw-pulse-entry'); });
  }

  function normalizePulseBrands(raw) {
    if (!Array.isArray(raw)) return [];
    var allowed = pulseInventory();
    return raw.filter(function (nickname, index) {
      return allowed.indexOf(nickname) !== -1 && raw.indexOf(nickname) === index;
    });
  }

  function normalizeLocale(value, fallback) {
    if (['zh_cn', 'zh-CN', 'zh_hans', 'en', 'original'].indexOf(value) !== -1) return value;
    return fallback;
  }

  var serverState = normalizeFilters(readInitialFromBody(), defaultFilters());
  var stored = readStoredPreferences();
  var state = storageEnabled ? clone(serverState) : hydrateFromControlPanel(clone(serverState));
  var urlFilterKeys = explicitFilterKeys();
  if (storageEnabled && stored) {
    state = normalizeFilters(stored.filters || {}, serverState);
    if (ALLOWED_WINDOWS.indexOf(Number(stored.window)) !== -1) {
      state.window = Number(stored.window);
    }
    urlFilterKeys.forEach(function (key) { state[key] = clone(serverState[key]); });
  }
  var pulseBrands = stored ? normalizePulseBrands(stored.pulseBrands) : [];
  if (urlFilterKeys.indexOf('brands') !== -1) pulseBrands = [];
  else if (pulseBrands.length) state.brands = clone(pulseBrands);
  var lenses = normalizeLenses(stored && stored.lens);
  var explicitLocale = queryHas('locale');
  var authoredLocale = normalizeLocale(
    body && body.getAttribute('data-pw-locale'),
    'zh_cn'
  );
  var preferenceLocale = explicitLocale
    ? authoredLocale
    : normalizeLocale(stored && stored.locale, authoredLocale);
  var preferenceTimezone = (stored && stored.timezone) === 'ca' ? 'ca' : 'local';
  var restoredFiltersDiffer = JSON.stringify(state) !== JSON.stringify(serverState);

  function preferencePayload() {
    return {
      version: STORAGE_VERSION,
      locale: preferenceLocale,
      window: Number(state.window),
      timezone: preferenceTimezone,
      lens: clone(lenses),
      filters: clone(state),
      pulseBrands: clone(pulseBrands),
    };
  }

  function persist() {
    if (!storageEnabled) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(preferencePayload()));
    } catch (error) {
      console.warn('pw-filter-store: preferences unavailable', error);
    }
  }

  function updatePulsePressed() {
    document.querySelectorAll('[data-pw-pulse-entry]').forEach(function (button) {
      button.setAttribute(
        'aria-pressed',
        pulseBrands.indexOf(button.getAttribute('data-pw-pulse-entry')) !== -1
          ? 'true'
          : 'false'
      );
    });
  }

  function emitChange(key, save) {
    updatePulsePressed();
    if (save !== false) persist();
    document.dispatchEvent(new CustomEvent('pw:filter-change', {
      detail: { key: key, filters: clone(state) },
    }));
  }

  function syncWindowControls() {
    document.querySelectorAll('[data-pw-window-btn]').forEach(function (button) {
      var active = Number(button.getAttribute('data-pw-window-btn')) === Number(state.window);
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function syncControlPanelGroup(group) {
    if (group === 'window') {
      syncWindowControls();
      return;
    }
    var panel = getFilterPanel();
    if (!panel) return;
    var value = state[group];
    controlsForGroup(panel, group).forEach(function (input) {
      if (group === 'unsanctioned') {
        input.checked = value === 'only' && input.value === 'only';
      } else if (value === '__all__') {
        input.checked = true;
      } else {
        input.checked = Array.isArray(value) && value.indexOf(input.value) !== -1;
      }
    });
    panel.querySelectorAll('[data-pw-filter-only="' + group + '"]').forEach(function (input) {
      input.checked = Array.isArray(value) && value.indexOf(input.value) !== -1;
    });
  }

  function syncLenses() {
    document.querySelectorAll('[data-lens-pair]').forEach(function (dropdown) {
      var pair = dropdown.getAttribute('data-lens-pair');
      var key = pair === 'open,closed' ? 'brands' : pair === 'us,cn' ? 'nationalism' : null;
      if (!key) return;
      var value = lenses[key];
      dropdown.querySelectorAll('.dd-segment [data-lens]').forEach(function (button) {
        var active = button.getAttribute('data-lens') === value;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      var lensBody = dropdown.querySelector('.dd-lens-body');
      if (lensBody) lensBody.setAttribute('data-active-lens', value);
    });
  }

  function setFilter(key, value) {
    if (key === 'window') value = Number(value);
    if (key === 'brands') pulseBrands = [];
    state[key] = clone(value);
    syncControlPanelGroup(key);
    emitChange(key);
  }

  function syncFromControls(group) {
    var panel = getFilterPanel();
    if (!panel) return;
    var value = valueFromControls(panel, group);
    if (value === undefined) return;
    if (group === 'brands') pulseBrands = [];
    state[group] = value;
    emitChange(group);
  }

  function setPreference(key, value) {
    if (key === 'locale' && ['en', 'zh_cn', 'zh_hans', 'zh-CN', 'original'].indexOf(value) !== -1) {
      preferenceLocale = value;
    } else if (key === 'timezone') {
      preferenceTimezone = value === 'ca' ? 'ca' : 'local';
    } else {
      return;
    }
    persist();
  }

  function setLens(key, value) {
    if (key === 'brands' && (value === 'open' || value === 'closed')) lenses.brands = value;
    else if (key === 'nationalism' && (value === 'us' || value === 'cn')) lenses.nationalism = value;
    else return;
    syncLenses();
    persist();
  }

  function wireControlPanel() {
    var panel = getFilterPanel();
    if (panel) {
      MULTI_VALUE_KEYS.concat(['unsanctioned']).forEach(syncControlPanelGroup);
      panel.querySelectorAll('input[type="checkbox"][data-pw-filter-group]').forEach(function (input) {
        input.addEventListener('change', function () {
          syncFromControls(input.getAttribute('data-pw-filter-group'));
        });
      });

      panel.querySelectorAll('[data-pw-filter-only]').forEach(function (onlyInput) {
        onlyInput.addEventListener('change', function () {
          var group = onlyInput.getAttribute('data-pw-filter-only');
          var onlyInputs = Array.prototype.slice.call(
            panel.querySelectorAll('[data-pw-filter-only="' + group + '"]')
          );
          var includes = controlsForGroup(panel, group);
          var selected = onlyInputs.filter(function (input) { return input.checked; })
            .map(function (input) { return input.value; });
          if (!selected.length) {
            includes.forEach(function (input) { input.checked = true; });
          } else {
            includes.forEach(function (input) {
              input.checked = selected.indexOf(input.value) !== -1;
            });
          }
          syncFromControls(group);
        });
      });
    }

    document.querySelectorAll('[data-pw-window-btn]').forEach(function (button) {
      button.addEventListener('click', function () {
        setFilter('window', Number(button.getAttribute('data-pw-window-btn')));
      });
    });

    document.addEventListener('click', function (event) {
      var button = event.target && event.target.closest
        ? event.target.closest('button[data-pw-pulse-entry]')
        : null;
      if (!button) return;
      var nickname = button.getAttribute('data-pw-pulse-entry');
      var selectedIndex = pulseBrands.indexOf(nickname);
      if (selectedIndex === -1) pulseBrands.push(nickname);
      else pulseBrands.splice(selectedIndex, 1);
      state.brands = pulseBrands.length ? clone(pulseBrands) : '__all__';
      syncControlPanelGroup('brands');
      emitChange('brands');
    });

    syncWindowControls();
    syncLenses();
    updatePulsePressed();
    if (restoredFiltersDiffer) {
      window.setTimeout(function () { emitChange('restore', false); }, 0);
    }
  }

  window.pwFilter = {
    get: function () { return clone(state); },
    getPulseBrands: function () { return clone(pulseBrands); },
    getPreferences: function () { return preferencePayload(); },
    getPreference: function (key) { return preferencePayload()[key]; },
    set: setFilter,
    setPreference: setPreference,
    setLens: setLens,
    syncFromControls: syncFromControls,
    on: function (event, handler) {
      document.addEventListener(event, function (nativeEvent) {
        try { handler(nativeEvent); }
        catch (error) { console.warn('pw filter handler', error); }
      });
    },
    state: state,
    storageKey: storageEnabled ? storageKey : null,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireControlPanel);
  } else {
    wireControlPanel();
  }
})();
