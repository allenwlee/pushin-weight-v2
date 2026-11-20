(function () {
  'use strict';

  var root = document.querySelector('[data-pw-each-chart]');
  if (!root) return;
  var canvas = root.querySelector('[data-each-canvas]');
  var panel = root.querySelector('.each-chart-panel');
  var face = root.querySelector('.each-chart-face');
  var legend = root.querySelector('[data-each-legend]');
  var status = root.querySelector('[data-each-status]');
  var bucketNote = root.querySelector('[data-each-bucket-note]');
  var tabs = Array.prototype.slice.call(root.querySelectorAll('[data-each-tab]'));
  var modes = Array.prototype.slice.call(root.querySelectorAll('[data-each-mode]'));
  var pulses = Array.prototype.slice.call(document.querySelectorAll('[data-pw-pulse-entry]'));
  var initial = document.getElementById('each-initial-chart');
  var payload = initial ? JSON.parse(initial.textContent) : null;
  var selected = payload && payload.brand || root.dataset.selectedBrand || '';
  var activeTab = payload && payload.tab || root.dataset.selectedTab || (tabs[0] && tabs[0].dataset.eachTab) || 'sentiment';
  var mode = (modes.find(function (input) { return input.checked; }) || {}).value || 'percent';
  var windowDays = Number(document.body.dataset.pwWindow || 7);
  var locale = document.body.dataset.pwLocale || 'en';
  var generation = 0;
  var controller = null;
  var headlineController = null;
  var headlineGeneration = 0;
  var committedHeadline = selected;
  var chart = null;
  var chartIdentity = '';
  var legendVersion = 0;
  var pinnedCategory = null;
  var hoveredCategory = null;
  var focusedCategory = null;
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

  function chartLabel(value, granularity, yearly) {
    var time = window.pwTime;
    if (granularity === 'minute') {
      return time
        ? time.clockText(new Date(value), locale)
        : new Date(value).toLocaleTimeString(locale.replace('_', '-'), { hour: 'numeric', minute: '2-digit' });
    }
    return time ? time.dateLabel(value, locale, yearly) : value.slice(5);
  }

  // Time axis built from the payload's dates: one-day ticks end at the last
  // harvested bucket and step back whole hours; date ticks end on the latest day.
  function timeAxis(days, granularity, bucketEnds) {
    var time = window.pwTime;
    var built = [];
    var yearly = days.length > 90;
    return {
      stacked: true,
      afterBuildTicks: function (axis) {
        if (!time) return;
        if (granularity === 'minute') {
          built = time.oneDayTicks(days, axis.width, 8);
          if (bucketEnds) {
            built = built.map(function (tick) {
              return { value: tick.value, instant: Date.parse(bucketEnds[tick.value]) };
            });
          }
          axis.ticks = built.map(function (tick) { return { value: tick.value }; });
        } else {
          var indices = time.dateTickIndices(days);
          var limit = Math.max(2, Math.floor(axis.width / 62));
          if (indices.length > limit) {
            var latest = indices[indices.length - 1];
            var stride = Math.ceil((indices.length - 1) / (limit - 1));
            indices = indices.filter(function (value, index) { return index % stride === 0 && value !== latest; });
            indices.push(latest);
          }
          axis.ticks = indices.map(function (value) { return { value: value }; });
        }
      },
      ticks: {
        color: '#687589',
        autoSkip: !time,
        maxTicksLimit: time ? undefined : 8,
        maxRotation: 0,
        callback: function (value, index) {
          if (!time) return this.getLabelForValue(value);
          if (granularity === 'minute') {
            return built[index] ? time.clockText(new Date(built[index].instant), locale) : '';
          }
          return days[value] ? time.dateLabel(days[value], locale, yearly) : '';
        }
      },
      grid: { display: false, color: '#eef1f7' },
      border: { color: '#e6eaf1' }
    };
  }

  function categoryColor(entry) {
    var colors = {
      '__unclassified__': '#8290a7', undetected: '#8290a7',
      neutral: '#25334b', other: '#25334b',
      '__no_audience_topic__': '#25334b', '__no_product_signal__': '#25334b',
      mixed: '#7c59f5', negative: '#f32e02', positive: '#0089f4'
    };
    return colors[entry.key] || entry.color;
  }

  function rgba(color, alpha) {
    var hex = color.slice(1);
    return 'rgba(' + parseInt(hex.slice(0, 2), 16) + ',' +
      parseInt(hex.slice(2, 4), 16) + ',' + parseInt(hex.slice(4, 6), 16) + ',' + alpha + ')';
  }

  function activeCategory() {
    return hoveredCategory || focusedCategory || pinnedCategory;
  }

  function categoryStyle(dataset) {
    var active = activeCategory();
    var selectedCategory = active === dataset.categoryKey;
    var muted = active !== null && !selectedCategory;
    dataset.backgroundColor = rgba(dataset.categoryColor, muted ? .055 : selectedCategory ? .48 : .34);
    dataset.borderColor = muted ? rgba(dataset.categoryColor, .17) : dataset.categoryColor;
    dataset.borderWidth = selectedCategory ? 2.7 : 2;
  }

  function updateEmphasis() {
    if (!chart) return;
    chart.data.datasets.forEach(categoryStyle);
    Array.prototype.forEach.call(legend.children, function (button) {
      button.setAttribute('aria-pressed', String(button.dataset.eachCategory === pinnedCategory));
      button.dataset.emphasized = String(button.dataset.eachCategory === activeCategory());
    });
    chart.update('none');
  }

  function placeLegend(instance) {
    if (!instance.chartArea) return;
    var buttons = Array.prototype.slice.call(legend.children);
    var top = instance.chartArea.top;
    var bottom = instance.chartArea.bottom;
    buttons.forEach(function (button, index) {
      button.style.top = (buttons.length === 1 ? (top + bottom) / 2 :
        top + index * (bottom - top) / (buttons.length - 1)) + 'px';
    });
  }

  function buildLegend(next) {
    var version = ++legendVersion;
    legend.replaceChildren();
    next.entries.slice().reverse().forEach(function (entry) {
      var button = document.createElement('button');
      var swatch = document.createElement('i');
      var label = document.createElement('span');
      button.type = 'button';
      button.dataset.eachCategory = entry.key;
      button.style.setProperty('--each-category-color', categoryColor(entry));
      button.setAttribute('aria-pressed', String(entry.key === pinnedCategory));
      button.dataset.emphasized = String(entry.key === activeCategory());
      swatch.setAttribute('aria-hidden', 'true');
      label.textContent = entry.label;
      button.appendChild(swatch);
      button.appendChild(label);
      function on(event, callback) {
        button.addEventListener(event, function () {
          if (version !== legendVersion) return;
          callback();
          updateEmphasis();
        });
      }
      on('pointerenter', function () { hoveredCategory = entry.key; });
      on('pointerleave', function () { hoveredCategory = null; });
      on('focus', function () { focusedCategory = entry.key; });
      on('blur', function () { focusedCategory = null; });
      on('click', function () {
        pinnedCategory = pinnedCategory === entry.key ? null : entry.key;
        hoveredCategory = null;
        focusedCategory = null;
      });
      legend.appendChild(button);
    });
  }

  function tabLabel(tab) {
    var button = tabs.find(function (entry) { return entry.dataset.eachTab === tab; });
    return button ? button.textContent.trim() : '';
  }

  function displayPayload(next) {
    if (next.window_days !== 1 || next.granularity !== 'minute' || next.days.length <= 12) return next;
    // The API retains five-minute counts. Sum before calculating percentages:
    // averaging percentages would give a one-post bucket the same weight as a busy one.
    var days = [], ends = [], totals = [];
    var series = {};
    var keys = Object.keys(next.series);
    keys.forEach(function (key) { series[key] = []; });
    for (var start = 0; start < next.days.length; start += 12) {
      var stop = Math.min(start + 12, next.days.length);
      days.push(next.days[start]);
      ends.push(new Date(Date.parse(next.days[stop - 1]) + 300000).toISOString());
      totals.push(next.totals.slice(start, stop).reduce(function (sum, value) { return sum + value; }, 0));
      keys.forEach(function (key) {
        series[key].push(next.series[key].slice(start, stop).reduce(function (sum, value) { return sum + value; }, 0));
      });
    }
    return Object.assign({}, next, { days: days, series: series, totals: totals, bucket_ends: ends });
  }

  function render(next) {
    var identity = [next.brand, next.tab, next.window_days, locale, next.bucket_timezone].join('|');
    if (identity !== chartIdentity || !next.entries.some(function (entry) { return entry.key === pinnedCategory; })) {
      pinnedCategory = null;
    }
    hoveredCategory = null;
    focusedCategory = null;
    chartIdentity = identity;
    payload = next;
    next = displayPayload(next);
    if (bucketNote) bucketNote.hidden = !next.bucket_ends;
    root.dataset.selectedBrand = next.brand;
    root.dataset.committedTab = next.tab;
    root.dataset.countingUnit = next.counting_unit;
    root.dataset.pwChartGranularity = next.granularity;
    var unitText = next.counting_unit === 'posts' ?
      (/^zh/.test(locale) ? '帖子' : locale === 'ja' ? '投稿' : 'posts') :
      (/^zh/.test(locale) ? '标签分配' : locale === 'ja' ? 'ラベル割当' : 'label assignments');
    canvas.setAttribute('aria-label', next.brand + ': ' + [tabLabel(next.tab), unitText].filter(Boolean).join(', ') + (mode === 'percent' ? ', % of total' : ', by volume') + (bucketNote && !bucketNote.hidden ? ', ' + bucketNote.textContent.trim() : ''));
    var localeLabels = next.days.map(function (day) {
      return chartLabel(day, next.granularity, next.days.length > 90);
    });
    var stackTotals = next.days.map(function (_, index) {
      return next.entries.reduce(function (sum, entry) {
        return sum + Number((next.series[entry.key] || [])[index] || 0);
      }, 0);
    });
    var datasets = next.entries.map(function (entry) {
      var dataset = {
        categoryKey: entry.key,
        categoryColor: categoryColor(entry),
        label: entry.label,
        data: (next.series[entry.key] || []).map(function (count, index) {
          return mode === 'percent' ? (stackTotals[index] ? count * 100 / stackTotals[index] : null) : count;
        }),
        fill: 'stack',
        pointRadius: 0,
        pointHoverRadius: 0,
        pointHitRadius: 8,
        cubicInterpolationMode: 'monotone',
        stack: 'classification'
      };
      categoryStyle(dataset);
      return dataset;
    });
    buildLegend(next);
    if (chart) chart.destroy();
    if (!window.Chart) {
      setStatus(root.dataset.chartError);
      return;
    }
    chart = new window.Chart(canvas, {
      type: 'line',
      data: { labels: localeLabels, datasets: datasets },
      plugins: [{ id: 'eachLeftLegend', afterLayout: placeLegend }],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            itemSort: function (left, right) { return right.datasetIndex - left.datasetIndex; },
            callbacks: {
              title: next.bucket_ends ? function (items) {
                if (!items.length) return '';
                var index = items[0].dataIndex;
                return localeLabels[index] + ' – ' + chartLabel(next.bucket_ends[index], 'minute', false);
              } : undefined,
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
          x: timeAxis(next.days, next.granularity, next.bucket_ends),
          y: {
            stacked: true,
            position: 'right',
            beginAtZero: true,
            max: mode === 'percent' ? 100 : undefined,
            ticks: {
              color: '#687589', precision: 0,
              callback: mode === 'percent' ? function (value) { return value + '%'; } : undefined
            },
            grid: { color: '#dfe4ec' },
            border: { display: false, dash: [1, 3] }
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

  function previousLabel(data) {
    if (!data) return '';
    var button = pulses.find(function (entry) { return entry.dataset.pwPulseEntry === data.brand; });
    var name = button && button.querySelector('.pulse-chip-name');
    var identity = [name ? name.textContent : data.brand, tabLabel(data.tab), data.window_days + 'd'].filter(Boolean).join(', ');
    return /^zh/.test(locale) ? '显示上次结果（' + identity + '）' :
      locale === 'ja' ? '前回の結果を表示（' + identity + '）' : 'Showing previous result (' + identity + ')';
  }

  function refresh(turn) {
    var ticket = ++generation;
    if (controller) controller.abort();
    face.classList.remove('is-turning-out', 'is-turning-in');
    var requestController = new AbortController();
    controller = requestController;
    var expired = false;
    var timer = window.setTimeout(function () { expired = true; requestController.abort(); }, 18000);
    setStatus((root.dataset.chartLoading || 'Loading chart…') + (payload ? ' ' + previousLabel(payload) : ''));
    panel.setAttribute('aria-busy', 'true');
    fetch(chartUrl(), { credentials: 'same-origin', signal: requestController.signal })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            var error = new Error('chart request');
            error.chartTimeout = body.error === 'chart_timeout';
            throw error;
          }
          return body;
        });
      })
      .then(function (next) {
        if (ticket !== generation || expired) return;
        if (next.brand !== selected || next.tab !== activeTab || Number(next.window_days) !== windowDays) throw new Error('stale chart');
        if (turn) turnTo(next, ticket); else render(next);
      })
      .catch(function (error) {
        if (ticket === generation && (expired || error.name !== 'AbortError')) {
          setStatus((expired || error.chartTimeout ? root.dataset.chartTimeout : root.dataset.chartError) || 'Chart refresh failed');
          if (payload) setStatus(status.textContent + ' ' + previousLabel(payload));
        }
      })
      .finally(function () {
        window.clearTimeout(timer);
        if (ticket === generation) panel.removeAttribute('aria-busy');
      });
  }

  function headlineStatus(message) {
    var current = document.querySelector('[data-pw-headline]');
    var notice = current && current.querySelector('[data-pw-headline-status]');
    if (notice) { notice.textContent = message; notice.hidden = !message; }
  }

  function refreshHeadline(brand) {
    var ticket = ++headlineGeneration;
    if (headlineController) headlineController.abort();
    var requestController = new AbortController();
    headlineController = requestController;
    var expired = false;
    var timer = window.setTimeout(function () { expired = true; requestController.abort(); }, 4000);
    var url = new URL(root.dataset.headlineUrl || '/api/v2/dashboard/each/headline/', window.location.href);
    url.searchParams.set('brand', brand);
    url.searchParams.set('window', String(windowDays));
    url.searchParams.set('locale', locale);
    var oldIdentity = committedHeadline ? previousLabel({ brand: committedHeadline, window_days: windowDays }) : '';
    headlineStatus((root.dataset.chartLoading || 'Loading…') + ' ' + oldIdentity);
    fetch(url.toString(), { credentials: 'same-origin', signal: requestController.signal })
      .then(function (response) { if (!response.ok) throw new Error('headline request'); return response.json(); })
      .then(function (next) {
        if (ticket !== headlineGeneration || selected !== brand || expired) return;
        if (next.brand !== brand || Number(next.window_days) !== windowDays || next.locale !== locale) throw new Error('stale headline');
        var fragment = new DOMParser().parseFromString(next.html, 'text/html').querySelector('[data-pw-headline]');
        var current = document.querySelector('[data-pw-headline]');
        if (!fragment || !current) throw new Error('missing headline');
        current.replaceWith(fragment);
        committedHeadline = brand;
      })
      .catch(function (error) {
        if (ticket === headlineGeneration && (expired || error.name !== 'AbortError')) {
          headlineStatus((root.dataset.headlineError || 'Headline refresh failed') + ' ' + oldIdentity);
        }
      })
      .finally(function () { window.clearTimeout(timer); });
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
      if (payload) {
        var currentStatus = status.textContent;
        var statusHidden = status.hidden;
        render(payload);
        status.textContent = currentStatus;
        status.hidden = statusHidden;
      }
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
  else if (selected) refresh(false);
  if (payload && windowDays > 1) {
    var localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    if (payload.bucket_timezone !== localTimezone) refresh(false);
  }
})();
