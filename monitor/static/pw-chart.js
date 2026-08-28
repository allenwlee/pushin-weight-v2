// Shared multi-brand home Chart.js and pulse lifecycle.

(function () {
  'use strict';

  var HOME_CHART_REGION_SELECTOR = '.home-chart-wrap[data-pw-chart]';
  var REFRESH_INTERVAL_MS = 60000;
  var REQUEST_TIMEOUT_MS = 12000;
  var generation = 0;
  var activeController = null;
  var fallbackComparisonHourFormatter = null;

  var BRAND_NAMES = {
    moonshot_kimi: 'Kimi',
    deepseek: 'DeepSeek',
    minimax: 'MiniMax',
    qwen: 'Qwen',
    ernie: 'ERNIE',
  };

  var TIMEZONE_ROW_LABEL_PLUGIN = {
    id: 'pwTimezoneRowLabels',
    afterDraw: function (chart, _args, options) {
      if (!options || options.display !== true || !chart.chartArea) return;
      var ctx = chart.ctx;
      ['x', 'xComparison'].forEach(function (scaleKey) {
        var scale = chart.scales[scaleKey];
        if (!scale) return;
        var scaleOptions = scale.options || {};
        var title = scaleOptions.title || {};
        var ticks = scaleOptions.ticks || {};
        var grid = scaleOptions.grid || {};
        if (!title.text) return;
        var font = ticks.font || {};
        var size = Number(font.size) || 9;
        var weight = font.weight || 400;
        var family = (Chart.defaults.font && Chart.defaults.font.family) || 'sans-serif';
        var tickLength = grid.display === false || grid.drawTicks === false
          ? 0
          : Number(grid.tickLength) || 0;
        var padding = Number(ticks.padding) || 0;

        ctx.save();
        ctx.fillStyle = ticks.color || title.color || Chart.defaults.color;
        ctx.font = weight + ' ' + size + 'px ' + family;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.fillText(
          String(title.text),
          chart.chartArea.left - 4,
          scale.top + tickLength + padding + size / 2
        );
        ctx.restore();
      });
    },
  };

  function getHomeChartRegion() {
    return document.querySelector(HOME_CHART_REGION_SELECTOR) ||
      document.getElementById('home-chart');
  }

  function isPublicHomeRegion(region) {
    return Boolean(region && region.matches && region.matches(HOME_CHART_REGION_SELECTOR));
  }

  function chartIn(region) {
    return region ? region.querySelector('canvas.home-chart') : null;
  }

  function readPayload(canvas) {
    if (!canvas) return null;
    try { return JSON.parse(canvas.getAttribute('data-home') || '{}'); }
    catch (error) { return null; }
  }

  function isObject(value) {
    return Boolean(value && typeof value === 'object' && !Array.isArray(value));
  }

  function validPayload(payload) {
    if (!isObject(payload) || !Array.isArray(payload.days) ||
        !isObject(payload.series) || !isObject(payload.totals) ||
        !isObject(payload.pulse) || !Array.isArray(payload.pulse.entries) ||
        !isObject(payload.trend_narrative) ||
        typeof payload.trend_narrative.state_label !== 'string' ||
        !isObject(payload.top_voices) || !Array.isArray(payload.top_voices.entries)) return false;
    var narrativeSchema = Number(payload.trend_narrative.schema_version);
    if (![1, 2, 3].includes(narrativeSchema)) return false;
    if (narrativeSchema === 3) {
      if (!validPerBrandNarrative(payload.trend_narrative)) return false;
    } else if (
      typeof payload.trend_narrative.body !== 'string' ||
      (payload.trend_narrative.body_prefix !== undefined &&
       typeof payload.trend_narrative.body_prefix !== 'string') ||
      (payload.trend_narrative.body_remainder !== undefined &&
       typeof payload.trend_narrative.body_remainder !== 'string')
    ) return false;
    if ([payload.pulse, payload.trend_narrative, payload.top_voices].some(function (projection) {
      return Number(payload.window_days) !== Number(projection.window_days) ||
        payload.computed_at !== projection.computed_at;
    })) return false;
    if (!payload.computed_at) return false;
    if (!payload.pulse.entries.every(function (entry) {
      return isObject(entry) && typeof entry.nickname === 'string';
    })) return false;
    if (!payload.top_voices.entries.every(function (entry) {
      return isObject(entry) && typeof entry.handle === 'string' &&
        Number.isFinite(Number(entry.voice_star));
    })) return false;
    if (payload.trend_narrative.primary_brand !== null &&
        payload.trend_narrative.primary_brand !== undefined &&
        (!isObject(payload.trend_narrative.primary_brand) ||
         typeof payload.trend_narrative.primary_brand.key !== 'string' ||
         typeof payload.trend_narrative.primary_brand.display_name !== 'string')) return false;
    var observations = payload.trend_narrative.observations;
    if (observations === undefined && Number(payload.trend_narrative.schema_version) === 1) {
      observations = [];
    }
    if (!Array.isArray(observations) || observations.length > 2 ||
        !observations.every(function (observation) {
          return typeof observation === 'string' && observation.trim().length > 0;
        })) return false;
    return Object.keys(payload.series).every(function (brand) {
      return Array.isArray(payload.series[brand]);
    });
  }

  function validPerBrandNarrative(narrative) {
    var states = [
      'available', 'stale', 'unavailable', 'no_content',
      'data_quality_unavailable', 'disabled'
    ];
    if (!Array.isArray(narrative.items) || narrative.items.length > 2 ||
        !isObject(narrative.selection)) return false;
    if (!narrative.items.every(function (item) {
      return isObject(item) && (item.id === null || typeof item.id === 'string') &&
        isObject(item.brand) && typeof item.brand.key === 'string' &&
        typeof item.brand.display_name === 'string' &&
        (item.brand.url === null || typeof item.brand.url === 'string') &&
        states.includes(item.state) && typeof item.state_label === 'string' &&
        typeof item.headline === 'string' && item.headline.trim().length > 0 &&
        typeof item.secondary === 'string' && item.secondary.trim().length > 0 &&
        (item.verified_at === null || typeof item.verified_at === 'string') &&
        (item.attempted_at === null || typeof item.attempted_at === 'string') &&
        isObject(item.freshness) &&
        (item.freshness.kind === null || ['verified', 'attempted'].includes(item.freshness.kind)) &&
        typeof item.freshness.relative === 'string' &&
        typeof item.freshness.absolute === 'string' &&
        (item.freshness.absolute_iso === null || typeof item.freshness.absolute_iso === 'string');
    })) return false;
    var selection = narrative.selection;
    return ['all', 'explicit'].includes(selection.mode) &&
      Number.isInteger(selection.requested_count) && selection.requested_count >= 0 &&
      Number.isInteger(selection.returned_count) &&
      selection.returned_count === narrative.items.length &&
      typeof selection.truncated === 'boolean' &&
      typeof selection.summary === 'string';
  }

  function colorVarFor(discourseKey) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue('--bar-' + discourseKey).trim() || '#9ca3af';
  }

  function fixedHourlyTicks(labels) {
    if (!Array.isArray(labels) || labels.length < 24) return [];
    var timestamps = labels.map(function (label) { return Date.parse(label); });
    if (timestamps.some(function (timestamp) { return !Number.isFinite(timestamp); })) return [];

    var firstHour = new Date(timestamps[0]);
    firstHour.setMinutes(0, 0, 0);
    firstHour.setHours(firstHour.getHours() + 1);

    return Array.from({ length: 24 }, function (_, hourIndex) {
      var instant = firstHour.getTime() + hourIndex * 60 * 60 * 1000;
      var closestIndex = 0;
      var closestDistance = Infinity;
      timestamps.forEach(function (timestamp, labelIndex) {
        var distance = Math.abs(timestamp - instant);
        if (distance < closestDistance) {
          closestDistance = distance;
          closestIndex = labelIndex;
        }
      });
      return { instant: instant, value: closestIndex };
    });
  }

  function comparisonState() {
    if (window.__pwTz && typeof window.__pwTz.getComparison === 'function') {
      return window.__pwTz.getComparison();
    }
    return {
      key: 'california',
      timezone: 'America/Los_Angeles',
      shortLabel: 'CA',
      localLabel: isZhLocale(currentLocale(getHomeChartRegion())) ? '本地' : 'local',
    };
  }

  function comparisonHour(timestamp) {
    if (window.__pwTz && typeof window.__pwTz.comparisonHour === 'function') {
      return String(Number(window.__pwTz.comparisonHour(timestamp)) % 24);
    }
    if (!fallbackComparisonHourFormatter) {
      fallbackComparisonHourFormatter = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/Los_Angeles',
        hour: 'numeric',
        hourCycle: 'h23',
      });
    }
    var parts = fallbackComparisonHourFormatter.formatToParts(new Date(timestamp));
    var hour = parts.find(function (part) { return part.type === 'hour'; });
    return String(Number(hour ? hour.value : 0) % 24);
  }

  function colorWithAlpha(color, alpha) {
    var value = String(color || '').trim();
    var shortHex = value.match(/^#([0-9a-f])([0-9a-f])([0-9a-f])$/i);
    var longHex = value.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    if (shortHex) {
      return 'rgba(' + [shortHex[1], shortHex[2], shortHex[3]].map(function (part) {
        return parseInt(part + part, 16);
      }).join(', ') + ', ' + alpha + ')';
    }
    if (longHex) {
      return 'rgba(' + [longHex[1], longHex[2], longHex[3]].map(function (part) {
        return parseInt(part, 16);
      }).join(', ') + ', ' + alpha + ')';
    }
    return value;
  }

  function oneDayScales(days) {
    var hourlyTicks = fixedHourlyTicks(days);
    if (hourlyTicks.length !== 24) return null;
    var defaultColor = (Chart.defaults && Chart.defaults.color) || '#666666';
    var timezone = comparisonState();
    var activeMode = window.__pwTz && window.__pwTz.mode === 'ca' ? 'ca' : 'local';
    var localColor = activeMode === 'local'
      ? defaultColor
      : colorWithAlpha(defaultColor, 0.55);
    var comparisonColor = activeMode === 'ca'
      ? 'rgba(251, 191, 36, 1)'
      : 'rgba(251, 191, 36, 0.45)';

    function hourlyScale(weight, color, formatter, fontWeight, title, drawBorder) {
      return {
        type: 'category',
        position: 'bottom',
        weight: weight,
        labels: days,
        offset: false,
        afterBuildTicks: function (scale) {
          scale.ticks = hourlyTicks.map(function (tick) { return { value: tick.value }; });
        },
        ticks: {
          autoSkip: false,
          color: color,
          font: { size: 9, weight: fontWeight },
          maxRotation: 0,
          minRotation: 0,
          padding: drawBorder ? 2 : 0,
          callback: function (_value, index) {
            var hour = Number(formatter(hourlyTicks[index].instant)) % 24;
            return hour % 2 === 0 ? hour + ':00' : '';
          },
        },
        grid: {
          display: drawBorder,
          drawOnChartArea: false,
          drawTicks: drawBorder,
          tickLength: drawBorder ? 4 : 0,
          color: color,
        },
        border: { display: drawBorder, color: color, width: 1.5 },
        title: {
          display: false,
          text: title,
          align: 'start',
          color: color,
          font: { size: 9, weight: fontWeight },
          padding: { top: 0, bottom: 0 },
        },
      };
    }

    return {
      x: hourlyScale(0, localColor, function (timestamp) {
        return String(new Date(timestamp).getHours());
      }, 600, timezone.localLabel || 'local', true),
      xComparison: hourlyScale(
        1,
        comparisonColor,
        comparisonHour,
        activeMode === 'ca' ? 600 : 400,
        timezone.shortLabel || 'CA',
        false
      ),
    };
  }

  function chartScales(days, granularity) {
    var xScales = granularity === 'minute' ? oneDayScales(days) : null;
    return Object.assign(xScales || {
      x: {
        type: 'category',
        labels: days,
        ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 7 },
        grid: { display: false },
      },
    }, {
      y: {
        beginAtZero: true,
        title: {
          display: true,
          text: granularity === 'minute' ? 'posts / 5min' : 'posts / day',
          font: granularity === 'minute' ? { size: 9 } : undefined,
          padding: granularity === 'minute' ? 0 : undefined,
        },
        ticks: {
          precision: 0,
          font: granularity === 'minute' ? { size: 9 } : undefined,
          padding: granularity === 'minute' ? 2 : undefined,
        },
      },
    });
  }

  function renderOne(canvas) {
    var payload = readPayload(canvas);
    if (!validPayload(payload)) return null;
    var days = payload.days;
    var granularity = payload.granularity || 'day';
    var series = payload.series;
    var colors = payload.colors || {};
    var stacked = payload.stacked || {};
    var brandList = Object.keys(series);
    var region = getHomeChartRegion();
    if (region && chartIn(region) === canvas) {
      region.setAttribute('data-pw-chart-granularity', granularity);
    }
    var prior = Chart.getChart(canvas);
    if (prior) prior.destroy();

    var datasets = [];
    brandList.forEach(function (brand, brandIndex) {
      var stroke = colors[brand] || '#9ca3af';
      var totalData = granularity === 'minute'
        ? series[brand].map(function (value) { return value === 0 ? NaN : value; })
        : series[brand];
      datasets.push({
        label: brand + ' (total)',
        data: totalData,
        type: 'line',
        borderColor: stroke,
        backgroundColor: stroke,
        borderWidth: 2,
        pointRadius: granularity === 'minute' ? 1.5 : 0,
        tension: granularity === 'minute' ? 0.3 : 0,
        fill: false,
        _brandIndex: brandIndex,
        _isTotalLine: true,
      });
      Object.keys(stacked[brand] || {}).forEach(function (discourseKey) {
        var values = stacked[brand][discourseKey];
        datasets.push({
          label: brand + ' ' + discourseKey,
          data: granularity === 'minute'
            ? values.map(function (value) { return value === 0 ? NaN : value; })
            : values,
          type: 'line',
          borderColor: 'transparent',
          backgroundColor: colorVarFor(discourseKey),
          borderWidth: 0,
          pointRadius: granularity === 'minute' ? 1.5 : 0,
          tension: granularity === 'minute' ? 0.3 : 0,
          fill: '-1',
          hidden: true,
          _brandIndex: brandIndex,
          _isTotalLine: false,
        });
      });
    });

    return new Chart(canvas, {
      type: 'line',
      data: { labels: days, datasets: datasets },
      plugins: [TIMEZONE_ROW_LABEL_PLUGIN],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          pwTimezoneRowLabels: { display: granularity === 'minute' },
          tooltip: {
            enabled: true,
            mode: 'index',
            intersect: false,
            filter: function (item) { return item.dataset._isTotalLine === true; },
            callbacks: {
              label: function (context) {
                var value = context.parsed.y;
                return context.dataset.label + ': ' + value + (value === 1 ? ' post' : ' posts');
              },
            },
          },
        },
        scales: chartScales(days, granularity),
        onHover: function () {},
      },
    });
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderIcon(symbolId, className) {
    return window.pwIcon && typeof window.pwIcon.render === 'function'
      ? window.pwIcon.render(symbolId, className)
      : '';
  }

  function isZhLocale(locale) {
    return ['zh_cn', 'zh-cn', 'zh_hans', 'zh-hans'].indexOf(String(locale || '').toLowerCase()) !== -1;
  }

  function renderLegend(region, payload) {
    var legend = region.querySelector('[data-pw-chart-legend]');
    if (!legend && isPublicHomeRegion(region) && document.createElement && region.appendChild) {
      legend = document.createElement('div');
      legend.className = 'legend';
      legend.setAttribute('data-pw-chart-legend', '');
      region.appendChild(legend);
    }
    if (!legend) return;
    var seriesOrder = Object.keys(payload.series);
    var pulseOrder = payload.pulse.entries.map(function (entry) { return entry.nickname; })
      .filter(function (brand) { return seriesOrder.indexOf(brand) !== -1; });
    var brandOrder = pulseOrder.concat(seriesOrder.filter(function (brand) {
      return pulseOrder.indexOf(brand) === -1;
    }));
    legend.innerHTML = brandOrder.map(function (brand) {
      return '<span data-pw-chart-brand="' + escapeHtml(brand) + '"><i style="background:' +
        escapeHtml((payload.colors || {})[brand] || '#9ca3af') + '"></i>' +
        escapeHtml(BRAND_NAMES[brand] || brand) + '</span>';
    }).join('');
  }

  function renderPulse(region, pulse) {
    var bar = document.querySelector('[data-pw-pulse]');
    if (!bar) return;
    var zh = isZhLocale(region.getAttribute('data-pw-locale'));
    var newText = region.getAttribute('data-pw-pulse-new-text') || 'NEW';
    var filters = activeFilters();
    var selectedBrands = window.pwFilter && typeof window.pwFilter.getPulseBrands === 'function'
      ? window.pwFilter.getPulseBrands()
      : (Array.isArray(filters.brands) ? filters.brands : []);
    bar.innerHTML = pulse.entries.map(function (entry) {
      var name = zh
        ? (entry.display_name_zh_cn || entry.display_name || entry.nickname)
        : (entry.display_name_en || entry.display_name || entry.nickname);
      var trend;
      var accessibleTrend;
      if (entry.status === 'new') {
        trend = '<span class="delta new">' + escapeHtml(newText) + '</span>';
        accessibleTrend = newText;
      } else {
        var direction = ['up', 'down', 'flat'].indexOf(entry.direction) === -1 ? 'flat' : entry.direction;
        var magnitude = Math.abs(Number(entry.delta_percent) || 0);
        var trendSymbol = { up: 'icon-rise', down: 'icon-fall', flat: 'icon-flat' }[direction];
        trend = '<span class="delta ' + direction + '">' +
          renderIcon(trendSymbol, 'pulse-trend-icon') + magnitude + '%</span>';
        var localizedDirection = zh
          ? { up: '上升', down: '下降', flat: '持平' }[direction]
          : direction;
        accessibleTrend = localizedDirection + ' ' + magnitude + (zh ? '%' : ' percent');
      }
      return '<li><button type="button" class="pulse-chip" data-pw-pulse-entry="' +
        escapeHtml(entry.nickname) + '" aria-label="' + escapeHtml(name + ', ' + accessibleTrend) +
        '" aria-pressed="' + (selectedBrands.indexOf(entry.nickname) !== -1 ? 'true' : 'false') +
        '" style="--chip-color:' + escapeHtml(entry.accent_color || '#9ca3af') + '">' +
        '<span class="pulse-chip-name">' + escapeHtml(name) + '</span>' + trend + '</button></li>';
    }).join('');
    bar.setAttribute('data-pw-window', String(pulse.window_days));
    bar.setAttribute('data-pw-computed-at', pulse.computed_at);
  }

  function clearChildren(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function renderHeadline(narrative, topVoices) {
    var strip = document.querySelector('[data-pw-headline]');
    if (!strip) return;
    var perBrand = Number(narrative.schema_version) === 3;
    var items = strip.querySelector('[data-pw-headline-items]');
    var selection = strip.querySelector('[data-pw-headline-selection]');
    var legacy = strip.querySelector('[data-pw-headline-legacy]');
    if (perBrand) {
      renderPerBrandNarratives(items, narrative);
      if (items) items.hidden = false;
      if (legacy) legacy.hidden = true;
      if (selection) {
        selection.textContent = narrative.selection.summary || '';
        selection.hidden = !narrative.selection.summary;
      }
    } else {
      if (items) {
        clearChildren(items);
        items.hidden = true;
      }
      if (legacy) legacy.hidden = false;
      if (selection) {
        selection.textContent = '';
        selection.hidden = true;
      }
    }
    var prefix = strip.querySelector('[data-pw-headline-prefix]');
    var body = strip.querySelector('[data-pw-headline-body]');
    var state = strip.querySelector('[data-pw-headline-state]');
    var oldBrand = strip.querySelector('[data-pw-headline-brand]');
    if (!perBrand && narrative.primary_brand) {
      var desiredTag = narrative.primary_brand.url ? 'A' : 'SPAN';
      var brand = oldBrand && oldBrand.tagName === desiredTag
        ? oldBrand
        : document.createElement(desiredTag.toLowerCase());
      brand.className = 'brand';
      brand.setAttribute('data-pw-headline-brand', '');
      brand.textContent = narrative.primary_brand.display_name || narrative.primary_brand.key;
      if (narrative.primary_brand.url) brand.setAttribute('href', narrative.primary_brand.url);
      if (brand !== oldBrand && body && body.parentNode) {
        if (oldBrand && oldBrand.parentNode) oldBrand.parentNode.removeChild(oldBrand);
        body.parentNode.insertBefore(brand, body);
      }
    } else if (!perBrand && oldBrand && oldBrand.parentNode) {
      oldBrand.parentNode.removeChild(oldBrand);
    }
    if (!perBrand && prefix) prefix.textContent = narrative.body_prefix || '';
    if (!perBrand && body) body.textContent = typeof narrative.body_remainder === 'string'
      ? narrative.body_remainder
      : narrative.body;
    if (state) state.textContent = narrative.state_label;
    var observations = strip.querySelector('[data-pw-headline-observations]');
    if (observations && !perBrand) {
      clearChildren(observations);
      (narrative.observations || []).forEach(function (observation) {
        var item = document.createElement('li');
        item.textContent = observation;
        observations.appendChild(item);
      });
      observations.hidden = !narrative.observations || narrative.observations.length === 0;
    }
    var voices = strip.querySelector('[data-pw-headline-voice-entries]');
    if (voices) {
      var signature = JSON.stringify(topVoices.entries.map(function (entry) {
        return [entry.handle, entry.voice_star];
      }));
      if (voices.getAttribute('data-pw-voice-signature') !== signature) {
        clearChildren(voices);
        if (topVoices.entries.length === 0) {
          var emptyVoices = document.createElement('span');
          emptyVoices.className = 'muted';
          emptyVoices.textContent = voices.getAttribute('data-pw-empty-text') || '';
          voices.appendChild(emptyVoices);
        }
        topVoices.entries.forEach(function (entry, index) {
          if (index > 0) {
            var separator = document.createElement('span');
            separator.className = 'voice-separator';
            separator.textContent = ', ';
            voices.appendChild(separator);
          }
          var link = document.createElement('a');
          link.className = 'voice-chip';
          link.href = 'https://x.com/' + String(entry.handle || '').replace(/^@/, '');
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          var handle = document.createElement('span');
          handle.className = 'voice-handle';
          handle.textContent = '@' + String(entry.handle || '').replace(/^@/, '');
          var score = document.createElement('span');
          score.className = 'voice-star';
          score.innerHTML = ' (' + renderIcon('icon-star', 'voice-star-icon') + ' ' +
            escapeHtml(entry.voice_star) + ')';
          link.appendChild(handle);
          link.appendChild(score);
          voices.appendChild(link);
        });
        voices.setAttribute('data-pw-voice-signature', signature);
      }
    }
    strip.setAttribute('data-pw-window', String(narrative.window_days));
    strip.setAttribute('data-pw-computed-at', narrative.computed_at);
    strip.setAttribute('data-pw-state', narrative.state);
  }

  function renderPerBrandNarratives(container, narrative) {
    if (!container) throw new Error('trend narrative items container is missing');
    clearChildren(container);
    if (narrative.items.length === 0) {
      var empty = document.createElement('p');
      empty.className = 'headline-empty';
      empty.setAttribute('data-pw-headline-empty', '');
      empty.textContent = narrative.body || '';
      container.appendChild(empty);
      return;
    }
    var zh = isZhLocale(currentLocale(getHomeChartRegion()));
    narrative.items.forEach(function (item, index) {
      var article = document.createElement('article');
      var titleId = 'trend-narrative-' + (index + 1);
      var detailId = titleId + '-detail';
      article.className = 'headline-item';
      article.setAttribute('data-pw-headline-item', '');
      article.setAttribute('data-pw-brand-key', item.brand.key);
      article.setAttribute('data-pw-state', item.state);
      article.setAttribute('data-pw-verified-at', item.verified_at || '');
      article.setAttribute('aria-labelledby', titleId);

      var meta = document.createElement('div');
      meta.className = 'headline-item-meta';
      var brand = document.createElement(item.brand.url ? 'a' : 'span');
      brand.className = 'brand';
      brand.setAttribute('data-pw-headline-item-brand', '');
      brand.textContent = item.brand.display_name || item.brand.key;
      if (item.brand.url) brand.setAttribute('href', item.brand.url);
      meta.appendChild(brand);

      var itemState = document.createElement('span');
      itemState.className = 'headline-item-state';
      itemState.setAttribute('data-pw-headline-item-state', '');
      itemState.textContent = item.state_label;
      if (item.freshness.absolute) {
        itemState.setAttribute('title', item.freshness.absolute);
        itemState.setAttribute(
          'aria-label', item.state_label + '. ' + item.freshness.absolute
        );
      } else {
        itemState.setAttribute('aria-label', item.state_label);
      }
      meta.appendChild(itemState);
      article.appendChild(meta);

      var headline = document.createElement('h2');
      headline.className = 'headline-item-title';
      headline.setAttribute('data-pw-headline-item-title', '');
      headline.setAttribute('id', titleId);
      headline.textContent = item.headline;
      var detail = document.createElement('button');
      detail.type = 'button';
      detail.className = 'headline-disclosure';
      detail.setAttribute('data-pw-headline-detail', '');
      detail.setAttribute('aria-controls', detailId);
      detail.setAttribute('aria-expanded', 'false');
      detail.textContent = zh ? '详情' : 'detail';
      headline.appendChild(detail);
      article.appendChild(headline);

      var secondary = document.createElement('div');
      secondary.className = 'headline-item-secondary';
      secondary.setAttribute('data-pw-headline-item-secondary', '');
      secondary.setAttribute('id', detailId);
      secondary.hidden = true;
      var secondaryCopy = document.createElement('span');
      secondaryCopy.setAttribute('data-pw-headline-secondary-copy', '');
      secondaryCopy.setAttribute('role', 'button');
      secondaryCopy.setAttribute('tabindex', '0');
      secondaryCopy.textContent = item.secondary;
      secondary.appendChild(secondaryCopy);
      var hide = document.createElement('button');
      hide.type = 'button';
      hide.className = 'headline-disclosure';
      hide.setAttribute('data-pw-headline-hide', '');
      hide.textContent = zh ? '收起' : 'hide';
      secondary.appendChild(hide);
      article.appendChild(secondary);
      container.appendChild(article);
    });
  }

  function setHeadlineDetail(article, expanded, restoreFocus) {
    if (!article) return;
    var detail = article.querySelector('[data-pw-headline-detail]');
    var secondary = article.querySelector('[data-pw-headline-item-secondary]');
    if (!detail || !secondary) return;
    secondary.hidden = !expanded;
    detail.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    if (!expanded && restoreFocus && typeof detail.focus === 'function') detail.focus();
  }

  function wireHeadlineDisclosure() {
    document.addEventListener('click', function (event) {
      if (!event.target || !event.target.closest) return;
      var article = event.target.closest('[data-pw-headline-item]');
      if (!article) return;
      if (event.target.closest('[data-pw-headline-detail]')) {
        setHeadlineDetail(article, true);
        return;
      }
      if (event.target.closest('[data-pw-headline-hide]') ||
          event.target.closest('[data-pw-headline-item-secondary]')) {
        setHeadlineDetail(article, false, true);
      }
    });
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      if (!event.target || !event.target.closest ||
          !event.target.closest('[data-pw-headline-secondary-copy]')) return;
      event.preventDefault();
      setHeadlineDetail(event.target.closest('[data-pw-headline-item]'), false, true);
    });
  }

  function setStatus(node, text, visible) {
    if (!node) return;
    node.textContent = visible ? text : '';
    node.hidden = !visible;
  }

  function payloadIsEmpty(payload) {
    return Object.keys(payload.totals).reduce(function (sum, brand) {
      return sum + (Number(payload.totals[brand]) || 0);
    }, 0) === 0;
  }

  function updateProjectionStates(region, payload, announce) {
    setStatus(
      region.querySelector('[data-pw-chart-status]'),
      region.getAttribute('data-pw-chart-empty-text') || 'No chart data in this window',
      payloadIsEmpty(payload)
    );
    setStatus(
      document.querySelector('[data-pw-pulse-status]'),
      region.getAttribute('data-pw-pulse-empty-text') || 'No pulse data in this window',
      payload.pulse.entries.length === 0
    );
    var headlineStatus = document.querySelector('[data-pw-headline-status]');
    if (headlineStatus) {
      headlineStatus.setAttribute('data-pw-status-kind', announce ? 'success' : '');
    }
    setStatus(
      headlineStatus,
      region.getAttribute('data-pw-headline-updated-text') || 'Trend summaries updated',
      Boolean(announce)
    );
    region.setAttribute('data-pw-refresh-failed', 'false');
    var bar = document.querySelector('[data-pw-pulse]');
    if (bar) bar.setAttribute('data-pw-refresh-failed', 'false');
    var headline = document.querySelector('[data-pw-headline]');
    if (headline) headline.setAttribute('data-pw-refresh-failed', 'false');
  }

  function showRefreshFailure(region) {
    setStatus(
      region.querySelector('[data-pw-chart-status]'),
      region.getAttribute('data-pw-chart-error-text') || 'Chart refresh failed; showing last result',
      true
    );
    var headlineStatus = document.querySelector('[data-pw-headline-status]');
    if (headlineStatus) headlineStatus.setAttribute('data-pw-status-kind', 'error');
    setStatus(
      headlineStatus,
      region.getAttribute('data-pw-headline-error-text') || 'Trend summary refresh failed; showing last result',
      true
    );
    setStatus(
      document.querySelector('[data-pw-pulse-status]'),
      region.getAttribute('data-pw-pulse-error-text') || 'Pulse refresh failed; showing last result',
      true
    );
    region.setAttribute('data-pw-refresh-failed', 'true');
    var bar = document.querySelector('[data-pw-pulse]');
    if (bar) bar.setAttribute('data-pw-refresh-failed', 'true');
    var headline = document.querySelector('[data-pw-headline]');
    if (headline) headline.setAttribute('data-pw-refresh-failed', 'true');
  }

  function payloadFromFragment(html) {
    var parsed = new DOMParser().parseFromString(html, 'text/html');
    return readPayload(parsed.querySelector('canvas.home-chart'));
  }

  function commitFragment(region, html, payload) {
    var priorCanvas = chartIn(region);
    var priorChart = priorCanvas ? Chart.getChart(priorCanvas) : null;
    var priorPayload = readPayload(priorCanvas);
    var priorRegionHtml = region.innerHTML;
    var priorPulse = document.querySelector('[data-pw-pulse]');
    var priorPulseHtml = priorPulse && priorPulse.innerHTML;
    var priorHeadline = document.querySelector('[data-pw-headline]');
    var priorHeadlineHtml = priorHeadline && priorHeadline.outerHTML;
    var priorRefreshState = region.getAttribute('data-pw-refresh-failed');
    try {
      if (priorChart) priorChart.destroy();
      region.innerHTML = html;
      var canvas = chartIn(region);
      if (!canvas) throw new Error('chart fragment omitted canvas');
      renderOne(canvas);
      renderLegend(region, payload);
      renderPulse(region, payload.pulse);
      renderHeadline(payload.trend_narrative, payload.top_voices);
      updateProjectionStates(region, payload, true);
    } catch (error) {
      // A valid response must replace all four projections together. Restore
      // every projection if a renderer or DOM operation fails mid-commit.
      try {
        region.innerHTML = priorRegionHtml;
        if (priorPayload && chartIn(region)) {
          renderOne(chartIn(region));
          renderLegend(region, priorPayload);
        }
        var restoredPulse = document.querySelector('[data-pw-pulse]');
        if (restoredPulse && priorPulseHtml !== undefined) {
          restoredPulse.innerHTML = priorPulseHtml;
        }
        var currentHeadline = document.querySelector('[data-pw-headline]');
        if (priorHeadlineHtml && currentHeadline && currentHeadline.outerHTML !== undefined) {
          currentHeadline.outerHTML = priorHeadlineHtml;
        }
        if (priorRefreshState !== null) {
          region.setAttribute('data-pw-refresh-failed', priorRefreshState);
        }
      } catch (restoreError) {
        // The request failure path still exposes a status if restoration is
        // impossible in a degraded DOM.
      }
      throw error;
    }
  }

  function activeFilters() {
    return window.pwFilter && window.pwFilter.get ? window.pwFilter.get() : {};
  }

  function currentLocale(region) {
    var bodyLocale = document.body && typeof document.body.getAttribute === 'function'
      ? document.body.getAttribute('data-pw-locale')
      : '';
    return bodyLocale || region.getAttribute('data-pw-locale') || 'en';
  }

  function filtersForEvent(event) {
    var filters = event && event.detail && event.detail.filters;
    return isObject(filters) ? filters : activeFilters();
  }

  function requestChart(event) {
    var region = getHomeChartRegion();
    if (!region) return Promise.resolve(false);
    var requestGeneration = ++generation;
    if (activeController) activeController.abort();
    activeController = typeof AbortController === 'function' ? new AbortController() : null;
    var timeout = setTimeout(function () {
      if (activeController && requestGeneration === generation) activeController.abort();
    }, REQUEST_TIMEOUT_MS);
    var filters = filtersForEvent(event);
    var url = '/chart.html?filters=' + encodeURIComponent(JSON.stringify(filters)) +
      '&window=' + encodeURIComponent(filters.window || 1) +
      '&locale=' + encodeURIComponent(currentLocale(region));
    return fetch(url, {
      credentials: 'same-origin',
      signal: activeController ? activeController.signal : undefined,
    }).then(function (response) {
      if (!response.ok) throw new Error('chart response status was not OK');
      return response.text();
    }).then(function (html) {
      if (requestGeneration !== generation) return false;
      var payload = payloadFromFragment(html);
      if (!validPayload(payload)) throw new Error('chart response payload was malformed');
      if (requestGeneration !== generation) return false;
      commitFragment(region, html, payload);
      return true;
    }).catch(function (error) {
      if (requestGeneration === generation && (!error || error.name !== 'AbortError')) {
        showRefreshFailure(region);
        console.warn('pw-chart: refresh failed', error);
      }
      return false;
    }).then(function (result) {
      clearTimeout(timeout);
      return result;
    });
  }

  function redrawOneDayTimeAxes() {
    var region = getHomeChartRegion();
    var canvas = chartIn(region);
    var payload = readPayload(canvas);
    if (!validPayload(payload) || (payload.granularity || 'day') !== 'minute') return;
    renderOne(canvas);
  }

  function disableHtmxRefresh(region) {
    ['hx-get', 'hx-trigger', 'hx-vals', 'hx-swap'].forEach(function (name) {
      region.removeAttribute(name);
    });
  }

  function boot() {
    wireHeadlineDisclosure();
    var region = getHomeChartRegion();
    if (region) {
      disableHtmxRefresh(region);
      var canvas = chartIn(region);
      var payload = readPayload(canvas);
      if (validPayload(payload)) {
        renderOne(canvas);
        renderLegend(region, payload);
        renderPulse(region, payload.pulse);
        renderHeadline(payload.trend_narrative, payload.top_voices);
        updateProjectionStates(region, payload, false);
      }
      setInterval(requestChart, REFRESH_INTERVAL_MS);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  document.addEventListener('pw:filter-change', requestChart);
  document.addEventListener('pw:locale-change', requestChart);
  document.addEventListener('pw:timezone-change', redrawOneDayTimeAxes);
})();
