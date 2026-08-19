// Pushin' Weight (走个量) topbar locale + window toggle hooks
//
// - Locale buttons (data-pw-locale-btn) POST to
//   /locale/<locale>, then reload (cheap; the route
//   redirects back with 303).
// - Legacy window buttons POST to /window/<n>; the public V22 filter store
//   owns window state without a reload.
// - Emits `pw:locale-change` and `pw:window-change` for the chart
//   module to react (KTD10).

(function () {
  'use strict';

  // This is intentionally v22-scoped UI copy.  account.role and the
  // unsanctioned taxonomy remain database-owned elsewhere; these labels only
  // describe the authored chrome in the v22 shell.
  var CHROME = {
    zh_cn: {
      locale_aria: '显示语言',
      window_aria: '时间窗口',
      pill_brands: '品牌',
      pill_discourse: '话语',
      pill_role: '角色',
      pill_lang: '语言',
      pill_sentiment: '情绪',
      pill_nationalism: '民族主义',
      pill_unsanctioned: '未授权',
      tz_local: '本地',
      tz_title: '切换 本地 ⇄ 加州时间'
    },
    en: {
      locale_aria: 'Display language',
      window_aria: 'Time-period selector',
      pill_brands: 'Brands',
      pill_discourse: 'Discourse',
      pill_role: 'Role',
      pill_lang: 'Lang',
      pill_sentiment: 'Sentiment',
      pill_nationalism: 'Nationalism',
      pill_unsanctioned: 'Unsanctioned',
      tz_local: 'local',
      tz_title: 'Toggle local ⇄ California time'
    }
  };

  function chromeLocale(locale) {
    return locale === 'zh_cn' || locale === 'zh-CN' || locale === 'zh-cn' || locale === 'zh_hans' || locale === 'zh-hans' ? 'zh_cn' : 'en';
  }

  function applyChrome(locale) {
    var key = chromeLocale(locale);
    var dict = CHROME[key];
    var useZh = key === 'zh_cn';
    document.body.setAttribute('data-pw-locale', locale);
    document.documentElement.lang = useZh ? 'zh-CN' : 'en';

    document.querySelectorAll('[data-i18n], [data-i18n-tz-local]').forEach(function (element) {
      var key = element.getAttribute('data-i18n') || 'tz_local';
      var text = dict[key];
      if (text) element.textContent = text;
    });

    var localeNav = document.querySelector('.locale-toggle');
    if (localeNav) {
      localeNav.setAttribute('aria-label', dict.locale_aria);
      localeNav.querySelectorAll('[data-pw-locale-btn]').forEach(function (button) {
        button.textContent = button.getAttribute(useZh ? 'data-label-zh' : 'data-label-en') || button.textContent;
        button.classList.toggle('is-active', chromeLocale(button.getAttribute('data-pw-locale-btn')) === key);
      });
    }

    document.querySelectorAll('.window-toggle:not(.locale-toggle)').forEach(function (windowNav) {
      windowNav.setAttribute('aria-label', dict.window_aria);
      windowNav.querySelectorAll('[data-pw-window-btn]').forEach(function (button) {
        button.textContent = button.getAttribute(useZh ? 'data-label-zh' : 'data-label-en') || button.textContent;
      });
    });

    var timezone = document.querySelector('[data-tz-widget]');
    if (timezone) {
      timezone.setAttribute('title', dict.tz_title);
      timezone.setAttribute('aria-label', dict.tz_title);
    }
    document.dispatchEvent(new CustomEvent('pw:chrome-change', { detail: { locale: locale } }));
  }

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
        applyChrome(locale);
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
    applyChrome(document.body.getAttribute('data-pw-locale') || 'zh_cn');
    wireLocale();
    // The V22 filter store owns public window changes so both consumers use
    // one event without a reload. Legacy pages retain their POST/cookie flow.
    if (!document.querySelector('.filter-bar')) wireWindow();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  window.pwApplyChrome = applyChrome;
})();
