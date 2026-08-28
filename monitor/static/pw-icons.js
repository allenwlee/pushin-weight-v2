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
    'icon-role-badge': true,
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

  var SEMANTIC_SYMBOLS = Object.freeze({
    sentiment: Object.freeze({
      positive: 'icon-sentiment',
      neutral: 'icon-sentiment-neutral',
      negative: 'icon-sentiment-negative',
      mixed: 'icon-sentiment-mixed'
    }),
    post_types: Object.freeze({
      hands_on_usage: 'icon-hands-on-hammer',
      performance_comparisons: 'icon-compare',
      buzz_releases: 'icon-announce',
      feedback_questions: 'icon-question',
      advertising_marketing: 'icon-marketing',
      event_announcement: 'icon-event'
    }),
    role: Object.freeze({
      official: 'icon-role-badge',
      staff: 'icon-role-badge',
      community: 'icon-role-badge'
    }),
    discourse: Object.freeze({ '*': 'icon-discourse' }),
    nationalism: Object.freeze({ '*': 'icon-nationalism' }),
    unsanctioned: Object.freeze({ only: 'icon-unsanctioned' })
  });

  var SEMANTIC_CLASSES = Object.freeze({
    sentiment: Object.freeze({
      positive: 'tone-positive',
      neutral: 'tone-neutral',
      negative: 'tone-negative',
      mixed: 'tone-mixed'
    }),
    role: Object.freeze({
      official: 'role-official',
      staff: 'role-staff',
      community: 'role-community'
    }),
    unsanctioned: Object.freeze({ only: 'tone-negative' })
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

  function semanticValue(registry, family, key) {
    var entries = registry[family];
    return entries ? (entries[key] || entries['*'] || '') : '';
  }

  function semanticSymbol(family, key) {
    var symbol = semanticValue(SEMANTIC_SYMBOLS, family, key);
    return ALLOWED_SYMBOLS[symbol] ? symbol : '';
  }

  function semanticClass(family, key) {
    return safeClasses(semanticValue(SEMANTIC_CLASSES, family, key));
  }

  function hydrateSemanticIcons(root) {
    if (!root || typeof root.querySelectorAll !== 'function') return;
    root.querySelectorAll('[data-pw-semantic-icon]').forEach(function (slot) {
      var family = slot.getAttribute('data-pw-semantic-family') || '';
      var key = slot.getAttribute('data-pw-semantic-key') || '';
      var symbol = semanticSymbol(family, key);
      var tone = semanticClass(family, key);
      slot.className = 'filter-option-icon' + (tone ? ' ' + tone : '');
      slot.innerHTML = render(symbol, 'filter-choice-icon');
      slot.setAttribute('aria-hidden', 'true');
    });
  }

  var api = Object.freeze({
    allowedSymbols: ALLOWED_SYMBOLS,
    semanticSymbols: SEMANTIC_SYMBOLS,
    isAllowed: function (symbolId) { return Boolean(ALLOWED_SYMBOLS[symbolId]); },
    render: render,
    semanticSymbol: semanticSymbol,
    semanticClass: semanticClass,
    hydrateSemanticIcons: hydrateSemanticIcons
  });

  global.pwIcon = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        hydrateSemanticIcons(document);
      });
    } else {
      hydrateSemanticIcons(document);
    }
  }
})(typeof window !== 'undefined' ? window : globalThis);
