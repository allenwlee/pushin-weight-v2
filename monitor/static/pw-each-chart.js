(function () {
  'use strict';

  var root = document.querySelector('[data-pw-each-chart]');
  if (!root) return;
  var canvas = root.querySelector('[data-each-canvas]');
  var panel = root.querySelector('.each-chart-panel');
  var face = root.querySelector('.each-chart-face');
  var legend = root.querySelector('[data-each-legend]');
  var status = root.querySelector('[data-each-status]');
  var tabs = Array.prototype.slice.call(root.querySelectorAll('[data-each-tab]'));
  var modes = Array.prototype.slice.call(root.querySelectorAll('[data-each-mode]'));
  var pulses = Array.prototype.slice.call(document.querySelectorAll('[data-pw-pulse-entry]'));
  var initial = document.getElementById('each-initial-chart');
  var payload = initial ? JSON.parse(initial.textContent) : null;
  var selected = payload && payload.brand || '';
  var activeTab = payload && payload.tab || (tabs[0] && tabs[0].dataset.eachTab) || 'sentiment';
  var mode = (modes.find(function (input) { return input.checked; }) || {}).value || 'percent';
  var windowDays = Number(document.body.dataset.pwWindow || 7);
  var locale = document.body.dataset.pwLocale || 'en';
  var generation = 0;
  var controller = null;
  var chart = null;
  var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  window.pwFilter = {
    get: function () {
      return { brands: selected ? [selected] : [], window: windowDays, unsanctioned: 'any' };
    }
  };

  function setStatus(message) {
    status.textContent = message || '';
    status.hidden = !message;
  }

  function setSelected(brand) {
    selected = brand;
    if (chart) { chart.destroy(); chart = null; }
    legend.replaceChildren();
    root.dataset.selectedBrand = '';
    pulses.forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.dataset.pwPulseEntry === brand));
    });
    var feed = document.querySelector('[data-pw-feed]');
    if (feed) feed.dataset.pwBrandScope = brand;
    document.dispatchEvent(new CustomEvent('pw:filter-change', {
      detail: { filters: window.pwFilter.get() }
    }));
  }

  function setTab(tab) {
    activeTab = tab;
    tabs.forEach(function (button) {
      var active = button.dataset.eachTab === tab;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
    });
  }

  function chartLabel(value, granularity) {
    if (granularity === 'minute') {
      return new Date(value).toLocaleTimeString(locale.replace('_', '-'), { hour: 'numeric', minute: '2-digit' });
    }
    return value.slice(5);
  }

  function render(next) {
    payload = next;
    root.dataset.selectedBrand = next.brand;
    root.dataset.countingUnit = next.counting_unit;
    root.dataset.pwChartGranularity = next.granularity;
    var unitText = next.counting_unit === 'posts' ?
      (/^zh/.test(locale) ? '帖子' : locale === 'ja' ? '投稿' : 'posts') :
      (/^zh/.test(locale) ? '标签分配' : locale === 'ja' ? 'ラベル割当' : 'label assignments');
    canvas.setAttribute('aria-label', next.brand + ': ' + unitText + (mode === 'percent' ? ', % of total' : ', by volume'));
    var localeLabels = next.days.map(function (day) { return chartLabel(day, next.granularity); });
    var stackTotals = next.days.map(function (_, index) {
      return next.entries.reduce(function (sum, entry) {
        return sum + Number((next.series[entry.key] || [])[index] || 0);
      }, 0);
    });
    var datasets = next.entries.map(function (entry) {
      return {
        label: entry.label,
        data: (next.series[entry.key] || []).map(function (count, index) {
          return mode === 'percent' ? (stackTotals[index] ? count * 100 / stackTotals[index] : null) : count;
        }),
        borderColor: entry.color,
        backgroundColor: entry.color + 'a8',
        borderWidth: 1.4,
        fill: 'stack',
        pointRadius: 0,
        pointHitRadius: 8,
        tension: 0.22,
        stack: 'classification'
      };
    });
    legend.replaceChildren();
    next.entries.forEach(function (entry) {
      var item = document.createElement('span');
      var dot = document.createElement('i');
      dot.style.backgroundColor = entry.color;
      item.appendChild(dot);
      item.appendChild(document.createTextNode(entry.label));
      legend.appendChild(item);
    });
    if (chart) chart.destroy();
    if (!window.Chart) {
      setStatus(root.dataset.chartError);
      return;
    }
    chart = new window.Chart(canvas, {
      type: 'line',
      data: { labels: localeLabels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (item) {
                var entry = next.entries[item.datasetIndex];
                var count = next.series[entry.key][item.dataIndex];
                return entry.label + ': ' + count + (mode === 'percent' ? ' (' + item.parsed.y.toFixed(1) + '%)' : '');
              },
              footer: function (items) {
                var total = items.length ? stackTotals[items[0].dataIndex] : 0;
                var words = /^zh/.test(locale) ? ['帖子', '标签分配'] :
                  locale === 'ja' ? ['投稿', 'ラベル割当'] : ['posts', 'label assignments'];
                var noun = words[next.counting_unit === 'posts' ? 0 : 1];
                return total + ' ' + noun;
              }
            }
          }
        },
        scales: {
          x: {
            stacked: true,
            ticks: { color: '#8f9bb2', maxTicksLimit: 8, maxRotation: 0 },
            grid: { color: 'rgba(141,156,181,.08)' }
          },
          y: {
            stacked: true,
            beginAtZero: true,
            max: mode === 'percent' ? 100 : undefined,
            ticks: {
              color: '#8f9bb2', precision: 0,
              callback: mode === 'percent' ? function (value) { return value + '%'; } : undefined
            },
            grid: { color: 'rgba(141,156,181,.14)' }
          }
        }
      }
    });
    setStatus(next.totals.some(function (count) { return count > 0; }) ? '' : root.dataset.chartEmpty);
  }

  function turnTo(next, ticket) {
    if (prefersReducedMotion.matches) {
      render(next);
      return;
    }
    face.classList.remove('is-turning-in');
    face.classList.add('is-turning-out');
    window.setTimeout(function () {
      if (ticket !== generation) return;
      face.classList.remove('is-turning-out');
      render(next);
      face.classList.add('is-turning-in');
      window.setTimeout(function () { face.classList.remove('is-turning-in'); }, 230);
    }, 115);
  }

  function chartUrl() {
    var params = new URLSearchParams({
      brand: selected,
      tab: activeTab,
      window: String(windowDays),
      locale: locale,
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    });
    return root.dataset.chartUrl + '?' + params.toString();
  }

  function refresh(turn) {
    var ticket = ++generation;
    if (controller) controller.abort();
    face.classList.remove('is-turning-out', 'is-turning-in');
    controller = new AbortController();
    setStatus('');
    panel.setAttribute('aria-busy', 'true');
    fetch(chartUrl(), { credentials: 'same-origin', signal: controller.signal })
      .then(function (response) { if (!response.ok) throw new Error('chart request'); return response.json(); })
      .then(function (next) {
        if (ticket !== generation) return;
        if (next.brand !== selected || next.tab !== activeTab) throw new Error('stale chart');
        if (turn) turnTo(next, ticket); else render(next);
      })
      .catch(function (error) {
        if (ticket === generation && error.name !== 'AbortError') {
          if (chart) { chart.destroy(); chart = null; }
          legend.replaceChildren();
          setStatus(root.dataset.chartError);
        }
      })
      .finally(function () {
        if (ticket === generation) panel.removeAttribute('aria-busy');
      });
  }

  function refreshHeadline(brand) {
    var ticket = generation;
    var url = new URL(window.location.href);
    url.searchParams.set('brand', brand);
    fetch(url.toString(), { credentials: 'same-origin' })
      .then(function (response) { if (!response.ok) throw new Error('headline request'); return response.text(); })
      .then(function (html) {
        if (ticket !== generation || selected !== brand) return;
        var next = new DOMParser().parseFromString(html, 'text/html').querySelector('[data-pw-headline]');
        var current = document.querySelector('[data-pw-headline]');
        if (next && current) current.replaceWith(next);
      })
      .catch(function () {
        if (ticket === generation) {
          var current = document.querySelector('[data-pw-headline]');
          var items = current && current.querySelector('[data-pw-headline-items]');
          if (items) items.replaceChildren();
        }
      });
  }

  tabs.forEach(function (button, index) {
    button.addEventListener('click', function () {
      if (activeTab === button.dataset.eachTab) return;
      setTab(button.dataset.eachTab);
      var url = new URL(window.location.href);
      url.searchParams.set('tab', activeTab);
      window.history.replaceState(window.history.state, '', url);
      refresh(true);
    });
    button.addEventListener('keydown', function (event) {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      event.preventDefault();
      var nextIndex = (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      tabs[nextIndex].focus();
      tabs[nextIndex].click();
    });
  });

  modes.forEach(function (input) {
    input.addEventListener('change', function () {
      if (!input.checked || mode === input.value) return;
      mode = input.value;
      if (payload) render(payload);
    });
  });

  pulses.forEach(function (button) {
    button.addEventListener('click', function () {
      var brand = button.dataset.pwPulseEntry;
      if (!brand || brand === selected) return;
      setSelected(brand);
      var url = new URL(window.location.href);
      url.searchParams.set('brand', brand);
      window.history.pushState({ brand: brand }, '', url);
      refresh(false);
      refreshHeadline(brand);
    });
  });
  document.addEventListener('click', function (event) {
    var button = event.target.closest && event.target.closest('[data-pw-headline-detail]');
    if (!button) return;
    var article = button.closest('[data-pw-headline-item]');
    var detail = article && article.querySelector('[data-pw-headline-item-secondary]');
    if (!detail) return;
    var expanded = button.getAttribute('aria-expanded') !== 'true';
    button.setAttribute('aria-expanded', String(expanded));
    detail.hidden = !expanded;
    var labels = locale === 'ja' ? ['詳細', '閉じる'] :
      /^zh/.test(locale) ? ['更多', '收起'] : ['more', 'less'];
    button.textContent = labels[expanded ? 1 : 0];
  });
  window.addEventListener('popstate', function () {
    var requested = new URL(window.location.href).searchParams.get('brand');
    var brand = pulses.some(function (button) { return button.dataset.pwPulseEntry === requested; })
      ? requested : (pulses[0] && pulses[0].dataset.pwPulseEntry);
    if (!brand || brand === selected) return;
    setSelected(brand);
    refresh(false);
    refreshHeadline(brand);
  });

  setTab(activeTab);
  if (payload) render(payload);
  if (payload && windowDays > 1) {
    var localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    if (payload.bucket_timezone !== localTimezone) refresh(false);
  }
})();
