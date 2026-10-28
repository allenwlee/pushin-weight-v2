// V24 split timezone pill: browser-local and a useful comparison clock.
(function () {
  'use strict';

  var CA_TIMEZONE = 'America/Los_Angeles';
  var BEIJING_TIMEZONE = 'Asia/Shanghai';

  function isZhLocale(locale) {
    return ['zh_cn', 'zh-cn', 'zh_hans', 'zh-hans'].indexOf(
      String(locale || '').toLowerCase()
    ) !== -1;
  }

  function comparisonForLocalTimezone(localTimezone) {
    if (localTimezone === CA_TIMEZONE) {
      return {
        key: 'beijing',
        timezone: BEIJING_TIMEZONE,
        iconClass: 'tz-bj-icon',
        iconSymbol: 'icon-beijing',
      };
    }
    return {
      key: 'california',
      timezone: CA_TIMEZONE,
      iconClass: 'tz-ca-icon',
      iconSymbol: 'icon-california',
    };
  }

  function timezoneCopy(locale, comparison) {
    var zh = isZhLocale(locale);
    var ja = ['ja', 'ja-jp'].indexOf(String(locale || '').toLowerCase()) !== -1;
    var beijing = comparison.key === 'beijing';
    var comparisonName = beijing
      ? (zh ? '北京' : 'Beijing')
      : (zh ? '加州' : 'California');
    return {
      localLabel: zh ? '本地' : ja ? '現地' : 'local',
      shortLabel: beijing ? comparisonName : (zh ? '加州' : 'CA'),
      comparisonName: comparisonName,
      toggleTitle: zh
        ? '切换 本地 ⇄ ' + comparisonName + '时间'
        : 'Toggle local ⇄ ' + comparisonName + ' time',
    };
  }

  // General-style pages show English times on the 12-hour clock ("8:17pm") and
  // Chinese and Japanese on the 24-hour clock ("20:17"). Other pages keep the
  // 24-hour clock everywhere.
  function generalStylePage() {
    return Boolean(typeof document !== 'undefined' && document.body &&
      document.body.classList && document.body.classList.contains('pw-general'));
  }

  function usesTwelveHourClock(locale) {
    var key = String(locale || '').toLowerCase();
    return key === 'en' || key.indexOf('en-') === 0 || key.indexOf('en_') === 0;
  }

  var clockFormatters = Object.create(null);
  var dateFormatters = Object.create(null);

  function clockText(date, locale, timeZone, twelveHour) {
    var instant = date instanceof Date ? date : new Date(date);
    if (!Number.isFinite(instant.getTime())) return '';
    var twelve = twelveHour === undefined ? usesTwelveHourClock(locale) : twelveHour;
    var cacheKey = (twelve ? '12|' : '24|') + (timeZone || '');
    if (!clockFormatters[cacheKey]) {
      var options = twelve
        ? { hour: 'numeric', minute: '2-digit', hour12: true }
        : { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
      if (timeZone) options.timeZone = timeZone;
      clockFormatters[cacheKey] = new Intl.DateTimeFormat(twelve ? 'en-US' : 'en-GB', options);
    }
    var text = clockFormatters[cacheKey].format(instant);
    return twelve
      ? text.replace(/[\s\u202f\u00a0]?([AP])M$/i, function (_match, letter) {
          return letter.toLowerCase() + 'm';
        })
      : text;
  }

  // One-day axis ticks: the last tick is the end of the last bucket and the
  // others step back whole hours (1, 2, 3, 4 or 6) so each step gets at least
  // 42px. Buckets are drawn at their end, so a tick's value is the index of
  // the bucket that ends at that instant.
  function oneDayTicks(labels, width, maxTicks) {
    if (!Array.isArray(labels) || labels.length < 2) return [];
    var first = Date.parse(labels[0]);
    var step = Date.parse(labels[1]) - first;
    if (!Number.isFinite(first) || !(step > 0)) return [];
    var end = Date.parse(labels[labels.length - 1]) + step;
    if (!Number.isFinite(end)) return [];
    var spanHours = (end - first) / 3600000;
    var limit = maxTicks || Infinity;
    var hours = [1, 2, 3, 4, 6].filter(function (candidate) {
      return (Number(width) || 0) * candidate / spanHours >= 42 &&
        spanHours / candidate <= limit;
    })[0] || 6;
    var ticks = [];
    for (var instant = end; instant >= first + step; instant -= hours * 3600000) {
      ticks.unshift({ value: Math.round((instant - first) / step) - 1, instant: instant });
    }
    return ticks;
  }

  function dateLocale(locale) {
    var key = String(locale || '').toLowerCase();
    if (key.indexOf('zh') === 0) return 'zh-CN';
    if (key.indexOf('ja') === 0) return 'ja-JP';
    return null;
  }

  // 7/30/365-day axis dates: "Oct 18" / "10月18日"; 365 days "Dec 2025" / "2025年12月".
  function dateLabel(isoDay, locale, yearly) {
    var instant = Date.parse(String(isoDay) + 'T00:00:00Z');
    if (!Number.isFinite(instant)) return '';
    var cjk = dateLocale(locale);
    var cacheKey = (cjk || 'en-US') + (yearly ? '|month' : '|day');
    if (!dateFormatters[cacheKey]) {
      var options = yearly
        ? { year: 'numeric', month: cjk ? 'long' : 'short', timeZone: 'UTC' }
        : { month: cjk ? 'long' : 'short', day: 'numeric', timeZone: 'UTC' };
      dateFormatters[cacheKey] = new Intl.DateTimeFormat(cjk || 'en-US', options);
    }
    return dateFormatters[cacheKey].format(instant);
  }

  // Tick indices for date axes: the latest day plus every day (7 days), every
  // fifth day (30 days), or every other month start (365 days), counted back.
  function dateTickIndices(labels) {
    if (!Array.isArray(labels) || !labels.length) return [];
    var last = labels.length - 1;
    var picks = [];
    if (labels.length > 90) {
      var starts = [];
      labels.forEach(function (label, index) { if (/-01$/.test(String(label))) starts.push(index); });
      for (var i = starts.length - 1; i >= 0; i -= 2) picks.unshift(starts[i]);
      return picks;
    }
    var every = Math.ceil(labels.length / 7);
    for (var j = last; j >= 0; j -= every) picks.unshift(j);
    return picks;
  }

  var axisHelpers = {
    clockText: clockText,
    oneDayTicks: oneDayTicks,
    dateLabel: dateLabel,
    dateTickIndices: dateTickIndices,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Object.assign({
      comparisonForLocalTimezone: comparisonForLocalTimezone,
      timezoneCopy: timezoneCopy,
    }, axisHelpers);
  }
  if (typeof window !== 'undefined') window.pwTime = axisHelpers;

  var root = document.querySelector('[data-tz-widget]');
  if (!root || !window.Intl || !Intl.DateTimeFormat) return;

  var localTimezone = '';
  try {
    localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  } catch (_error) { /* comparison defaults to California */ }
  var comparison = comparisonForLocalTimezone(localTimezone);
  var savedMode = window.pwFilter && window.pwFilter.getPreference
    ? window.pwFilter.getPreference('timezone')
    : null;
  var active = savedMode === 'ca' || (savedMode == null && root.getAttribute('data-tz-active') === 'ca')
    ? 'ca'
    : 'local';
  var formattersByZone = Object.create(null);

  function currentLocale() {
    return document.body && document.body.getAttribute
      ? (document.body.getAttribute('data-pw-locale') || 'en')
      : 'en';
  }

  function formattersFor(timezone) {
    var key = timezone || 'local';
    if (!formattersByZone[key]) {
      var timeOptions = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
      var hourOptions = { hour: 'numeric', hourCycle: 'h23' };
      if (timezone) {
        timeOptions.timeZone = timezone;
        hourOptions.timeZone = timezone;
      }
      formattersByZone[key] = {
        time: new Intl.DateTimeFormat('en-GB', timeOptions),
        hour: new Intl.DateTimeFormat('en-GB', hourOptions),
      };
    }
    return formattersByZone[key];
  }

  function setText(element, value) {
    if (element && element.textContent !== value) element.textContent = value;
  }

  function setHTML(element, value) {
    if (element && element.innerHTML !== value) element.innerHTML = value;
  }

  function zoneTime(date, timezone) {
    if (generalStylePage()) return clockText(date, currentLocale(), timezone);
    return formattersFor(timezone).time.format(date);
  }

  function zoneHour(date, timezone) {
    var hour = formattersFor(timezone).hour.formatToParts(date).find(function (part) {
      return part.type === 'hour';
    });
    return hour ? Number(hour.value) : 0;
  }

  function renderIcon(symbolId, className) {
    return window.pwIcon && typeof window.pwIcon.render === 'function'
      ? window.pwIcon.render(symbolId, className)
      : '';
  }

  function daySymbol(hour) {
    if (hour >= 5 && hour < 8) return 'icon-sunrise';
    if (hour >= 8 && hour < 17) return 'icon-day';
    if (hour >= 17 && hour < 20) return 'icon-dusk';
    return 'icon-night';
  }

  function activeTimezone() {
    return active === 'ca' ? comparison.timezone : undefined;
  }

  function comparisonIconHTML(copy) {
    return '<span class="' + comparison.iconClass + '" title="' + copy.comparisonName +
      '" aria-label="' + copy.comparisonName + '">' +
      renderIcon(comparison.iconSymbol, 'tz-place-icon') + '</span>';
  }

  function renderFeedStamps(copy) {
    var reviewNow = document.body && document.body.getAttribute('data-pw-feed-now');
    var parsedReviewNow = reviewNow ? new Date(reviewNow).getTime() : NaN;
    var now = Number.isNaN(parsedReviewNow) ? Date.now() : parsedReviewNow;
    var timezone = activeTimezone();
    document.querySelectorAll('.feed-row[data-created-at-iso]').forEach(function (row) {
      var createdAt = new Date(row.getAttribute('data-created-at-iso') || '');
      var stamp = row.querySelector('.ts-abs');
      if (!stamp || Number.isNaN(createdAt.getTime())) return;
      var minutes = Math.max(0, Math.floor((now - createdAt.getTime()) / (60 * 1000)));
      if (minutes >= 24 * 60) {
        if (stamp.textContent !== '') stamp.textContent = '';
        if (!stamp.hidden) stamp.hidden = true;
        return;
      }
      if (stamp.hidden) stamp.hidden = false;
      var time = zoneTime(createdAt, timezone);
      if (active === 'ca') setHTML(stamp, '(' + time + ' ' + comparisonIconHTML(copy) + ')');
      else setText(stamp, '(' + time + ' ' + copy.localLabel + ')');
    });
  }

  function notifyTimezoneChange(copy) {
    document.dispatchEvent(new CustomEvent('pw:timezone-change', {
      detail: {
        mode: active,
        comparison: comparison.key,
        timezone: comparison.timezone,
        localLabel: copy.localLabel,
        comparisonLabel: copy.shortLabel,
      },
    }));
  }

  function render(notify) {
    var now = new Date();
    var copy = timezoneCopy(currentLocale(), comparison);
    root.setAttribute('data-tz-active', active);
    root.setAttribute('data-tz-comparison', comparison.key);
    root.setAttribute('title', copy.toggleTitle);
    root.setAttribute('aria-label', copy.toggleTitle);
    document.documentElement.setAttribute('data-tz-mode', active);
    var localChoice = root.querySelector('[data-tz-choice="local"]');
    var comparisonChoice = root.querySelector('[data-tz-choice="ca"]');
    var localEmoji = root.querySelector('[data-tz-local-emoji]');
    var comparisonEmoji = root.querySelector('[data-tz-comparison-emoji]');
    var localTime = root.querySelector('[data-tz-local-time]');
    var comparisonTime = root.querySelector('[data-tz-comparison-time]');
    var localLabelElement = root.querySelector('[data-tz-local-label]');
    var comparisonIcon = root.querySelector('[data-tz-comparison-icon]');
    if (localChoice) localChoice.classList.toggle('is-selected', active === 'local');
    if (comparisonChoice) comparisonChoice.classList.toggle('is-selected', active === 'ca');
    setHTML(localEmoji, renderIcon(daySymbol(zoneHour(now)), 'tz-daypart-icon'));
    setHTML(comparisonEmoji, renderIcon(
      daySymbol(zoneHour(now, comparison.timezone)),
      'tz-daypart-icon'
    ));
    setText(localTime, zoneTime(now));
    setText(comparisonTime, zoneTime(now, comparison.timezone));
    setText(localLabelElement, copy.localLabel);
    if (comparisonIcon) {
      comparisonIcon.classList.remove('tz-ca-icon', 'tz-bj-icon');
      comparisonIcon.classList.add(comparison.iconClass);
      comparisonIcon.setAttribute('title', copy.comparisonName);
      comparisonIcon.setAttribute('aria-label', copy.comparisonName);
      setHTML(comparisonIcon, renderIcon(comparison.iconSymbol, 'tz-place-icon'));
    }
    renderFeedStamps(copy);
    if (notify) notifyTimezoneChange(copy);
  }

  function setMode(mode) {
    active = mode === 'ca' ? 'ca' : 'local';
    if (window.pwFilter && window.pwFilter.setPreference) {
      window.pwFilter.setPreference('timezone', active);
    }
    render(true);
  }

  function toggle() {
    setMode(active === 'local' ? 'ca' : 'local');
  }

  root.addEventListener('click', toggle);
  root.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggle();
    }
  });
  document.addEventListener('pw:chrome-change', function () { render(true); });
  document.addEventListener('pw:feed-rows-mounted', function () {
    renderFeedStamps(timezoneCopy(currentLocale(), comparison));
  });
  window.__pwTz = {
    get mode() { return active; },
    getComparison: function () {
      var copy = timezoneCopy(currentLocale(), comparison);
      return {
        key: comparison.key,
        timezone: comparison.timezone,
        label: copy.comparisonName,
        shortLabel: copy.shortLabel,
        localLabel: copy.localLabel,
        iconClass: comparison.iconClass,
        iconText: comparison.iconText,
      };
    },
    comparisonHour: function (timestamp) {
      return zoneHour(new Date(timestamp), comparison.timezone);
    },
    setMode: setMode,
  };
  render(false);
  window.setInterval(function () { render(false); }, 60 * 1000);
})();
