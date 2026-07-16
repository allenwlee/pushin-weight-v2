// {{AGENT_ATTRIBUTION}}
// x_monitor/static/pw-filter-store.js
// Pushin' Weight (走个量) home-page filter store (U7 of
// feat/pushin-weight-home-pages, 2026-07-06).
//
// Vanilla-JS state store + `pw:filter-change` event bus (KTD3, KTD10).
// - On boot, reads the initial filter state from the `data-pw-filters`
//   JSON attribute on <body>.
// - Exposes `window.pwFilter.get()`, `set(filterKey, value)`, `on(event, handler)`.
// - Emits `pw:filter-change` on `document` whenever a toggle changes.
//   Detail includes the changed key + new value.
//
// The store has no opinion on who renders; pw-chart.js and pw-feed.js
// each subscribe and re-render their own region.

(function () {
  'use strict';

  var STORAGE_KEY = 'pw-filter-store-v1';
  // Default filter shape: every checkbox group is "all on". The
  // unsanctioned group is special: it's a single "only" toggle,
  // defaulting to "off" (i.e. show only unflagged posts).
  function defaultFilters() {
    return {
      brands: '__all__',     // sentinel: all enabled brands
      discourse: '__all__',
      post_types: '__all__',
      role: '__all__',
      cn_nationalism: '__all__',
      us_nationalism: '__all__',
      unsanctioned: 'off',    // 'off' | 'only'
    };
  }

  function readInitialFromBody() {
    var body = document.body;
    if (!body) return defaultFilters();
    var raw = body.getAttribute('data-pw-filters');
    if (!raw) return defaultFilters();
    try {
      var parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        var d = defaultFilters();
        for (var k in parsed) {
          if (Object.prototype.hasOwnProperty.call(parsed, k)) {
            d[k] = parsed[k];
          }
        }
        return d;
      }
    } catch (e) {
      console.warn('pw-filter-store: invalid data-pw-filters JSON', e);
    }
    return defaultFilters();
  }

  // Hydrate state from the body attribute + read the actual checkbox
  // state from the control panel (this is the source of truth for
  // which keys are currently toggled).
  function hydrateFromControlPanel(state) {
    var panel = document.getElementById('control-panel');
    if (!panel) return state;
    var groups = panel.querySelectorAll('[data-pw-filter-group]');
    var seen = {};
    groups.forEach(function (input) {
      var group = input.getAttribute('data-pw-filter-group');
      if (!group) return;
      seen[group] = seen[group] || [];
      if (input.checked) {
        seen[group].push(input.value);
      }
    });
    // Special: unsanctioned is a single toggle, mapped to "only" or "off"
    if (seen['unsanctioned'] && seen['unsanctioned'].indexOf('only') !== -1) {
      state['unsanctioned'] = 'only';
    } else {
      state['unsanctioned'] = 'off';
    }
    // Map all other groups: if at least one checked, send the array;
    // if NONE checked, send an empty array (filter narrows to nothing).
    ['brands', 'discourse', 'post_types', 'role',
     'cn_nationalism', 'us_nationalism'].forEach(function (k) {
      if (seen[k] && seen[k].length > 0) {
        state[k] = seen[k];
      } else if (seen[k]) {
        state[k] = [];
      }
    });
    return state;
  }

  var state = readInitialFromBody();
  state = hydrateFromControlPanel(state);

  var handlers = {};   // event -> [handler]
  function emit(event, detail) {
    var ev = new CustomEvent(event, { detail: detail || {} });
    document.dispatchEvent(ev);
  }

  // Wire up checkbox change events on the control panel.
  function wireControlPanel() {
    var panel = document.getElementById('control-panel');
    if (!panel) return;
    var inputs = panel.querySelectorAll('input[type="checkbox"][data-pw-filter-group]');
    inputs.forEach(function (input) {
      input.addEventListener('change', function () {
        var group = input.getAttribute('data-pw-filter-group');
        // Re-hydrate from the panel (one toggle can change a group shape).
        state = hydrateFromControlPanel(state);
        emit('pw:filter-change', { key: group, filters: state });
      });
    });
  }

  // Public API
  var pwFilter = {
    get: function () { return JSON.parse(JSON.stringify(state)); },
    set: function (key, value) {
      state[key] = value;
      emit('pw:filter-change', { key: key, filters: state });
    },
    on: function (event, handler) {
      if (!handlers[event]) handlers[event] = [];
      handlers[event].push(handler);
      document.addEventListener(event, function (e) {
        try { handler(e); } catch (err) { console.warn('pw handler', err); }
      });
    },
    state: state,
  };
  window.pwFilter = pwFilter;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireControlPanel);
  } else {
    wireControlPanel();
  }
})();
