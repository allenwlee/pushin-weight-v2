// Shared filter state and event bus for public and legacy home controls.

(function () {
  'use strict';

  var MULTI_VALUE_KEYS = [
    'brands', 'discourse', 'post_types', 'role', 'lang', 'sentiment',
    'cn_nationalism', 'us_nationalism',
  ];

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
    var body = document.body;
    if (!body) return initial;
    var raw = body.getAttribute('data-pw-filters');
    if (raw) {
      try {
        var parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          Object.keys(initial).forEach(function (key) {
            if (Object.prototype.hasOwnProperty.call(parsed, key)) initial[key] = parsed[key];
          });
        }
      } catch (error) {
        console.warn('pw-filter-store: invalid data-pw-filters JSON', error);
      }
    }
    var bodyWindow = Number(body.getAttribute('data-pw-window'));
    if (!Object.prototype.hasOwnProperty.call((parsed || {}), 'window') && bodyWindow) {
      initial.window = bodyWindow;
    }
    return initial;
  }

  function getFilterPanel() {
    return document.getElementById('control-panel') || document.querySelector('.filter-bar');
  }

  function controlsForGroup(panel, group) {
    // Filter dropdowns are portaled to body while open, so the active
    // controls may no longer be descendants of the filter bar.
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

  function hydrateFromControlPanel(state) {
    var panel = getFilterPanel();
    if (!panel) return state;
    MULTI_VALUE_KEYS.concat(['unsanctioned']).forEach(function (group) {
      var value = valueFromControls(panel, group);
      if (value !== undefined) state[group] = value;
    });
    return state;
  }

  var state = hydrateFromControlPanel(readInitialFromBody());
  var pulseBrands = [];

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

  function emitChange(key) {
    updatePulsePressed();
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
    var inputs = controlsForGroup(panel, group);
    inputs.forEach(function (input) {
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

  function wireControlPanel() {
    var panel = getFilterPanel();
    if (panel) {
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
    updatePulsePressed();
  }

  window.pwFilter = {
    get: function () { return clone(state); },
    getPulseBrands: function () { return clone(pulseBrands); },
    set: setFilter,
    syncFromControls: syncFromControls,
    on: function (event, handler) {
      document.addEventListener(event, function (nativeEvent) {
        try { handler(nativeEvent); }
        catch (error) { console.warn('pw filter handler', error); }
      });
    },
    state: state,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireControlPanel);
  } else {
    wireControlPanel();
  }
})();
