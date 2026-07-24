// {{AGENT_ATTRIBUTION}}
// x_monitor/static/pw-locale-toggle.js
// Pushin' Weight (走个量) topbar locale + window toggle hooks
//
// - Locale buttons (data-pw-locale-btn) POST to
//   /locale/<locale>, then reload (cheap; the route
//   redirects back with 303).
// - Window buttons (data-pw-window-btn) POST to
//   /window/<n>, same reload pattern.
// - Emits `pw:locale-change` and `pw:window-change` for the chart
//   module to react (KTD10).

(function () {
  'use strict';

  // Read Django CSRF token from cookie (set by CsrfViewMiddleware).
  function getCSRFToken() {
    var name = 'csrftoken=';
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf(name) === 0) {
        return decodeURIComponent(c.substring(name.length));
      }
    }
    return '';
  }

  function postAndReload(url) {
    var form = document.createElement('form');
    form.method = 'POST';
    form.action = url;
    form.style.display = 'none';

    // Inject CSRF token so Django accepts the POST.
    var csrf = document.createElement('input');
    csrf.type = 'hidden';
    csrf.name = 'csrfmiddlewaretoken';
    csrf.value = getCSRFToken();
    form.appendChild(csrf);

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
        postAndReload('/locale/' + encodeURIComponent(locale) + '/');
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
        postAndReload('/window/' + encodeURIComponent(n) + '/');
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
