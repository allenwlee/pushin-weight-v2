// x_monitor/static/trend-chart.js
// Per-card stacked area chart for the dashboard grid. Driven by the
// `data-chart` JSON attribute on `.trend-chart-wrap` (populated by
// serialize_grid_card via Jinja's tojson filter). Idempotent on htmx
// re-renders: destroys any prior Chart.js instance on the canvas before
// creating a new one.

(function () {
  'use strict';

  // Six series, ordered to match the old signal-bar left-to-right.
  // Keys must match `chart_series_keys` in dashboard.py.
  var SIGNAL_KEYS = [
    'release',
    'community_question',
    'criticism',
    'commenter_capture',
    'other',
    'praise',
  ];

  var SIGNAL_LABELS = {
    release: 'Q1 release',
    community_question: 'Q2 community',
    criticism: 'Q3 criticism',
    commenter_capture: 'Q4 commenters',
    other: 'Q5 other',
    praise: 'Q6 praise',
  };

  // CSS custom property names per signal. Read at chart-creation time so
  // theme changes take effect without a page reload.
  var SIGNAL_CSS_VARS = {
    release: '--bar-release',
    community_question: '--bar-community',
    criticism: '--bar-criticism',
    commenter_capture: '--bar-other',  // shares with Q5 — both "ambient"
    other: '--bar-other',
    praise: '--bar-praise',
  };

  function cssVar(name) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(name)
      .trim();
  }

  function colorFor(signal) {
    var name = SIGNAL_CSS_VARS[signal];
    return name ? cssVar(name) : '#9ca3af';
  }

  function renderOne(canvas) {
    var wrap = canvas.closest('.trend-chart-wrap');
    if (!wrap) return;
    var raw = wrap.getAttribute('data-chart') || '{}';
    var payload;
    try {
      payload = JSON.parse(raw);
    } catch (e) {
      console.warn('trend-chart: invalid data-chart JSON', e);
      return;
    }
    var days = payload.days || [];
    var series = payload.series || {};

    // v1.7-i18n (Unit 5): the server emits a per-card data-signal-labels
    // attribute when the dashboard locale resolves to a label-bearing
    // locale. When present, it overrides SIGNAL_LABELS so the chart
    // tooltips render in the user's selected language. Falls back to
    // the hardcoded English labels when the attribute is missing
    // (defensive: keeps the chart functional on partial / hand-edited
    // cards).
    var labelsRaw = wrap.getAttribute('data-signal-labels');
    var labels = SIGNAL_LABELS;
    if (labelsRaw) {
      try {
        var parsed = JSON.parse(labelsRaw);
        if (parsed && typeof parsed === 'object') {
          labels = parsed;
        }
      } catch (e) {
        console.warn('trend-chart: invalid data-signal-labels JSON', e);
      }
    }

    // Defensive destroy. Chart.js v4 cleans up on canvas removal, but
    // explicit destroy is cheap and survives upgrades / wrappers.
    var prior = Chart.getChart(canvas);
    if (prior) prior.destroy();

    var datasets = SIGNAL_KEYS
      .filter(function (k) { return series[k]; })
      .map(function (k) {
        return {
          label: labels[k] || SIGNAL_LABELS[k] || k,
          data: series[k],
          backgroundColor: colorFor(k),
          borderColor: colorFor(k),
          borderWidth: 0.5,
          fill: true,
          stack: 'all',
          pointRadius: 0,
          pointHoverRadius: 3,
        };
      });

    var muted = cssVar('--muted');

    new Chart(canvas, {
      type: 'line',
      data: { labels: days, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,  // 30s polls — animation is noise
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: false },
          tooltip: {
            enabled: true,
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + ': ' + ctx.parsed.y;
              },
            },
          },
        },
        scales: {
          x: {
            type: 'category',
            ticks: {
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 5,
              color: muted,
            },
            grid: { display: false },
          },
          y: {
            // Don't force beginAtZero: the latest day may have just 1 tweet
            // while yesterday had 6+. beginAtZero makes the right edge look
            // like a cliff. The suggestedMin floor is just a visual anchor.
            suggestedMin: 0,
            stacked: true,
            title: {
              display: true,
              text: 'tweets / day',
              color: muted,
              font: { size: 10 },
            },
            ticks: { color: muted, precision: 0 },
            grid: { color: 'rgba(139, 148, 158, 0.1)' },
          },
        },
      },
    });
  }

  function renderAll(root) {
    var scope = root || document;
    var canvases = scope.querySelectorAll('canvas.trend-chart');
    for (var i = 0; i < canvases.length; i++) {
      renderOne(canvases[i]);
    }
  }

  // Initial render after parsing.
  document.addEventListener('DOMContentLoaded', function () {
    renderAll(document);
  });

  // htmx re-renders the <main> contents every poll; the new <canvas>
  // elements need fresh Chart instances. `htmx:afterSwap` fires on the
  // swapped-in container.
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    renderAll(evt.target);
  });

  // Card-wide click handler. After the card-link <a> wrapper was removed
  // (so each top-3 post can be a real first-class <a> to the tweet), the
  // rest of the card body (header, chart, footer) needs an explicit way
  // to navigate to the model drill-down. Clicks on .top3-link (the per-post
  // anchors) stop propagation so the tweet opens in a new tab as expected.
  function wireCardClicks(root) {
    var scope = root || document;
    var cards = scope.querySelectorAll('.model-card[data-href]');
    for (var i = 0; i < cards.length; i++) {
      (function (card) {
        if (card.__cardClickWired) return;
        card.__cardClickWired = true;
        card.addEventListener('click', function (e) {
          // Don't intercept clicks on real anchors inside the card
          // (the per-post top-3 links).
          if (e.target.closest('a')) return;
          // Don't intercept clicks on canvas / chart (they may handle
          // their own events).
          if (e.target.closest('canvas')) return;
          window.location.href = card.getAttribute('data-href');
        });
      })(cards[i]);
    }
  }
  document.addEventListener('DOMContentLoaded', function () {
    wireCardClicks(document);
  });
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    wireCardClicks(evt.target);
  });
})();
