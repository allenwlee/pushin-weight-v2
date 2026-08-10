// v22 timezone pill: browser-local time ⇄ America/Los_Angeles.
(function () {
  'use strict';

  var root = document.querySelector('[data-tz-widget]');
  if (!root || !window.Intl || !Intl.DateTimeFormat) return;

  var CA_TIMEZONE = 'America/Los_Angeles';
  var active = root.getAttribute('data-tz-active') === 'ca' ? 'ca' : 'local';
  var CA_ICON_HTML = '<span class="tz-ca-icon" title="California" aria-label="California">CA</span>';

  function zoneTime(date, timezone) {
    var options = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
    if (timezone) options.timeZone = timezone;
    return new Intl.DateTimeFormat('en-GB', options).format(date);
  }

  function zoneHour(timezone) {
    var options = { hour: 'numeric', hourCycle: 'h23' };
    if (timezone) options.timeZone = timezone;
    var hour = new Intl.DateTimeFormat('en-GB', options).formatToParts(new Date()).find(function (part) {
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
    return key === 'zh_cn' || key === 'zh-CN' || key === 'zh-cn' ? '本地' : 'local';
  }

  function renderFeedStamps() {
    var now = Date.now();
    var timezone = activeTimezone();
    document.querySelectorAll('.feed-row[data-posted-offset-min]').forEach(function (row) {
      var minutes = Number(row.getAttribute('data-posted-offset-min')) || 0;
      var stamp = row.querySelector('[data-ts-abs]');
      if (!stamp) return;
      if (minutes >= 24 * 60) {
        stamp.textContent = '';
        stamp.hidden = true;
        return;
      }
      stamp.hidden = false;
      var time = zoneTime(new Date(now - minutes * 60 * 1000), timezone);
      if (active === 'ca') stamp.innerHTML = '(' + time + ' ' + CA_ICON_HTML + ')';
      else stamp.textContent = '(' + time + ' ' + localLabel() + ')';
    });
  }

  function render() {
    var timezone = activeTimezone();
    var time = zoneTime(new Date(), timezone);
    root.setAttribute('data-tz-active', active);
    document.documentElement.setAttribute('data-tz-mode', active);
    var emoji = root.querySelector('[data-tz-emoji]');
    var timeElement = root.querySelector('[data-tz-time]');
    var zone = root.querySelector('[data-tz-zone]');
    var pair = root.querySelector('[data-tz-pair]');
    if (emoji) emoji.textContent = dayEmoji(zoneHour(timezone));
    if (timeElement) timeElement.textContent = time;
    if (zone) {
      zone.classList.toggle('is-ca', active === 'ca');
      if (active === 'ca') zone.innerHTML = CA_ICON_HTML;
      else zone.textContent = localLabel();
    }
    if (pair) pair.innerHTML = active === 'ca' ? '⇄ ' + localLabel() : '⇄ ' + CA_ICON_HTML;
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
