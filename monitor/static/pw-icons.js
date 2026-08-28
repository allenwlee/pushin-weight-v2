// Owner-approved Cyber-Quan SVG renderer for the public home surface.
(function (global) {
  'use strict';

  var ALLOWED_SYMBOLS = Object.freeze({
    'mark-quiet': true,
    'icon-heart': true,
    'icon-reply': true,
    'icon-repost': true,
    'icon-rise': true,
    'icon-flat': true,
    'icon-fall': true,
    'icon-followers-1': true,
    'icon-followers-2': true,
    'icon-followers-3': true,
    'icon-followers-4': true,
    'icon-sentiment-neutral': true,
    'icon-sentiment-negative': true,
    'icon-sentiment-mixed': true,
    'icon-hands-on-hammer': true,
    'icon-compare': true,
    'icon-question': true,
    'icon-marketing': true,
    'icon-event': true,
    'icon-discourse': true,
    'icon-nationalism': true,
    'icon-unsanctioned': true,
    'icon-california': true,
    'icon-beijing': true,
    'icon-sentiment': true,
    'icon-announce': true,
    'icon-star': true,
    'icon-caret': true,
    'icon-sunrise': true,
    'icon-day': true,
    'icon-dusk': true,
    'icon-night': true
  });

  function safeClasses(className) {
    return String(className || '')
      .split(/\s+/)
      .filter(function (name) { return /^[a-z0-9_-]+$/i.test(name); })
      .join(' ');
  }

  function render(symbolId, className) {
    if (!ALLOWED_SYMBOLS[symbolId]) return '';
    var classes = safeClasses(className);
    return '<svg class="pw-icon' + (classes ? ' ' + classes : '') +
      '" aria-hidden="true" focusable="false"><use href="#' + symbolId +
      '"></use></svg>';
  }

  var api = Object.freeze({
    allowedSymbols: ALLOWED_SYMBOLS,
    isAllowed: function (symbolId) { return Boolean(ALLOWED_SYMBOLS[symbolId]); },
    render: render
  });

  global.pwIcon = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
