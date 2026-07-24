// {{AGENT_ATTRIBUTION}}
// x_monitor/static/pw-chart.js
// Pushin' Weight (走个量) multi-brand home chart (U7 of
// feat/pushin-weight-home-pages, 2026-07-06).
//
// Architecture (mirrors combined-chart.js):
// - One Chart.js instance per .home-chart canvas.
// - One total line per enabled brand, in the brand's accent color.
// - On `pw:filter-change` (U3, 2026-07-16), re-fetches
//   /chart.html with the new filters in the query, swaps
//   the chart region innerHTML, and re-renders the new canvas.
// - On htmx:afterSwap of the chart region, destroys any prior instance
//   and re-binds to the new canvas.

(function () {
  'use strict';

  function readPayload(canvas) {
    var raw = canvas.getAttribute('data-home') || '{}';
    try { return JSON.parse(raw); }
    catch (e) { return null; }
  }

  function readColorsFromCss() {
    return {
      '--pt-buzz-releases': getComputedStyle(document.documentElement)
        .getPropertyValue('--pt-buzz-releases').trim(),
      '--pt-hands-on-usage': getComputedStyle(document.documentElement)
        .getPropertyValue('--pt-hands-on-usage').trim(),
    };
  }

  function renderOne(canvas) {
    var payload = readPayload(canvas);
    if (!payload) return;
    var days = payload.days || [];
    var granularity = payload.granularity || 'day';
    var series = payload.series || {};
    var colors = payload.colors || {};
    var stacked = payload.stacked || {};
    var brandList = Object.keys(series);

    var prior = Chart.getChart(canvas);
    if (prior) prior.destroy();

    var datasets = [];
    brandList.forEach(function (brand) {
      var stroke = colors[brand] || '#9ca3af';
      // For minute granularity, convert 0→NaN so spanGaps skips the
      // baseline — the line connects non-zero dots directly without
      // dropping to zero between events.
      var totalData = granularity === 'minute'
        ? series[brand].map(function(v) { return v === 0 ? NaN : v; })
        : series[brand];
      datasets.push({
        label: brand + ' (total)',
        data: totalData,
        type: 'line',
        borderColor: stroke,
        backgroundColor: stroke,
        borderWidth: 2,
        pointRadius: granularity === 'minute' ? 1.5 : 0,
        tension: granularity === 'minute' ? 0.3 : 0.0,
        fill: false,
        _brandIndex: brandList.indexOf(brand),
        _isTotalLine: true,
      });
      // Per-discourse overlay datasets (mirrors combined-chart.js D3
      // pattern). All hidden by default; hover reveals them.
      var brandStacked = stacked[brand] || {};
      Object.keys(brandStacked).forEach(function (dk) {
        var stackedData = granularity === 'minute'
          ? brandStacked[dk].map(function(v) { return v === 0 ? NaN : v; })
          : brandStacked[dk];
        datasets.push({
          label: brand + ' ' + dk,
          data: stackedData,
          type: 'line',
          borderColor: 'transparent',
          backgroundColor: colorVarFor(dk),
          borderWidth: 0,
          pointRadius: granularity === 'minute' ? 1.5 : 0,
          tension: granularity === 'minute' ? 0.3 : 0.0,
          fill: datasets.length === 0 ? 'origin' : '-1',
          hidden: true,
          _isTotalLine: false,
          _brandIndex: brandList.indexOf(brand),
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
          legend: { display: false },
          tooltip: {
            enabled: true,
            mode: 'index',
            intersect: false,
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
            ticks: granularity === 'minute' ? {
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 7,
              callback: function (value, index) {
                var label = this.getLabelForValue(value);
                var d = new Date(label);
                if (isNaN(d.getTime())) return label;
                if (index === this.chart.data.labels.length - 1) return 'now';
                if (d.getMinutes() === 0) {
                  var h = String(d.getHours());
                  return h.length < 2 ? '0' + h + ':00' : h + ':00';
                }
                return '';
              },
            } : {
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 6,
            },
            grid: { display: false },
          },
          y: {
            beginAtZero: true,
            title: {
              display: true,
              text: granularity === 'minute' ? 'posts / 5min' : 'posts / day',
            },
            ticks: { precision: 0 },
          },
        },
        onHover: function (event, activeElements, c) {
          var hoveredBrandIndex = -1;
          if (activeElements && activeElements.length > 0) {
            var cursorY = (event && event.y != null) ? event.y : null;
            if (cursorY != null && activeElements[0].index != null) {
              var dataIdx = activeElements[0].index;
              var yScale = c.scales.y;
              var bestDist = Infinity;
              var bestBrand = -1;
              for (var i = 0; i < activeElements.length; i++) {
                var dsIdx2 = activeElements[i].datasetIndex;
                var ds2 = c.data.datasets[dsIdx2];
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
              for (var j = 0; j < activeElements.length; j++) {
                var dsIdx = activeElements[j].datasetIndex;
                var ds = c.data.datasets[dsIdx];
                if (ds && ds._isTotalLine) {
                  hoveredBrandIndex = ds._brandIndex;
                  break;
                }
              }
            }
          }
          c.data.datasets.forEach(function (ds) {
            if (ds._isTotalLine) return;
            ds.hidden = hoveredBrandIndex === -1
              ? true
              : (ds._brandIndex !== hoveredBrandIndex);
          });
          c.update('none');
        },
      },
    });
    return chart;
  }

  // Map a discourse key to its CSS-var color (existing --bar-* tokens).
  function colorVarFor(discourseKey) {
    var v = '--bar-' + discourseKey.replace(/-/g, '-');
    return getComputedStyle(document.documentElement).getPropertyValue(v).trim() || '#9ca3af';
  }

  function renderAll() {
    var canvases = document.querySelectorAll('canvas.home-chart');
    for (var i = 0; i < canvases.length; i++) {
      try { renderOne(canvases[i]); }
      catch (e) { console.warn('pw-chart: render failed', e); }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderAll);
  } else {
    renderAll();
  }

  // Re-bind on htmx swaps of the home-chart region.
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (!evt.target) return;
    if (evt.target.id === 'home-chart' || evt.target.id === 'brand-chart') {
      var canvas = evt.target.querySelector('canvas');
      if (canvas) {
        try { renderOne(canvas); }
        catch (e) { console.warn('pw-chart: post-swap render failed', e); }
      }
    }
  });

  // U3 (2026-07-16): react to control-panel filter changes. Re-fetch
  // the chart fragment with the active filters in the query, swap the
  // region innerHTML, and re-render the canvas. Simple and correct;
  // htmx's `every Ns` poll carries the same filter via `hx-vals` so
  // both paths converge on the same payload.
  //
  // Scoped to the multi-brand page: this module owns `#home-chart`
  // only. The single-brand page (`/brand_home.html.j2`) loads
  // pw-brand-chart.js for `#brand-chart` and does not include
  // `#home-chart`, so we no-op there.
  function refetchChartWithFilters() {
    var region = document.getElementById('home-chart');
    if (!region) return;
    var filters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
    var url = '/chart.html?filters=' + encodeURIComponent(JSON.stringify(filters));
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        region.innerHTML = html;
        var canvas = region.querySelector('canvas');
        if (canvas) {
          try { renderOne(canvas); }
          catch (e) { console.warn('pw-chart: post-filter render failed', e); }
        }
      })
      .catch(function (e) { console.warn('pw-chart: filter refetch failed', e); });
  }
  document.addEventListener('pw:filter-change', refetchChartWithFilters);
})();
