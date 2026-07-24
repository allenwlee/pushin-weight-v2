// {{AGENT_ATTRIBUTION}}
// x_monitor/static/pw-brand-chart.js
// Pushin' Weight (走个量) single-brand stacked-area chart with 6 tabs
// (U7 of feat/pushin-weight-home-pages, 2026-07-06).
//
// - Builds 6 stacked-area datasets, all `hidden: true` except the
//   active tab. Tab switch = toggle visibility + `chart.update('none')`
//   (KTD6).
// - Reads `data-brand-chart` JSON attribute. Tab order is fixed:
//   post_type, discourse, account_roles, us_nationalism, cn_nationalism,
//   unsanctioned.
// - On tab click, emits `pw:tab-change` and updates URL hash.

(function () {
  'use strict';

  var TABS = [
    'post_type', 'discourse', 'account_roles',
    'us_nationalism', 'cn_nationalism', 'unsanctioned',
  ];

  function colorForCategory(tab, cat) {
    var prefix = '';
    if (tab === 'post_type') prefix = '--pt-';
    else if (tab === 'discourse') prefix = '--bar-';
    else if (tab === 'account_roles') prefix = '--role-';
    else if (tab === 'us_nationalism' || tab === 'cn_nationalism') prefix = '--nat-';
    else if (tab === 'unsanctioned') {
      if (cat === 'flagged') {
        return getComputedStyle(document.documentElement)
          .getPropertyValue('--red').trim() || '#ef4444';
      }
      return getComputedStyle(document.documentElement)
        .getPropertyValue('--muted').trim() || '#8b949e';
    }
    var v = prefix + cat.replace(/-/g, '-');
    var c = getComputedStyle(document.documentElement).getPropertyValue(v).trim();
    return c || '#9ca3af';
  }

  function readPayload(canvas) {
    var raw = canvas.getAttribute('data-brand-chart') || '{}';
    try { return JSON.parse(raw); }
    catch (e) { return null; }
  }

  function renderOne(canvas) {
    var payload = readPayload(canvas);
    if (!payload) return;
    var days = payload.days || [];
    var granularity = payload.granularity || 'day';
    var tabDatasets = payload.tab_datasets || {};
    var activeTab = payload.tab || 'post_type';

    var prior = Chart.getChart(canvas);
    if (prior) prior.destroy();

    var datasets = [];
    TABS.forEach(function (tab) {
      var tabCats = tabDatasets[tab] || {};
      Object.keys(tabCats).forEach(function (cat) {
        var brandData = granularity === 'minute'
          ? tabCats[cat].map(function(v) { return v === 0 ? NaN : v; })
          : tabCats[cat];
        datasets.push({
          label: tab + ': ' + cat,
          data: brandData,
          type: 'line',
          borderColor: 'transparent',
          backgroundColor: colorForCategory(tab, cat),
          borderWidth: 0,
          pointRadius: granularity === 'minute' ? 1.5 : 0,
          tension: granularity === 'minute' ? 0.3 : 0.0,
          fill: datasets.length === 0 ? 'origin' : '-1',
          hidden: tab !== activeTab,
          _tab: tab,
          _category: cat,
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
            stacked: true,
            title: {
              display: true,
              text: granularity === 'minute' ? 'posts / 5min' : 'posts / day',
            },
            ticks: { precision: 0 },
          },
        },
      },
    });
    return chart;
  }

  function renderAll() {
    var canvases = document.querySelectorAll('canvas.home-brand-chart');
    for (var i = 0; i < canvases.length; i++) {
      try { renderOne(canvases[i]); }
      catch (e) { console.warn('pw-brand-chart: render failed', e); }
    }
  }

  function wireTabs() {
    var strip = document.getElementById('brand-tabs');
    if (!strip) return;
    var tabs = strip.querySelectorAll('.pw-tab');
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var tabName = tab.getAttribute('data-pw-tab');
        tabs.forEach(function (t) { t.classList.remove('is-active'); });
        tab.classList.add('is-active');
        var canvas = document.querySelector('canvas.home-brand-chart');
        if (!canvas) return;
        var chart = Chart.getChart(canvas);
        if (chart) {
          chart.data.datasets.forEach(function (ds) {
            ds.hidden = ds._tab !== tabName;
          });
          chart.update('none');
        }
        document.dispatchEvent(new CustomEvent('pw:tab-change', {
          detail: { tab: tabName },
        }));
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      renderAll();
      wireTabs();
    });
  } else {
    renderAll();
    wireTabs();
  }

  document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (!evt.target) return;
    if (evt.target.id === 'brand-chart') {
      var canvas = evt.target.querySelector('canvas.home-brand-chart');
      if (canvas) {
        try { renderOne(canvas); }
        catch (e) { console.warn('pw-brand-chart: post-swap render failed', e); }
      }
    }
  });

  // U3 (2026-07-16): react to control-panel filter changes on the
  // single-brand page too. Brand checkbox is locked, but the other 6
  // filter groups still apply — re-fetch the chart fragment with the
  // current filters, swap the region, re-render.
  //
  // The brand-chart route requires `?brand=<id>` (no path segment).
  // Read it from the body's `data-pw-brand` attribute (set by
  // `brand_home.html.j2`).
  function refetchBrandChartWithFilters() {
    var region = document.getElementById('brand-chart');
    if (!region) return;
    var brandId = document.body && document.body.getAttribute('data-pw-brand');
    if (!brandId) return;
    var filters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
    var url = '/brand-chart/' + encodeURIComponent(brandId) + '.html?filters=' + encodeURIComponent(JSON.stringify(filters));
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        region.innerHTML = html;
        var canvas = region.querySelector('canvas.home-brand-chart');
        if (canvas) {
          try { renderOne(canvas); }
          catch (e) { console.warn('pw-brand-chart: post-filter render failed', e); }
        }
      })
      .catch(function (e) { console.warn('pw-brand-chart: filter refetch failed', e); });
  }
  document.addEventListener('pw:filter-change', refetchBrandChartWithFilters);
})();
