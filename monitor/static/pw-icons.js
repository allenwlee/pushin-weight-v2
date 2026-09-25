// Owner-approved Cyber-Quan SVG renderer for the public home surface.
(function (global) {
  'use strict';

  var ALLOWED_SYMBOLS = Object.freeze({
    'icon-pending-armillary-frame': true,
    'icon-failed-stop': true,
    'icon-language-globe': true,
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
    'a-opportunity': true,
    'a-jobs': true,
    'a-personnel': true,
    'a-opinions': true,
    'a-research': true,
    'a-finance': true,
    'a-other': true,
    'distillation-a': true,
    'licensing-b': true,
    'api-a': true,
    'agents-b': true,
    'local-b': true,
    'evaluation-a': true,
    'cost-a': true,
    'bug-a': true,
    'complaint-a': true,
    'testimony-a': true,
    'idea-a': true,
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
      results_evaluations: 'icon-compare',
      results_analysis: 'icon-compare',
      releases_updates: 'icon-announce',
      questions_requests: 'icon-question',
      advertising_marketing: 'icon-marketing',
      events: 'icon-event',
      opportunities: 'a-opportunity',
      job_listings: 'a-jobs',
      personnel_changes: 'a-personnel',
      events_opportunities: 'icon-event',
      opinions_reactions: 'a-opinions',
      research_explanations: 'a-research',
      business_finance: 'a-finance',
      other: 'a-other'
    }),
    audience_topics: Object.freeze({
      local_inference: 'local-b',
      cost_performance: 'cost-a',
      model_distillation: 'distillation-a',
      evals_benchmarks: 'evaluation-a',
      openness_license: 'licensing-b',
      agents_tools: 'agents-b',
      api_developer_surface: 'api-a'
    }),
    geopolitical_modes: Object.freeze({
      reporting: 'icon-discourse',
      framework: 'icon-nationalism',
      nationalism: 'icon-nationalism'
    }),
    product_labels: Object.freeze({
      bug: 'bug-a',
      complaint: 'complaint-a',
      testimonial: 'testimony-a',
      ideas_requests: 'idea-a',
      investigate_claim: 'icon-unsanctioned',
      misinformation: 'icon-unsanctioned'
    }),
    role: Object.freeze({
      official: 'icon-role-badge',
      staff: 'icon-role-badge',
      community: 'icon-role-badge'
    }),
    nationalism: Object.freeze({ '*': 'icon-nationalism' }),
    untracked_brand_promotions: Object.freeze({
      general: 'icon-unsanctioned',
      spam: 'icon-unsanctioned',
      scam: 'icon-unsanctioned',
      crypto: 'icon-unsanctioned',
      unauthorized: 'icon-unsanctioned'
    }),
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
    untracked_brand_promotions: Object.freeze({
      general: 'tone-negative',
      spam: 'tone-negative',
      scam: 'tone-negative',
      crypto: 'tone-negative',
      unauthorized: 'tone-negative'
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
    var external = symbolId === 'icon-failed-stop' || symbolId === 'icon-language-globe' ||
      symbolId === 'icon-pending-armillary-frame';
    var sprite = external && global.document && global.document.body &&
      global.document.body.getAttribute('data-pw-processing-glyph-sprite-url');
    var href = (sprite || '') + '#' + symbolId;
    return '<svg class="pw-icon' + (classes ? ' ' + classes : '') +
      '" aria-hidden="true" focusable="false"><use href="' + href.replace(/&/g, '&amp;').replace(/"/g, '&quot;') +
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
