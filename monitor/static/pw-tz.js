// V24 split timezone pill: browser-local and America/Los_Angeles clocks.
(function () {
  'use strict';

  var root = document.querySelector('[data-tz-widget]');
  if (!root || !window.Intl || !Intl.DateTimeFormat) return;

  var CA_TIMEZONE = 'America/Los_Angeles';
  var active = root.getAttribute('data-tz-active') === 'ca' ? 'ca' : 'local';
  var CA_ICON_HTML = '<span class="tz-ca-icon" title="California" aria-label="California">CA</span>';
  var formattersByZone = Object.create(null);

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
        hour: new Intl.DateTimeFormat('en-GB', hourOptions)
      };
    }
    return formattersByZone[key];
  }

  function setText(element, value) {
    if (element.textContent !== value) element.textContent = value;
  }

  function setHTML(element, value) {
    if (element.innerHTML !== value) element.innerHTML = value;
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
    return active === 'ca' ? CA_TIMEZONE : undefined;
  }

  function localLabel() {
    var key = document.body.getAttribute('data-pw-locale');
    return key === 'zh_cn' || key === 'zh-CN' || key === 'zh-cn' || key === 'zh_hans' || key === 'zh-hans' ? '本地' : 'local';
  }

  function renderFeedStamps() {
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
      if (active === 'ca') setHTML(stamp, '(' + time + ' ' + CA_ICON_HTML + ')');
      else setText(stamp, '(' + time + ' ' + localLabel() + ')');
    });
  }

  function render() {
    var now = new Date();
    root.setAttribute('data-tz-active', active);
    document.documentElement.setAttribute('data-tz-mode', active);
    var localChoice = root.querySelector('[data-tz-choice="local"]');
    var caChoice = root.querySelector('[data-tz-choice="ca"]');
    var localEmoji = root.querySelector('[data-tz-local-emoji]');
    var caEmoji = root.querySelector('[data-tz-ca-emoji]');
    var localTime = root.querySelector('[data-tz-local-time]');
    var caTime = root.querySelector('[data-tz-ca-time]');
    var localLabelElement = root.querySelector('[data-tz-local-label]');
    if (localChoice) localChoice.classList.toggle('is-selected', active === 'local');
    if (caChoice) caChoice.classList.toggle('is-selected', active === 'ca');
    if (localEmoji) setText(localEmoji, dayEmoji(zoneHour(now)));
    if (caEmoji) setText(caEmoji, dayEmoji(zoneHour(now, CA_TIMEZONE)));
    if (localTime) setText(localTime, zoneTime(now));
    if (caTime) setText(caTime, zoneTime(now, CA_TIMEZONE));
    if (localLabelElement) setText(localLabelElement, localLabel());
    renderFeedStamps();
  }

  function toggle() {
    active = active === 'local' ? 'ca' : 'local';
    render();
  }

  root.addEventListener('click', toggle);
  root.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggle();
    }
  });
  document.addEventListener('pw:chrome-change', render);
  window.__pwTz = { get mode() { return active; }, setMode: function (mode) { active = mode === 'ca' ? 'ca' : 'local'; render(); } };
  render();
  window.setInterval(render, 60 * 1000);
})();
