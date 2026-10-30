// Shared multi-brand home Chart.js and pulse lifecycle.

(function () {
  'use strict';

  if (typeof Chart !== 'undefined' && Chart.Tooltip && Chart.Tooltip.positioners) {
    Chart.Tooltip.positioners.pwCursorClear = function (items) {
      return Chart.Tooltip.positioners.average.call(this, items);
    };
  }

  var HOME_CHART_REGION_SELECTOR = '.home-chart-wrap[data-pw-chart]';
  var REFRESH_INTERVAL_MS = 60000;
  var REQUEST_TIMEOUT_MS = 12000;
  var generation = 0;
  var activeController = null;
  var fallbackComparisonHourFormatter = null;
  var chartRefreshTimer = null;
  var frozenPoint = null;
  var BROWSER_TIMEZONE = resolveBrowserTimezone();

  function resolveBrowserTimezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch (error) {
      return 'UTC';
    }
  }

  // Each brand keeps a fixed line pattern and beacon shape on the public
  // homepage chart, so similar colors stay distinguishable and a brand keeps
  // its look as rankings change. No two brands share a pair.
  var DASHES = { solid: [], dashed: [7, 4], dotted: [0, 4], dashdot: [9, 3.5, 0, 3.5] };
  var BRAND_STYLE = {
    deepseek: ['solid', 'circle'], qwen: ['solid', 'square'], moonshot_kimi: ['dashed', 'triangle'],
    minimax: ['dashed', 'diamond'], glm: ['dotted', 'square'], mimo: ['dotted', 'circle'],
    doubao: ['dashdot', 'diamond'], llama: ['dashdot', 'star'], hunyuan: ['dotted', 'triangle'],
    ernie: ['dashed', 'star'], mistral: ['dashdot', 'triangle'], upstage: ['solid', 'triangle'],
    nemo_megatron: ['solid', 'diamond'], stepfun: ['dashed', 'circle'], inclusionai: ['solid', 'star'],
    yi: ['dashed', 'square'], sensechat: ['dotted', 'diamond'], exaone: ['dotted', 'star'],
    kuaishou: ['dashdot', 'circle'], sakana_ai: ['dashdot', 'square'], dots: ['solid', 'cross'],
  };
  var SHAPES = ['circle', 'square', 'triangle', 'diamond', 'star', 'cross'];
  var LINE_END_GAP = 16;
  var PING_CYCLE_MS = 2250;
  var DIM_LINE_ALPHA = 0.24;
  var AXIS_TEXT = '#687589';
  var GRID_LINE = '#dfe4ec';
  var AXIS_LINE = '#e6eaf1';

  function brandStyle(brand) {
    var pair = BRAND_STYLE[brand];
    if (!pair) {
      var hash = 0;
      String(brand || '').split('').forEach(function (character) {
        hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
      });
      pair = [Object.keys(DASHES)[hash % 4], SHAPES[(hash >> 2) % 6]];
    }
    return { dash: pair[0], shape: pair[1] };
  }

  function shapePoints(shape, x, y, r) {
    function ring(count, radius, turn) {
      var points = [];
      for (var k = 0; k < count; k++) {
        var angle = turn + k * 2 * Math.PI / count;
        points.push([x + radius * Math.cos(angle), y + radius * Math.sin(angle)]);
      }
      return points;
    }
    if (shape === 'square') {
      var q = r * 0.86;
      return [[x - q, y - q], [x + q, y - q], [x + q, y + q], [x - q, y + q]];
    }
    if (shape === 'triangle') {
      return ring(3, r * 1.3, -Math.PI / 2).map(function (point) { return [point[0], point[1] + r * 0.2]; });
    }
    if (shape === 'diamond') return ring(4, r * 1.2, -Math.PI / 2);
    if (shape === 'star') {
      var outer = ring(5, r * 1.45, -Math.PI / 2);
      var inner = ring(5, r * 0.62, -Math.PI / 2 + Math.PI / 5);
      var star = [];
      for (var k = 0; k < 5; k++) star.push(outer[k], inner[k]);
      return star;
    }
    if (shape === 'cross') {
      var a = r * 0.42;
      var b = r * 1.2;
      return [[x - a, y - b], [x + a, y - b], [x + a, y - a], [x + b, y - a], [x + b, y + a], [x + a, y + a],
        [x + a, y + b], [x - a, y + b], [x - a, y + a], [x - b, y + a], [x - b, y - a], [x - a, y - a]];
    }
    return null;
  }

  function shapePath(ctx, shape, x, y, r) {
    var points = shapePoints(shape, x, y, r);
    ctx.beginPath();
    if (!points) {
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      return;
    }
    points.forEach(function (point, index) { ctx[index ? 'lineTo' : 'moveTo'](point[0], point[1]); });
    ctx.closePath();
  }

  function shapeSvg(shape, x, y, r, attrs) {
    var points = shapePoints(shape, x, y, r);
    return points
      ? '<polygon points="' + points.map(function (point) {
          return point[0].toFixed(2) + ',' + point[1].toFixed(2);
        }).join(' ') + '" ' + attrs + '/>'
      : '<circle cx="' + x + '" cy="' + y + '" r="' + r + '" ' + attrs + '/>';
  }

  // Legend swatch: a short line in the brand's pattern ending in its beacon shape.
  function swatchSvg(brand, color) {
    var style = brandStyle(brand);
    var dash = DASHES[style.dash];
    var safeColor = escapeHtml(color);
    return '<svg class="pw-swatch" width="26" height="12" viewBox="0 0 26 12" aria-hidden="true">' +
      '<line x1="1.5" y1="6" x2="18" y2="6" stroke="' + safeColor + '" stroke-width="1.75" stroke-linecap="round"' +
      (dash.length ? ' stroke-dasharray="' + dash.map(function (value) { return value * 0.6; }).join(' ') + '"' : '') +
      '/>' + shapeSvg(style.shape, 20.5, 6, 3.4, 'class="pw-swatch-ping" fill="' + safeColor + '"') +
      shapeSvg(style.shape, 20.5, 6, 3.4, 'fill="' + safeColor + '"') + '</svg>';
  }

  function brandOfDataset(dataset) {
    var match = /^([a-z0-9_]+)/i.exec(String(dataset && dataset.label || ''));
    return match ? match[1].toLowerCase() : null;
  }

  function localizedBrandName(entry, locale) {
    if (!entry) return '';
    return isZhLocale(locale)
      ? (entry.display_name_zh_cn || entry.display_name || entry.nickname)
      : (entry.display_name_en || entry.display_name || entry.nickname);
  }

  function easeOut(progress) {
    // CSS ease-out, cubic-bezier(0, 0, 0.58, 1), solved for x.
    var low = 0;
    var high = 1;
    var t = progress;
    for (var k = 0; k < 18; k++) {
      t = (low + high) / 2;
      var x = 3 * (1 - t) * t * t * 0.58 + t * t * t;
      if (x < progress) low = t; else high = t;
    }
    return 3 * (1 - t) * t * t + t * t * t;
  }

  function nowMs() {
    return typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
  }

  var LEGACY_BRAND_NAMES = {
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

        var right = options.placement === 'right';
        var text = String(title.text);
        ctx.save();
        ctx.fillStyle = ticks.color || title.color || Chart.defaults.color;
        ctx.font = weight + ' ' + size + 'px ' + family;
        ctx.textAlign = right ? 'left' : 'right';
        ctx.textBaseline = 'middle';
        ctx.fillText(
          right ? text.charAt(0).toUpperCase() + text.slice(1) : text,
          right ? chart.chartArea.right + 6 : chart.chartArea.left - 4,
          scale.top + tickLength + padding + size / 2
        );
        ctx.restore();
      });
    },
  };

  var HOVER_FREEZE_PLUGIN = {
    id: 'pwHoverFreeze',
    afterEvent: function (chart, args) {
      if (!frozenPoint || frozenPoint.chart !== chart) return;
      holdFrozenPoint(chart, frozenPoint.index, false);
      if (args) args.changed = true;
    },
  };

  // Brand focus (hover, keyboard, pinned click, touch tap), count labels and
  // the always-on beacon at each line's latest time slot.
  var focus = { hover: null, pinned: null, touch: null };
  var reducedMotion = false;
  var chartInView = true;
  var lastPointerType = 'mouse';

  function focusedBrand() {
    return focus.hover || focus.touch || focus.pinned;
  }

  function isFocusChart(chart) {
    return Boolean(chart && chart.options && chart.options.plugins &&
      chart.options.plugins.pwBrandFocus && chart.options.plugins.pwBrandFocus.enabled);
  }

  function drawBeacon(chart, args, phase) {
    var points = (args.meta && args.meta.data) || [];
    var dataset = chart.data.datasets[args.index];
    var last = points[points.length - 1];
    if (!last) return;
    var position = { x: last.x, y: last.y };
    if (last.skip || !Number.isFinite(position.y)) {
      // An empty latest five-minute bucket is drawn as a gap; its beacon sits at 0.
      var xScale = chart.scales.x;
      var yScale = chart.scales.y;
      if (!xScale || !yScale) return;
      position = { x: xScale.getPixelForValue(points.length - 1), y: yScale.getPixelForValue(0) };
    }
    if (!Number.isFinite(position.x) || !Number.isFinite(position.y)) return;
    var brand = brandOfDataset(dataset);
    var focused = focusedBrand();
    var alpha = focused && brand !== focused ? DIM_LINE_ALPHA : 1;
    var shape = brandStyle(brand).shape;
    var ctx = chart.ctx;
    ctx.save();
    if (!reducedMotion && phase !== null) {
      var eased = easeOut(phase);
      ctx.fillStyle = colorWithAlpha(dataset.borderColor, alpha * 0.6 * (1 - eased));
      shapePath(ctx, shape, position.x, position.y, 4 * (1 + 3 * eased));
      ctx.fill();
    }
    ctx.fillStyle = colorWithAlpha(dataset.borderColor, alpha);
    shapePath(ctx, shape, position.x, position.y, 4);
    ctx.fill();
    ctx.restore();
  }

  function drawCountLabels(chart, args) {
    var dataset = chart.data.datasets[args.index];
    var area = chart.chartArea;
    var points = (args.meta && args.meta.data) || [];
    var lastRight = -Infinity;
    var ctx = chart.ctx;
    ctx.save();
    ctx.font = "600 10px 'DM Sans', system-ui, sans-serif";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.lineJoin = 'round';
    for (var index = 0; index < points.length; index++) {
      var point = points[index];
      if (!point || point.skip || !Number.isFinite(point.x) || !Number.isFinite(point.y)) continue;
      var parsed = args.meta.controller.getParsed(index);
      var value = parsed && parsed.y;
      if (value === null || value === undefined || !Number.isFinite(value)) continue;
      var text = String(Math.round(value));
      var width = ctx.measureText(text).width;
      // A label that would collide with the previous one is skipped.
      if (point.x - width / 2 < lastRight + 2) continue;
      var y = Math.max(area.top + 11, point.y - 5);
      ctx.strokeStyle = 'rgba(255,255,255,0.9)';
      ctx.lineWidth = 3;
      ctx.strokeText(text, point.x, y);
      ctx.fillStyle = dataset.borderColor;
      ctx.fillText(text, point.x, y);
      lastRight = point.x + width / 2;
    }
    ctx.restore();
  }

  var BRAND_FOCUS_PLUGIN = {
    id: 'pwBrandFocus',
    afterLayout: function (chart) {
      // Leave room between each line's latest point and the right-hand axis.
      Object.keys(chart.scales).forEach(function (key) {
        var scale = chart.scales[key];
        if (!scale.isHorizontal() || scale._reversePixels) return;
        scale._endPixel -= LINE_END_GAP;
        scale._length = scale._endPixel - scale._startPixel;
      });
    },
    beforeDatasetDraw: function (chart, args) {
      var dataset = chart.data.datasets[args.index];
      var focused = focusedBrand();
      var line = args.meta && args.meta.dataset;
      if (line && line.options && dataset._isTotalLine) {
        var solid = Boolean(focused) && brandOfDataset(dataset) === focused;
        line.options.borderDash = solid ? [] : DASHES[brandStyle(brandOfDataset(dataset)).dash];
        // Chart.js caches segment styles; drop them when this line's focus flips.
        if (line._pwSolid !== solid) {
          line._pwSolid = solid;
          line._segments = undefined;
        }
      }
      chart.ctx.save();
      if (focused && brandOfDataset(dataset) !== focused) chart.ctx.globalAlpha = DIM_LINE_ALPHA;
    },
    afterDatasetDraw: function (chart, args) {
      chart.ctx.restore();
      var dataset = chart.data.datasets[args.index];
      if (!dataset._isTotalLine || args.meta.hidden) return;
      var phase = (nowMs() % PING_CYCLE_MS) / PING_CYCLE_MS;
      drawBeacon(chart, args, phase);
      if (focusedBrand() && brandOfDataset(dataset) === focusedBrand()) drawCountLabels(chart, args);
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

  function colorVarFor(categoryKey) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue('--bar-' + categoryKey).trim() || '#9ca3af';
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

  function clockLabel(instant, timezone) {
    var locale = currentLocale(getHomeChartRegion());
    if (window.pwTime && typeof window.pwTime.clockText === 'function') {
      return window.pwTime.clockText(new Date(instant), locale, timezone);
    }
    return new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: timezone,
    }).format(new Date(instant));
  }

  function generalOneDayScales(days) {
    if (!window.pwTime || typeof window.pwTime.oneDayTicks !== 'function' || days.length < 2) return null;
    var timezone = comparisonState();
    var activeMode = window.__pwTz && window.__pwTz.mode === 'ca' ? 'ca' : 'local';
    var dimText = colorWithAlpha(AXIS_TEXT, 0.55);

    function timeScale(weight, color, zone, fontWeight, title, drawBorder) {
      var built = [];
      return {
        type: 'category',
        position: 'bottom',
        weight: weight,
        labels: days,
        offset: false,
        afterBuildTicks: function (axis) {
          built = window.pwTime.oneDayTicks(days, axis.width);
          axis.ticks = built.map(function (tick) { return { value: tick.value }; });
        },
        ticks: {
          autoSkip: false,
          color: color,
          font: { size: 9, weight: fontWeight },
          maxRotation: 0,
          minRotation: 0,
          padding: drawBorder ? 2 : 0,
          callback: function (_value, index) {
            return built[index] ? clockLabel(built[index].instant, zone) : '';
          },
        },
        grid: {
          display: drawBorder,
          drawOnChartArea: false,
          drawTicks: drawBorder,
          tickLength: drawBorder ? 4 : 0,
          color: AXIS_LINE,
        },
        border: { display: drawBorder, color: AXIS_LINE, width: 1 },
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
      x: timeScale(0, activeMode === 'local' ? AXIS_TEXT : dimText, undefined, 600,
        timezone.localLabel || 'local', true),
      xComparison: timeScale(1, activeMode === 'ca' ? AXIS_TEXT : dimText, timezone.timezone,
        activeMode === 'ca' ? 600 : 400, timezone.shortLabel || 'CA', false),
    };
  }

  function generalDateScale(days) {
    var locale = currentLocale(getHomeChartRegion());
    var yearly = days.length > 90;
    var helpers = window.pwTime;
    return {
      type: 'category',
      labels: days,
      afterBuildTicks: function (axis) {
        if (!helpers) return;
        axis.ticks = helpers.dateTickIndices(days).map(function (value) { return { value: value }; });
      },
      ticks: {
        autoSkip: !helpers,
        maxTicksLimit: helpers ? undefined : 7,
        maxRotation: 0,
        color: AXIS_TEXT,
        callback: function (value) {
          if (!days[value]) return '';
          return helpers ? helpers.dateLabel(days[value], locale, yearly) : days[value];
        },
      },
      grid: { display: false },
      border: { color: AXIS_LINE },
    };
  }

  function chartScales(days, granularity, general) {
    if (general) {
      var minute = granularity === 'minute';
      return Object.assign(minute ? (generalOneDayScales(days) || { x: generalDateScale(days) })
        : { x: generalDateScale(days) }, {
        y: {
          position: 'right',
          beginAtZero: true,
          title: {
            display: true,
            text: minute ? 'posts / 5min' : 'posts / day',
            color: AXIS_TEXT,
            font: minute ? { size: 9 } : undefined,
            padding: minute ? 0 : undefined,
          },
          ticks: {
            precision: 0,
            color: AXIS_TEXT,
            font: minute ? { size: 9 } : undefined,
            padding: minute ? 2 : undefined,
          },
          grid: { color: GRID_LINE },
          border: { display: false, dash: [1, 3] },
        },
      });
    }
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

  function prettifiedBucketDateTime(timestamp, locale) {
    var instant = new Date(timestamp);
    if (!Number.isFinite(instant.getTime())) return null;
    if (isPublicHomeRegion(getHomeChartRegion()) && window.pwTime) {
      return generalBucketDateTime(instant, locale);
    }
    var zh = isZhLocale(locale);
    var intlLocale = zh ? 'zh-CN' : 'en-US';
    var options = {
      year: 'numeric',
      month: zh ? 'numeric' : 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    };
    var local = new Intl.DateTimeFormat(intlLocale, options).format(instant);
    var beijing = new Intl.DateTimeFormat(intlLocale, Object.assign({
      timeZone: 'Asia/Shanghai',
    }, options)).format(instant);
    var localLine = (zh ? '本地 ' : 'Local: ') + local;
    var beijingLine = (zh ? '北京 ' : 'Beijing: ') + beijing;
    return {
      local: localLine,
      beijing: beijingLine,
      title: localLine + ' · ' + beijingLine,
    };
  }

  function generalBucketDateTime(instant, locale) {
    var zh = isZhLocale(locale);
    var ja = String(locale || '').toLowerCase().indexOf('ja') === 0;
    var dateOptions = { year: 'numeric', month: zh || ja ? 'numeric' : 'short', day: 'numeric' };
    function stamp(timeZone) {
      var date = new Intl.DateTimeFormat(zh ? 'zh-CN' : ja ? 'ja-JP' : 'en-US',
        Object.assign({ timeZone: timeZone }, dateOptions)).format(instant);
      return date + ' ' + window.pwTime.clockText(instant, locale, timeZone);
    }
    var localLine = (zh ? '本地 ' : ja ? '現地 ' : 'Local: ') + stamp(undefined);
    var beijingLine = (zh || ja ? '北京 ' : 'Beijing: ') + stamp('Asia/Shanghai');
    return { local: localLine, beijing: beijingLine, title: localLine + ' · ' + beijingLine };
  }

  function fiveMinuteBucket(payload, index) {
    if (!payload || Number(payload.window_days) !== 1 ||
        (payload.granularity || 'day') !== 'minute' ||
        !Number.isInteger(index) || index < 0 || index >= payload.days.length) return null;
    var startMs = Date.parse(payload.days[index]);
    if (!Number.isFinite(startMs)) return null;
    return {
      start: new Date(startMs).toISOString(),
      end: new Date(startMs + 5 * 60 * 1000).toISOString(),
    };
  }

  function activeTotalPoints(chart, index) {
    return chart.data.datasets.reduce(function (points, dataset, datasetIndex) {
      if (!dataset._isTotalLine || !Number.isFinite(Number(dataset.data[index]))) return points;
      if (typeof chart.isDatasetVisible === 'function' && !chart.isDatasetVisible(datasetIndex)) {
        return points;
      }
      var meta = typeof chart.getDatasetMeta === 'function'
        ? chart.getDatasetMeta(datasetIndex)
        : null;
      if (meta && meta.hidden === true) return points;
      points.push({ datasetIndex: datasetIndex, index: index });
      return points;
    }, []);
  }

  function frozenTooltipPosition(chart, points) {
    if (!points.length || typeof chart.getDatasetMeta !== 'function') return { x: 0, y: 0 };
    var element = (chart.getDatasetMeta(points[0].datasetIndex).data || [])[points[0].index];
    if (!element) return { x: 0, y: 0 };
    if (typeof element.getCenterPoint === 'function') return element.getCenterPoint();
    return { x: Number(element.x) || 0, y: Number(element.y) || 0 };
  }

  function holdFrozenPoint(chart, index, update) {
    var points = activeTotalPoints(chart, index);
    if (!points.length) return false;
    if (typeof chart.setActiveElements === 'function') chart.setActiveElements(points);
    if (chart.tooltip && typeof chart.tooltip.setActiveElements === 'function') {
      chart.tooltip.setActiveElements(points, frozenTooltipPosition(chart, points));
    }
    if (update && typeof chart.update === 'function') chart.update('none');
    return true;
  }

  function clearFrozenPoint(chart) {
    if (!chart) return;
    if (typeof chart.setActiveElements === 'function') chart.setActiveElements([]);
    if (chart.tooltip && typeof chart.tooltip.setActiveElements === 'function') {
      chart.tooltip.setActiveElements([], { x: 0, y: 0 });
    }
    if (typeof chart.update === 'function') chart.update('none');
  }

  function snapshotLocaleButtons() {
    return Array.prototype.map.call(
      document.querySelectorAll('[data-pw-locale-btn]'),
      function (button) {
        return {
          button: button,
          active: Boolean(button.classList && button.classList.contains('is-active')),
          ariaPressed: button.getAttribute('aria-pressed'),
        };
      }
    );
  }

  function clearLocaleSelection() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-pw-locale-btn]'), function (button) {
      if (button.classList) button.classList.remove('is-active');
      button.setAttribute('aria-pressed', 'false');
    });
  }

  function restoreLocaleSelection(snapshot) {
    (snapshot || []).forEach(function (entry) {
      if (entry.button.classList) {
        entry.button.classList.toggle('is-active', entry.active);
      }
      if (entry.ariaPressed === null) entry.button.removeAttribute('aria-pressed');
      else entry.button.setAttribute('aria-pressed', entry.ariaPressed);
    });
  }

  function stopChartRefresh() {
    if (chartRefreshTimer !== null) clearInterval(chartRefreshTimer);
    chartRefreshTimer = null;
  }

  function startChartRefresh() {
    if (chartRefreshTimer !== null || frozenPoint || !getHomeChartRegion()) return;
    chartRefreshTimer = setInterval(requestChart, REFRESH_INTERVAL_MS);
  }

  function cancelChartRequest() {
    generation += 1;
    if (activeController) activeController.abort();
    activeController = null;
  }

  function startHoverFreeze(chart, payload, index) {
    var range = fiveMinuteBucket(payload, index);
    var formatted = range && prettifiedBucketDateTime(
      range.start,
      currentLocale(getHomeChartRegion())
    );
    if (!range || !formatted || !holdFrozenPoint(chart, index, true)) return false;
    var localeButtons = snapshotLocaleButtons();
    stopChartRefresh();
    cancelChartRequest();
    frozenPoint = {
      chart: chart,
      canvas: chart.canvas,
      index: index,
      localeButtons: localeButtons,
    };
    clearLocaleSelection();
    if (document.body && typeof document.body.setAttribute === 'function') {
      document.body.setAttribute('data-pw-hover-freeze', 'true');
    }
    if (chart.canvas && typeof chart.canvas.setAttribute === 'function') {
      chart.canvas.setAttribute('data-pw-hover-freeze-index', String(index));
    }
    document.dispatchEvent(new CustomEvent('pw:hover-freeze-start', {
      detail: {
        start: range.start,
        end: range.end,
        title: formatted.title,
        local: formatted.local,
        beijing: formatted.beijing,
        index: index,
      },
    }));
    return true;
  }

  function endHoverFreeze() {
    if (!frozenPoint) return false;
    var prior = frozenPoint;
    frozenPoint = null;
    clearFrozenPoint(prior.chart);
    restoreLocaleSelection(prior.localeButtons);
    if (document.body && typeof document.body.removeAttribute === 'function') {
      document.body.removeAttribute('data-pw-hover-freeze');
    }
    if (prior.canvas && typeof prior.canvas.removeAttribute === 'function') {
      prior.canvas.removeAttribute('data-pw-hover-freeze-index');
    }
    startChartRefresh();
    document.dispatchEvent(new CustomEvent('pw:hover-freeze-end'));
    return true;
  }

  function exactChartPoint(chart, event) {
    if (!chart || typeof chart.getElementsAtEventForMode !== 'function') return null;
    var points = chart.getElementsAtEventForMode(
      event && event.native ? event.native : event,
      'nearest',
      { intersect: true, axis: 'xy' },
      false
    ) || [];
    return points.find(function (point) {
      var dataset = chart.data.datasets[point.datasetIndex];
      return dataset && dataset._isTotalLine && Number.isFinite(Number(dataset.data[point.index]));
    }) || null;
  }

  function handleChartClick(chart, payload, event) {
    if (!fiveMinuteBucket(payload, 0)) return;
    var point = exactChartPoint(chart, event);
    if (frozenPoint) {
      if (frozenPoint.chart === chart && point && point.index === frozenPoint.index) {
        holdFrozenPoint(chart, frozenPoint.index, true);
        return;
      }
      endHoverFreeze();
      return;
    }
    if (point) startHoverFreeze(chart, payload, point.index);
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
    var general = isPublicHomeRegion(region);
    var compactPublicOneDay = granularity === 'minute' && general;
    var prior = Chart.getChart(canvas);
    if (prior) prior.destroy();

    var datasets = [];
    brandList.forEach(function (brand, brandIndex) {
      var stroke = colors[brand] || '#9ca3af';
      var totalData = granularity === 'minute'
        ? series[brand].map(function (value) { return value === 0 ? NaN : value; })
        : series[brand];
      var partialDay = granularity === 'day' && Number(payload.window_days) > 1;
      if (general) {
        var dash = DASHES[brandStyle(brand).dash];
        datasets.push({
          label: brand + ' (total)',
          data: totalData,
          type: 'line',
          borderColor: stroke,
          backgroundColor: stroke,
          borderWidth: compactPublicOneDay ? 1.75 : 2,
          borderDash: dash,
          borderCapStyle: 'round',
          pointRadius: 0,
          pointHoverRadius: 0,
          pointHitRadius: granularity === 'minute' ? 8 : 0,
          cubicInterpolationMode: 'monotone',
          fill: false,
          segment: {
            borderDash: function (context) {
              // The focused line is solid end to end; the dashed partial last
              // day stays only on solid-pattern lines.
              if (focusedBrand() === brand) return [];
              if (dash.length || !partialDay) return undefined;
              return context.p1DataIndex === days.length - 1 ? [4, 4] : undefined;
            },
          },
          _brandIndex: brandIndex,
          _isTotalLine: true,
        });
      } else {
        datasets.push({
          label: brand + ' (total)',
          data: totalData,
          type: 'line',
          borderColor: stroke,
          backgroundColor: stroke,
          borderWidth: 2,
          pointRadius: granularity === 'minute' ? 1.5 : 0,
          pointHitRadius: granularity === 'minute' ? 8 : 0,
          tension: granularity === 'minute' ? 0.3 : 0,
          fill: false,
          segment: partialDay
            ? {
                borderDash: function (context) {
                  return context.p1DataIndex === days.length - 1 ? [4, 4] : undefined;
                },
              }
            : undefined,
          _brandIndex: brandIndex,
          _isTotalLine: true,
        });
      }
      Object.keys(stacked[brand] || {}).forEach(function (categoryKey) {
        var values = stacked[brand][categoryKey];
        datasets.push({
          label: brand + ' ' + categoryKey,
          data: granularity === 'minute'
            ? values.map(function (value) { return value === 0 ? NaN : value; })
            : values,
          type: 'line',
          borderColor: 'transparent',
          backgroundColor: colorVarFor(categoryKey),
          borderWidth: 0,
          pointRadius: general ? 0 : (granularity === 'minute' ? 1.5 : 0),
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
      plugins: general
        ? [TIMEZONE_ROW_LABEL_PLUGIN, HOVER_FREEZE_PLUGIN, BRAND_FOCUS_PLUGIN]
        : [TIMEZONE_ROW_LABEL_PLUGIN, HOVER_FREEZE_PLUGIN],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          pwTimezoneRowLabels: {
            display: granularity === 'minute',
            placement: general ? 'right' : 'left',
          },
          pwBrandFocus: { enabled: general },
          tooltip: {
            position: 'pwCursorClear',
            caretPadding: 12,
            // The General-style chart shows no tooltip; brand focus replaces it.
            enabled: !general,
            mode: 'index',
            intersect: false,
            filter: function (item) { return item.dataset._isTotalLine === true; },
            callbacks: {
              title: function (contexts) {
                if (granularity !== 'minute' || !contexts || !contexts.length) {
                  return contexts && contexts.length ? contexts[0].label : '';
                }
                var formatted = prettifiedBucketDateTime(
                  days[contexts[0].dataIndex],
                  currentLocale(getHomeChartRegion())
                );
                return formatted ? [formatted.local, formatted.beijing] : contexts[0].label;
              },
              label: function (context) {
                var value = context.parsed.y;
                return context.dataset.label + ': ' + value + (value === 1 ? ' post' : ' posts');
              },
            },
          },
        },
        scales: chartScales(days, granularity, general),
        onHover: function () {},
        onClick: function (event, _elements, chart) {
          handleChartClick(chart, payload, event);
        },
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

  function brandLogoUrls() {
    var raw = document.body && typeof document.body.getAttribute === 'function'
      ? document.body.getAttribute('data-pw-brand-logos')
      : null;
    try {
      var parsed = JSON.parse(raw || '{}');
      return isObject(parsed) ? parsed : {};
    } catch (error) { return {}; }
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
    if (!isPublicHomeRegion(region)) {
      legend.innerHTML = brandOrder.map(function (brand) {
        return '<span data-pw-chart-brand="' + escapeHtml(brand) + '"><i style="background:' +
          escapeHtml((payload.colors || {})[brand] || '#9ca3af') + '"></i>' +
          escapeHtml(LEGACY_BRAND_NAMES[brand] || brand) + '</span>';
      }).join('');
      return;
    }
    var locale = currentLocale(region);
    var entries = {};
    payload.pulse.entries.forEach(function (entry) { entries[entry.nickname] = entry; });
    var logos = brandLogoUrls();
    legend.innerHTML = brandOrder.map(function (brand) {
      var color = (payload.colors || {})[brand] || '#9ca3af';
      var name = entries[brand] ? localizedBrandName(entries[brand], locale) : brand;
      var logo = typeof logos[brand] === 'string' ? logos[brand] : '';
      return '<button type="button" data-pw-chart-brand="' + escapeHtml(brand) + '" aria-pressed="false">' +
        swatchSvg(brand, color) +
        (logo ? '<img class="pw-legend-logo" src="' + escapeHtml(logo) + '" alt="" width="14" height="14">' : '') +
        '<span class="pw-legend-name">' + escapeHtml(name) + '</span></button>';
    }).join('');
  }

  function focusCharts() {
    var region = getHomeChartRegion();
    var canvas = chartIn(region);
    var chart = canvas && typeof Chart.getChart === 'function' ? Chart.getChart(canvas) : null;
    return chart && isFocusChart(chart) ? [chart] : [];
  }

  function legendButtons(region) {
    if (!region || typeof region.querySelectorAll !== 'function') return [];
    return Array.prototype.slice.call(
      region.querySelectorAll('[data-pw-chart-legend] [data-pw-chart-brand]')
    );
  }

  function paintFocus() {
    var region = getHomeChartRegion();
    if (!isPublicHomeRegion(region)) return;
    var focused = focusedBrand();
    var delay = -(nowMs() % PING_CYCLE_MS) + 'ms';
    legendButtons(region).forEach(function (button) {
      var brand = button.getAttribute('data-pw-chart-brand');
      if (button.classList) {
        button.classList.toggle('pw-legend-focus', Boolean(focused) && brand === focused);
        button.classList.toggle('pw-legend-dim', Boolean(focused) && brand !== focused);
      }
      button.setAttribute('aria-pressed', focus.pinned === brand ? 'true' : 'false');
      if (button.style && button.style.setProperty) button.style.setProperty('--pw-ping-delay', delay);
    });
    focusCharts().forEach(function (chart) { chart.draw(); });
  }

  function setFocus(kind, brand) {
    if (focus[kind] === brand) return;
    focus[kind] = brand;
    paintFocus();
  }

  function reconcileFocus(payload) {
    var brands = Object.keys((payload && payload.series) || {});
    ['hover', 'pinned', 'touch'].forEach(function (kind) {
      if (focus[kind] && brands.indexOf(focus[kind]) === -1) focus[kind] = null;
    });
  }

  // The brand whose drawn line (any segment, not only its points) is nearest
  // the pointer within `reach` pixels; the first brand in legend order wins ties.
  function lineAt(chart, event, reach) {
    if (!chart || !chart.canvas || typeof chart.canvas.getBoundingClientRect !== 'function') return null;
    var rect = chart.canvas.getBoundingClientRect();
    var px = event.clientX - rect.left;
    var py = event.clientY - rect.top;
    var best = null;
    var bestDistance = reach * reach;
    chart.data.datasets.forEach(function (dataset, index) {
      if (!dataset._isTotalLine) return;
      var meta = chart.getDatasetMeta(index);
      if (meta.hidden || !chart.isDatasetVisible(index)) return;
      var points = (meta.data || []).filter(function (point) {
        return point && !point.skip && Number.isFinite(point.x) && Number.isFinite(point.y);
      });
      for (var j = 0; j < points.length; j++) {
        var a = points[j];
        var b = points[j + 1] || a;
        var vx = b.x - a.x;
        var vy = b.y - a.y;
        var length = vx * vx + vy * vy;
        var t = length ? Math.max(0, Math.min(1, ((px - a.x) * vx + (py - a.y) * vy) / length)) : 0;
        var dx = a.x + t * vx - px;
        var dy = a.y + t * vy - py;
        var distance = dx * dx + dy * dy;
        if (distance < bestDistance) {
          bestDistance = distance;
          best = brandOfDataset(dataset);
        }
      }
    });
    return best;
  }

  function wireFocus(region) {
    if (!region || typeof region.addEventListener !== 'function' || region._pwFocusWired) return;
    region._pwFocusWired = true;
    function legendItem(event) {
      var item = event.target && event.target.closest
        ? event.target.closest('[data-pw-chart-legend] [data-pw-chart-brand]')
        : null;
      return item && region.contains(item) ? item : null;
    }
    function chartFrom(event) {
      return event.target && event.target.matches && event.target.matches('canvas.home-chart')
        ? Chart.getChart(event.target)
        : null;
    }
    function recordPointer(event) { lastPointerType = event.pointerType || 'mouse'; }
    document.addEventListener('pointerdown', function (event) {
      recordPointer(event);
      if (lastPointerType === 'touch' && focus.touch && !region.contains(event.target)) {
        setFocus('touch', null);
      }
    }, true);
    region.addEventListener('pointerover', function (event) {
      if (event.pointerType === 'touch') return;
      var item = legendItem(event);
      if (item) setFocus('hover', item.getAttribute('data-pw-chart-brand'));
    });
    region.addEventListener('pointerout', function (event) {
      if (event.pointerType === 'touch') return;
      var item = legendItem(event);
      if (item && !item.contains(event.relatedTarget)) setFocus('hover', null);
    });
    region.addEventListener('pointermove', function (event) {
      if (event.pointerType === 'touch') return;
      var chart = chartFrom(event);
      if (chart) setFocus('hover', lineAt(chart, event, 8));
    });
    region.addEventListener('pointerleave', function (event) {
      if (event.pointerType !== 'touch') setFocus('hover', null);
    });
    region.addEventListener('focusin', function (event) {
      var item = legendItem(event);
      if (item && lastPointerType !== 'touch') setFocus('hover', item.getAttribute('data-pw-chart-brand'));
    });
    region.addEventListener('focusout', function (event) {
      if (legendItem(event)) setFocus('hover', null);
    });
    region.addEventListener('click', function (event) {
      var item = legendItem(event);
      var chart = chartFrom(event);
      if (lastPointerType === 'touch') {
        // A tap does what hover does; tapping the same brand or elsewhere clears it.
        var tapped = item ? item.getAttribute('data-pw-chart-brand') : (chart ? lineAt(chart, event, 16) : null);
        setFocus('touch', tapped && tapped === focus.touch ? null : tapped);
        return;
      }
      if (item) {
        var brand = item.getAttribute('data-pw-chart-brand');
        // Keyboard activation (Enter/Space) toggles the pin; a mouse click pins.
        setFocus('pinned', event.detail === 0 && focus.pinned === brand ? null : brand);
        return;
      }
      setFocus('pinned', chart ? lineAt(chart, event, 8) : null);
    });
    document.addEventListener('click', function (event) {
      if (lastPointerType !== 'touch' && focus.pinned && !region.contains(event.target)) {
        setFocus('pinned', null);
      }
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && focus.pinned) setFocus('pinned', null);
    });
  }

  var beaconLoopStarted = false;

  function watchMotionAndVisibility(region) {
    if (window.matchMedia) {
      var query = window.matchMedia('(prefers-reduced-motion: reduce)');
      reducedMotion = Boolean(query.matches);
      var onChange = function (event) {
        reducedMotion = Boolean(event.matches);
        focusCharts().forEach(function (chart) { chart.draw(); });
      };
      if (query.addEventListener) query.addEventListener('change', onChange);
      else if (query.addListener) query.addListener(onChange);
    }
    if (typeof IntersectionObserver === 'function' && region) {
      new IntersectionObserver(function (entries) {
        chartInView = entries.some(function (entry) { return entry.isIntersecting; });
      }).observe(region);
    }
  }

  // One redraw loop (about 30 frames a second) animates the beacons while the
  // chart is on screen and the tab is visible.
  function startBeaconLoop() {
    if (beaconLoopStarted || typeof requestAnimationFrame !== 'function') return;
    beaconLoopStarted = true;
    var lastFrame = 0;
    function frame(timestamp) {
      if (!reducedMotion && chartInView && !document.hidden && timestamp - lastFrame >= 33) {
        lastFrame = timestamp;
        focusCharts().forEach(function (chart) { chart.draw(); });
      }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function focusedLegendBrand(region) {
    var active = document.activeElement;
    return active && region && typeof region.contains === 'function' && region.contains(active) &&
      active.getAttribute ? active.getAttribute('data-pw-chart-brand') : null;
  }

  function restoreLegendFocus(region, brand) {
    if (!brand) return;
    var button = legendButtons(region).filter(function (candidate) {
      return candidate.getAttribute('data-pw-chart-brand') === brand;
    })[0];
    if (button && typeof button.focus === 'function') button.focus();
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

  function renderHeadline(narrative) {
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
      detail.textContent = zh ? '更多' : 'more';
      headline.appendChild(detail);
      article.appendChild(headline);

      var secondary = document.createElement('div');
      secondary.className = 'headline-item-secondary';
      secondary.setAttribute('data-pw-headline-item-secondary', '');
      secondary.setAttribute('id', detailId);
      secondary.hidden = true;
      var secondaryCopy = document.createElement('span');
      secondaryCopy.setAttribute('data-pw-headline-secondary-copy', '');
      secondaryCopy.textContent = item.secondary;
      secondary.appendChild(secondaryCopy);
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
    var zh = isZhLocale(currentLocale(getHomeChartRegion()));
    detail.textContent = expanded ? (zh ? '收起' : 'less') : (zh ? '更多' : 'more');
    if (restoreFocus && typeof detail.focus === 'function') detail.focus();
  }

  function wireHeadlineDisclosure() {
    document.addEventListener('click', function (event) {
      if (!event.target || !event.target.closest) return;
      var article = event.target.closest('[data-pw-headline-item]');
      if (!article) return;
      var detail = event.target.closest('[data-pw-headline-detail]');
      if (!detail) return;
      setHeadlineDetail(
        article,
        detail.getAttribute('aria-expanded') !== 'true',
        true
      );
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
    var keyboardBrand = focusedLegendBrand(region);
    try {
      if (priorChart) priorChart.destroy();
      region.innerHTML = html;
      var canvas = chartIn(region);
      if (!canvas) throw new Error('chart fragment omitted canvas');
      reconcileFocus(payload);
      renderOne(canvas);
      renderLegend(region, payload);
      paintFocus();
      restoreLegendFocus(region, keyboardBrand);
      renderPulse(region, payload.pulse);
      renderHeadline(payload.trend_narrative);
      updateProjectionStates(region, payload, true);
    } catch (error) {
      // A valid response must replace all four projections together. Restore
      // every projection if a renderer or DOM operation fails mid-commit.
      try {
        region.innerHTML = priorRegionHtml;
        if (priorPayload && chartIn(region)) {
          renderOne(chartIn(region));
          renderLegend(region, priorPayload);
          paintFocus();
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
    if (frozenPoint) {
      clearLocaleSelection();
      return Promise.resolve(false);
    }
    var requestGeneration = ++generation;
    if (activeController) activeController.abort();
    activeController = typeof AbortController === 'function' ? new AbortController() : null;
    var timedOut = false;
    var timeout = setTimeout(function () {
      if (activeController && requestGeneration === generation) {
        timedOut = true;
        activeController.abort();
      }
    }, REQUEST_TIMEOUT_MS);
    var filters = filtersForEvent(event);
    var url = '/chart.html?filters=' + encodeURIComponent(JSON.stringify(filters)) +
      '&window=' + encodeURIComponent(filters.window || 1) +
      '&locale=' + encodeURIComponent(currentLocale(region)) +
      '&timezone=' + encodeURIComponent(BROWSER_TIMEZONE);
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
      if (requestGeneration === generation && (timedOut || !error || error.name !== 'AbortError')) {
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
    if (frozenPoint) return;
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
        if (isPublicHomeRegion(region) && Chart.defaults && Chart.defaults.font) {
          Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";
        }
        renderOne(canvas);
        renderLegend(region, payload);
        if (isPublicHomeRegion(region)) {
          wireFocus(region);
          watchMotionAndVisibility(region);
          startBeaconLoop();
          paintFocus();
        }
        renderPulse(region, payload.pulse);
        renderHeadline(payload.trend_narrative);
        updateProjectionStates(region, payload, false);
        if ((payload.granularity || 'day') === 'day' &&
            payload.bucket_timezone !== BROWSER_TIMEZONE) {
          requestChart();
        }
      }
      startChartRefresh();
    }
  }

  document.addEventListener('click', function (event) {
    if (!frozenPoint || event.target === frozenPoint.canvas) return;
    endHoverFreeze();
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  document.addEventListener('pw:filter-change', requestChart);
  document.addEventListener('pw:locale-change', requestChart);
  document.addEventListener('pw:timezone-change', redrawOneDayTimeAxes);
})();
