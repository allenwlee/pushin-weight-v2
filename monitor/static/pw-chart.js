// {{AGENT_ATTRIBUTION}}
// x_monitor/static/pw-chart.js
// Pushin' Weight (走个量) multi-brand home chart (U7 of
// feat/pushin-weight-home-pages, 2026-07-06).
//
// Architecture (mirrors combined-chart.js):
// - One Chart.js instance per .home-chart canvas.
// - One total line per enabled brand, in the brand's accent color.
// - On `pw:filter-change` (U3, 2026-07-16), re-fetches
//   /api/v1/home.chart.html with the new filters in the query, swaps
//   the chart region innerHTML, and re-renders the new canvas.
// - On htmx:afterSwap of the chart region, destroys any prior instance
//   and re-binds to the new canvas.

(function () {
  'use strict';

  // The root route must stay structurally faithful to the authored mockup,
  // which has no chart-region ID. Scope the public chart runtime to an
  // implementation-only data marker instead. /internal retains its legacy
  // ID as a fallback while it keeps its separate legacy shell.
  var HOME_CHART_REGION_SELECTOR = '.home-chart-wrap[data-pw-chart]';

  function getHomeChartRegion() {
    return document.querySelector(HOME_CHART_REGION_SELECTOR) ||
      document.getElementById('home-chart');
  }

  function isHomeChartRegion(region) {
    return Boolean(region && region.matches &&
      region.matches(HOME_CHART_REGION_SELECTOR));
  }

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

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var MOCKUP_BRAND_ORDER = ['moonshot_kimi', 'deepseek', 'minimax', 'qwen', 'ernie'];
  var MOCKUP_BRAND_NAMES = {
    moonshot_kimi: 'Kimi',
    deepseek: 'DeepSeek',
    minimax: 'MiniMax',
    qwen: 'Qwen',
    ernie: 'ERNIE',
  };

  function isSvgChart(chart) {
    return Boolean(chart && chart.tagName && chart.tagName.toLowerCase() === 'svg');
  }

  function chartIn(region) {
    if (!region) return null;
    return region.querySelector('canvas.home-chart') || region.querySelector('svg.home-chart');
  }

  function orderedBrands(series) {
    return Object.keys(series).sort(function (a, b) {
      var aIndex = MOCKUP_BRAND_ORDER.indexOf(a);
      var bIndex = MOCKUP_BRAND_ORDER.indexOf(b);
      if (aIndex === -1) aIndex = MOCKUP_BRAND_ORDER.length;
      if (bIndex === -1) bIndex = MOCKUP_BRAND_ORDER.length;
      return aIndex === bIndex ? a.localeCompare(b) : aIndex - bIndex;
    });
  }

  function svgElement(name, attrs) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    return node;
  }

  function renderSvgLegend(svg, brands, colors) {
    var legend = svg.parentNode && svg.parentNode.querySelector('.legend');
    if (!legend) return;
    legend.innerHTML = brands.map(function (brand) {
      var label = MOCKUP_BRAND_NAMES[brand] || brand;
      var color = colors[brand] || '#9ca3af';
      return '<span><i style="background:' + color + '"></i>' + label + '</span>';
    }).join('');
  }

  function renderSvg(svg) {
    var payload = readPayload(svg);
    if (!payload || !document.createElementNS) return;
    var series = payload.series || {};
    var colors = payload.colors || {};
    var brands = orderedBrands(series);
    var max = 1;
    brands.forEach(function (brand) {
      (series[brand] || []).forEach(function (value) { max = Math.max(max, Number(value) || 0); });
    });

    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.appendChild(svgElement('rect', { width: '360', height: '180', fill: '#0f172a' }));
    [45, 90, 135].forEach(function (y) {
      svg.appendChild(svgElement('line', {
        x1: '0', y1: String(y), x2: '360', y2: String(y),
        stroke: '#1f2937', 'stroke-dasharray': '2 4',
      }));
    });
    var paths = svgElement('g', { 'stroke-width': '1.8', fill: 'none' });
    brands.forEach(function (brand) {
      var values = series[brand] || [];
      var lastIndex = Math.max(values.length - 1, 1);
      var points = values.map(function (value, index) {
        var x = (360 * index / lastIndex).toFixed(2);
        var y = (160 - ((Number(value) || 0) / max * 140)).toFixed(2);
        return x + ',' + y;
      });
      if (points.length) {
        paths.appendChild(svgElement('polyline', {
          stroke: colors[brand] || '#9ca3af', points: points.join(' '),
        }));
      }
    });
    svg.appendChild(paths);
    renderSvgLegend(svg, brands, colors);
  }

  function renderOne(chartElement) {
    if (isSvgChart(chartElement)) {
      renderSvg(chartElement);
      return;
    }
    var canvas = chartElement;
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
        // U4: hover-isolate removed (plan § Net D — `hoveredBrandIndex` must be
        // absent or inert). Callback kept as a no-op so Chart.js does not error.
        onHover: function (event, activeElements, c) {
          // no-op: all brand lines stay visible on hover
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
    var charts = document.querySelectorAll('canvas.home-chart, svg.home-chart');
    for (var i = 0; i < charts.length; i++) {
      try { renderOne(charts[i]); }
      catch (e) { console.warn('pw-chart: render failed', e); }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderAll);
  } else {
    renderAll();
  }

  // Re-bind on htmx swaps of the root chart region, plus the legacy
  // /internal and single-brand regions that still use IDs.
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (!evt.target) return;
    if (isHomeChartRegion(evt.target) || evt.target.id === 'home-chart' || evt.target.id === 'brand-chart') {
      var chart = chartIn(evt.target);
      if (chart) {
        try { renderOne(chart); }
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
  // Scoped to the multi-brand page: this module owns the root chart's
  // mockup-safe data marker (or /internal's legacy `#home-chart` fallback).
  // The single-brand page (`/brand_home.html.j2`) loads pw-brand-chart.js
  // for `#brand-chart`, so we no-op there.
  function refetchChartWithFilters() {
    var region = getHomeChartRegion();
    if (!region) return;
    var filters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
    var renderer = region.id === 'home-chart' ? '&renderer=canvas' : '';
    var url = '/chart.html?filters=' + encodeURIComponent(JSON.stringify(filters)) + renderer;
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        region.innerHTML = html;
        var chart = chartIn(region);
        if (chart) {
          try { renderOne(chart); }
          catch (e) { console.warn('pw-chart: post-filter render failed', e); }
        }
      })
      .catch(function (e) { console.warn('pw-chart: filter refetch failed', e); });
  }
  document.addEventListener('pw:filter-change', refetchChartWithFilters);
})();
