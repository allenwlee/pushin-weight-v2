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
        iconText: '京',
      };
    }
    return {
      key: 'california',
      timezone: CA_TIMEZONE,
      iconClass: 'tz-ca-icon',
      iconText: 'CA',
    };
  }

  function timezoneCopy(locale, comparison) {
    var zh = isZhLocale(locale);
    var beijing = comparison.key === 'beijing';
    var comparisonName = beijing
      ? (zh ? '北京' : 'Beijing')
      : (zh ? '加州' : 'California');
    return {
      localLabel: zh ? '本地' : 'local',
      shortLabel: beijing ? comparisonName : (zh ? '加州' : 'CA'),
      comparisonName: comparisonName,
      toggleTitle: zh
        ? '切换 本地 ⇄ ' + comparisonName + '时间'
        : 'Toggle local ⇄ ' + comparisonName + ' time',
    };
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      comparisonForLocalTimezone: comparisonForLocalTimezone,
      timezoneCopy: timezoneCopy,
    };
  }

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
    return formattersFor(timezone).time.format(date);
  }

  function zoneHour(date, timezone) {
    var hour = formattersFor(timezone).hour.formatToParts(date).find(function (part) {
      return part.type === 'hour';
    });
    return hour ? Number(hour.value) : 0;
  }

  function dayEmoji(hour) {
    if (hour >= 5 && hour < 8) return '🌅';
    if (hour >= 8 && hour < 17) return '☀️';
    if (hour >= 17 && hour < 20) return '🌆';
    return '🌙';
  }

  function activeTimezone() {
    return active === 'ca' ? comparison.timezone : undefined;
  }

  function comparisonIconHTML(copy) {
    return '<span class="' + comparison.iconClass + '" title="' + copy.comparisonName +
      '" aria-label="' + copy.comparisonName + '">' + comparison.iconText + '</span>';
  }

  function renderFeedStamps(copy) {
    var now = Date.now();
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
    setText(localEmoji, dayEmoji(zoneHour(now)));
    setText(comparisonEmoji, dayEmoji(zoneHour(now, comparison.timezone)));
    setText(localTime, zoneTime(now));
    setText(comparisonTime, zoneTime(now, comparison.timezone));
    setText(localLabelElement, copy.localLabel);
    if (comparisonIcon) {
      comparisonIcon.classList.remove('tz-ca-icon', 'tz-bj-icon');
      comparisonIcon.classList.add(comparison.iconClass);
      comparisonIcon.setAttribute('title', copy.comparisonName);
      comparisonIcon.setAttribute('aria-label', copy.comparisonName);
      setText(comparisonIcon, comparison.iconText);
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
