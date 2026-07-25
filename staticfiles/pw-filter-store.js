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
      lang: '__all__',         // added 2026-07-22
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
    // Count total checkboxes per group so we can collapse a fully-checked
    // group back to the "__all__" sentinel. The server's _post_matches_filter
    // documents "__all__" as "all on" (no narrowing); emitting the full
    // checkbox array instead causes the nationality/role axes (whose
    // top-level fields are not denormalized on every post) to fail the
    // `post.cn_nationalism not in active` check and collapse totals to 0.
    var totalByGroup = {};
    panel.querySelectorAll('[data-pw-filter-group]').forEach(function (input) {
      var g = input.getAttribute('data-pw-filter-group');
      if (!g || g === 'unsanctioned') return;
      totalByGroup[g] = (totalByGroup[g] || 0) + 1;
    });

    // Map all other groups:
    //   - all checked  → "__all__" (no narrowing)
    //   - some checked → array of values
    //   - none checked → [] (narrows to zero)
    ['brands', 'discourse', 'post_types', 'role', 'lang',
     'cn_nationalism', 'us_nationalism'].forEach(function (k) {
      if (!seen[k]) return;
      if (seen[k].length === 0) {
        state[k] = [];
      } else if (seen[k].length === (totalByGroup[k] || 0)) {
        state[k] = '__all__';
      } else {
        state[k] = seen[k];
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

    // --- "only" checkboxes (brands-only for now) ---
    // When an "only" checkbox is checked, all include checkboxes for
    // that group are cleared and only the "only"-selected brands are
    // included. Multiple "only" checkboxes can be active (union).
    // When the last "only" is unchecked, all includes are restored.
    panel.querySelectorAll('[data-pw-filter-only]').forEach(function (onlyCb) {
      onlyCb.addEventListener('change', function () {
        var group = onlyCb.getAttribute('data-pw-filter-only');
        var value = onlyCb.value;
        var allOnlyCbs = panel.querySelectorAll('[data-pw-filter-only="' + group + '"]');
        var allIncludeCbs = panel.querySelectorAll('[data-pw-filter-group="' + group + '"]');

        if (onlyCb.checked) {
          // This brand is now "only" — rebuild the include set from all
          // active "only" checkboxes.
          allIncludeCbs.forEach(function (icb) { icb.checked = false; });
          allOnlyCbs.forEach(function (ocb) {
            if (ocb.checked) {
              var icb = panel.querySelector(
                '[data-pw-filter-group="' + group + '"][value="' + ocb.value + '"]'
              );
              if (icb) icb.checked = true;
            }
          });
        } else {
          // Unchecked this "only". If no "only" checkboxes remain active,
          // restore all includes. Otherwise just remove this brand.
          var anyOnly = false;
          allOnlyCbs.forEach(function (ocb) { if (ocb.checked) anyOnly = true; });
          if (!anyOnly) {
            allIncludeCbs.forEach(function (icb) { icb.checked = true; });
          } else {
            var icb = panel.querySelector(
              '[data-pw-filter-group="' + group + '"][value="' + value + '"]'
            );
            if (icb) icb.checked = false;
          }
        }

        state = hydrateFromControlPanel(state);
        emit('pw:filter-change', { key: group, filters: state });
      });
    });

    // --- window buttons (1d / 7d / 30d) — these live in .topbar, not #control-panel ---
    document.querySelectorAll('[data-pw-window-btn]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var days = parseInt(btn.getAttribute('data-pw-window-btn'), 10);
        // Update active state on all window buttons
        document.querySelectorAll('[data-pw-window-btn]').forEach(function (b) {
          b.classList.toggle('is-active', b === btn);
        });
        // Store window in filter state
        state.window = days;
        emit('pw:filter-change', { key: 'window', filters: state });
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
