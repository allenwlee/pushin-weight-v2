// {{AGENT_ATTRIBUTION}}
// x_monitor/static/pw-locale-toggle.js
// Pushin' Weight (走个量) topbar locale + window toggle hooks
// (U7 of feat/pushin-weight-home-pages, 2026-07-06).
//
// - Locale buttons (data-pw-locale-btn) POST to
//   /api/v1/home.locale/<locale>, then reload (cheap; the route
//   redirects back with 303).
// - Window buttons (data-pw-window-btn) POST to
//   /api/v1/home.window/<n>, same reload pattern.
// - Emits `pw:locale-change` and `pw:window-change` for the chart
//   module to react (KTD10).

(function () {
  'use strict';

  function postAndReload(url) {
    var form = document.createElement('form');
    form.method = 'POST';
    form.action = url;
    form.style.display = 'none';
    document.body.appendChild(form);
    form.submit();
  }

  function wireLocale() {
    var buttons = document.querySelectorAll('[data-pw-locale-btn]');
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var locale = btn.getAttribute('data-pw-locale-btn');
        document.dispatchEvent(new CustomEvent('pw:locale-change', {
          detail: { locale: locale },
        }));
        postAndReload('/api/v1/home.locale/' + encodeURIComponent(locale));
      });
    });
  }

  function wireWindow() {
    var buttons = document.querySelectorAll('[data-pw-window-btn]');
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var n = btn.getAttribute('data-pw-window-btn');
        document.dispatchEvent(new CustomEvent('pw:window-change', {
          detail: { window: parseInt(n, 10) },
        }));
        postAndReload('/api/v1/home.window/' + encodeURIComponent(n));
      });
    });
  }

  function init() {
    wireLocale();
    wireWindow();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
