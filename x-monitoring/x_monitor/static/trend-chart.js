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

    // Defensive destroy. Chart.js v4 cleans up on canvas removal, but
    // explicit destroy is cheap and survives upgrades / wrappers.
    var prior = Chart.getChart(canvas);
    if (prior) prior.destroy();

    var datasets = SIGNAL_KEYS
      .filter(function (k) { return series[k]; })
      .map(function (k) {
        return {
          label: SIGNAL_LABELS[k],
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
            beginAtZero: true,
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
})();
