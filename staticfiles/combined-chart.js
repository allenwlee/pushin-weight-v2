// {{AGENT_ATTRIBUTION}}
// x_monitor/static/combined-chart.js
// Combined multi-brand chart with overlay hover area. Driven by the
// `data-combined` JSON attribute on .combined-chart-wrap (populated by
// serialize_combined_chart via Jinja's tojson filter).
//
// Architecture:
// - One Chart.js instance per canvas.
// - 1 dataset per enabled brand, type 'line', plotting the per-day TOTAL
//   post count. Always visible.
// - 6 overlay datasets per brand (one per signal), all created with
//   hidden: true. On mouseover of a brand's total line, its 6 overlay
//   datasets become visible. On mouseout they hide again.
// - Idempotent on htmx re-renders: destroys any prior Chart.js instance
//   on the canvas before creating a new one (matches trend-chart.js).

(function () {
  'use strict';

  // Six signal keys, ordered to match serialize_combined_chart's
  // chart_series_keys in x_monitor/dashboard.py.
  var SIGNAL_KEYS = [
    'release',
    'community_question',
    'criticism',
    'commenter_capture',
    'other',
    'praise',
  ];

  // CSS custom property names per signal. Read at chart-creation time so
  // theme changes take effect without a page reload. Same token names as
  // trend-chart.js for consistency with the 9-card grid.
  var SIGNAL_CSS_VARS = {
    release: '--bar-release',
    community_question: '--bar-community',
    criticism: '--bar-criticism',
    commenter_capture: '--bar-commenters',
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
    var wrap = canvas.closest('.combined-chart-wrap');
    if (!wrap) return;
    var raw = wrap.getAttribute('data-combined') || '{}';
    var payload;
    try {
      payload = JSON.parse(raw);
    } catch (e) {
      console.warn('combined-chart: invalid data-combined JSON', e);
      return;
    }
    var days = payload.days || [];
    var series = payload.series || {};
    var stacked = payload.stacked || {};
    var colors = payload.colors || {};

    // Defensive destroy. Chart.js v4 cleans up on canvas removal, but
    // explicit destroy is cheap and survives upgrades / wrappers.
    var prior = Chart.getChart(canvas);
    if (prior) prior.destroy();

    var brands = Object.keys(series);

    // Build datasets: one total line per brand, then 6 hidden overlay
    // datasets per brand (so we can flip them visible on hover without
    // rebuilding the chart).
    var datasets = [];
    brands.forEach(function (brand) {
      // Total line — always visible, stroke = brand's accent color
      // from MODEL_ACCENT_COLORS (passed via payload.colors).
      var stroke = colors[brand] || '#9ca3af';
      datasets.push({
        label: brand + ' (total)',
        data: series[brand],
        type: 'line',
        borderColor: stroke,
        backgroundColor: stroke,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.0,
        fill: false,
        // Hoverable signal index: hover events on this dataset
        // route back to the brand via indexOf on `brands`.
        _brandIndex: brands.indexOf(brand),
        _isTotalLine: true,
      });
      // Six overlay datasets — all hidden by default.
      var brandStacked = stacked[brand] || {};
      SIGNAL_KEYS.forEach(function (sig) {
        var sigColor = colorFor(sig);
        datasets.push({
          label: brand + ' ' + sig,
          data: brandStacked[sig] || [],
          type: 'line',
          borderColor: 'transparent',
          backgroundColor: sigColor,
          borderWidth: 0,
          pointRadius: 0,
          // Stacked area: each signal stacks on the prior one.
          fill: datasets.length === 0 ? 'origin' : '-1',
          hidden: true,
          // Mark as overlay (not the total line) so onHover skips it.
          _isTotalLine: false,
          _brandIndex: brands.indexOf(brand),
        });
      });
    });

    var chart = new Chart(canvas, {
      type: 'line',
      data: { labels: days, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            // Hide the noisy per-signal legend; the topbar nav strip
            // already explains the chart.
            display: false,
          },
          tooltip: {
            enabled: true,
            mode: 'index',
            intersect: false,
            // Only show totals in the tooltip (filter out the 66
            // overlay datasets so the tooltip stays compact).
            filter: function (tooltipItem) {
              return tooltipItem.dataset._isTotalLine === true;
            },
            callbacks: {
              label: function (ctx) {
                var v = ctx.parsed.y;
                return ctx.dataset.label + ': ' + v + (v === 1 ? ' post' : ' posts');
              },
            },
          },
        },
        scales: {
          x: {
            type: 'category',
            labels: days,
            ticks: {
              // Show ~6 date labels across the window to avoid clutter.
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 6,
            },
            grid: { display: false },
          },
          y: {
            beginAtZero: true,
            title: { display: true, text: 'posts / day' },
            ticks: { precision: 0 },
          },
        },
        // Hover handler: when a total line is hovered, reveal the 6
        // overlay datasets for that brand. When no dataset is hovered,
        // hide all overlays.
        //
        // With 11 brand lines and intersect:false, Chart.js returns ALL
        // 11 total lines in activeElements when the cursor is anywhere
        // over the chart. We pick the closest total line to the cursor
        // Y by computing the pixel distance from cursor to each line's
        // data point at activeElements[0].index.
        onHover: function (event, activeElements, chart) {
          var hoveredBrandIndex = -1;
          if (activeElements && activeElements.length > 0) {
            // Cursor position in CSS pixels (event may be a native MouseEvent
            // or a Chart.js fake event with x/y already in chart coords).
            var cursorY = (event && event.y != null) ? event.y : null;
            if (cursorY != null && activeElements[0].index != null) {
              var dataIdx = activeElements[0].index;
              var yScale = chart.scales.y;
              var bestDist = Infinity;
              var bestBrand = -1;
              // Iterate all hovered total-line datasets, compute each
              // one's pixel Y at dataIdx, and pick the closest to cursorY.
              for (var i = 0; i < activeElements.length; i++) {
                var dsIdx2 = activeElements[i].datasetIndex;
                var ds2 = chart.data.datasets[dsIdx2];
                if (!ds2 || !ds2._isTotalLine) continue;
                var value = ds2.data[dataIdx];
                if (value == null) continue;
                var linePixelY = yScale.getPixelForValue(value);
                var dist = Math.abs(cursorY - linePixelY);
                if (dist < bestDist) {
                  bestDist = dist;
                  bestBrand = ds2._brandIndex;
                }
              }
              hoveredBrandIndex = bestBrand;
            } else {
              // Fallback: pick the first hovered TOTAL line.
              for (var j = 0; j < activeElements.length; j++) {
                var dsIdx = activeElements[j].datasetIndex;
                var ds = chart.data.datasets[dsIdx];
                if (ds && ds._isTotalLine) {
                  hoveredBrandIndex = ds._brandIndex;
                  break;
                }
              }
            }
          }
          chart.data.datasets.forEach(function (ds) {
            if (ds._isTotalLine) return; // never toggle the total lines
            ds.hidden = hoveredBrandIndex === -1
              ? true
              : (ds._brandIndex !== hoveredBrandIndex);
          });
          // No animation on hover state change — feels instant.
          chart.update('none');
        },
      },
    });
  }

  function renderAll() {
    var canvases = document.querySelectorAll('canvas.combined-chart');
    for (var i = 0; i < canvases.length; i++) {
      try {
        renderOne(canvases[i]);
      } catch (e) {
        console.warn('combined-chart: render failed for canvas', canvases[i], e);
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderAll);
  } else {
    renderAll();
  }

  // Re-render after every htmx swap (the innerHTML replacement destroys
  // the old canvas, so we re-init on the new one).
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    // Only re-render if the swap affected a combined-chart region.
    if (evt.target && evt.target.id === 'combined-chart') {
      var canvas = evt.target.querySelector('canvas.combined-chart');
      if (canvas) {
        try {
          renderOne(canvas);
        } catch (e) {
          console.warn('combined-chart: post-swap render failed', e);
        }
      }
    }
  });
})();