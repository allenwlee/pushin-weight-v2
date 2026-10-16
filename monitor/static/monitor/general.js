(() => {
  'use strict';
  const initial = JSON.parse(document.getElementById('general-data').textContent);
  const body = document.body;
  body.classList.add('js-enabled');
  const sharedKey = `pushinweight.home.preferences.v2:${body.dataset.preferencesNamespace}`;
  const generalKey = `${sharedKey}:general`;
  const read = key => { try { return JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch (_) { return {}; } };
  const shared = read(sharedKey), stored = read(generalKey);
  const state = {...initial.state};
  const valid = {weights: ['open', 'none'], audience: ['human', 'agent'], timezone: ['local', 'ca'], lang: ['en', 'zh-cn', 'ja']};
  const url = new URL(location.href);
  let closedNotice = initial.closed_weights_notice;
  const normalizeLocale = value => ['zh_cn', 'zh_hans', 'zh-hans'].includes(value) ? 'zh-cn' : value;
  const preferredLocale = normalizeLocale(shared.locale);
  if (!url.searchParams.has('lang') && !url.searchParams.has('locale') && valid.lang.includes(preferredLocale) && preferredLocale !== state.locale) {
    url.searchParams.set('lang', preferredLocale);
    location.replace(url);
    return;
  }
  const preferredWeights = stored.weights ?? shared.lens?.brands;
  if (!url.searchParams.has('weights') && ['closed', 'both'].includes(preferredWeights)) closedNotice = true;
  for (const [key, value] of Object.entries({weights: preferredWeights, audience: stored.audience, timezone: shared.timezone})) {
    if (!url.searchParams.has(key) && valid[key].includes(value)) state[key] = value;
  }
  let desktopExpanded = stored.navigation === 'expanded';
  let mobileOpen = false, returnFocus = null;
  const mobile = matchMedia('(max-width: 700px)');
  const nav = document.getElementById('left-navigation');
  const shell = document.querySelector('.general-shell');
  const backdrop = document.querySelector('.nav-backdrop');
  const settings = document.getElementById('general-settings');
  const comingSoon = document.getElementById('weights-coming-soon');
  let noticeAnchor = null;
  let clockStart = performance.now(), clockBase = Date.parse(initial.as_of);
  const now = () => clockBase + performance.now() - clockStart;
  const copy = state.locale === 'ja' ? {
    loading: '更新中…', failed: '更新できませんでした。前の内容を表示しています。', retry: '再試行', min: '分', hrs: '時間', days: '日', live: '開催中・終了まで', start: '開始まで', recent: '掲載されたばかり：', fetched: '取得から', ago: '前', end: '開催中・終了時刻不明', ended: '終了',
  } : state.locale === 'zh-cn' ? {
    loading: '更新中…', failed: '更新失败，仍显示上次的内容。', retry: '重试', min: '分钟', hrs: '小时', days: '天', live: '进行中：距结束', start: '距开始', recent: '刚刚收录：', fetched: '收录于', ago: '前', end: '进行中：结束时间未知', ended: '已结束',
  } : {
    loading: 'Updating…', failed: 'Could not refresh. Previous results are still shown.', retry: 'Retry', min: 'min', hrs: 'hrs', days: 'days', live: 'Live: ends in', start: 'Starts in', recent: 'Just listed', fetched: 'Fetched', ago: 'ago', end: 'Live: end time unavailable', ended: 'Ended',
  };
  const panels = new Map();
  for (const section of Object.keys(initial.feeds)) {
    panels.set(section, {node: document.querySelector(`[data-panel="${section}"]`), feed: initial.feeds[section], sequence: 0, controller: null, pending: false, lastClockRefresh: 0});
  }
  function persist() {
    try {
      const previous = read(sharedKey);
      localStorage.setItem(sharedKey, JSON.stringify({...previous, version: 2, locale: state.locale === 'zh-cn' ? 'zh_cn' : state.locale, timezone: state.timezone}));
      localStorage.setItem(generalKey, JSON.stringify({audience: state.audience, weights: state.weights, navigation: desktopExpanded ? 'expanded' : 'rail'}));
    } catch (_) { /* Storage is optional; controls remain usable. */ }
  }
  function pageUrl() {
    const next = new URL(location.href);
    next.searchParams.delete('locale');
    next.searchParams.delete('notice');
    next.searchParams.set('lang', state.locale);
    for (const key of ['weights', 'audience', 'timezone']) next.searchParams.set(key, state[key]);
    return next;
  }
  function syncControls() {
    body.dataset.audience = state.audience;
    document.querySelector('[data-identity-article]').textContent = state.locale === 'en' ? (state.audience === 'agent' ? 'an' : 'a') : '';
    document.querySelectorAll('[data-pref]').forEach(link => {
      const key = link.dataset.pref, value = link.dataset.value;
      const active = key === 'weights' && value === 'closed' ? comingSoon.open : (key === 'lang' ? state.locale : state[key]) === value;
      if (active) link.setAttribute('aria-current', 'true'); else link.removeAttribute('aria-current');
      if (key === 'weights') link.setAttribute('aria-pressed', String(active));
      const target = pageUrl();
      if (key === 'weights') {
        if (value === 'closed') target.searchParams.set('notice', 'closed-weights');
        else target.searchParams.set(key, state.weights === 'open' ? 'none' : 'open');
      } else target.searchParams.set(key, value);
      link.href = target.pathname + target.search;
    });
  }
  function positionClosedNotice() {
    if (!comingSoon.open) return;
    if (!noticeAnchor?.getClientRects().length || noticeAnchor.closest('details:not([open])')) noticeAnchor = document.querySelector('.primary-settings [data-value="closed"]');
    const anchor = noticeAnchor.getBoundingClientRect();
    const {width, height} = comingSoon.getBoundingClientRect();
    const gutter = 12, gap = 8;
    const left = Math.max(gutter, Math.min(anchor.x + anchor.width / 2 - width / 2, innerWidth - width - gutter));
    const below = anchor.bottom + gap;
    const top = below + height <= innerHeight - gutter ? below : Math.max(gutter, anchor.top - height - gap);
    comingSoon.style.left = `${left}px`;
    comingSoon.style.top = `${top}px`;
  }
  function showClosedNotice(trigger) {
    noticeAnchor = trigger || document.querySelector('.primary-settings [data-value="closed"]');
    comingSoon.dataset.anchored = '';
    if (!comingSoon.open) comingSoon.showModal();
    positionClosedNotice();
    syncControls();
  }
  window.addEventListener('resize', positionClosedNotice);
  window.addEventListener('scroll', positionClosedNotice, true);
  comingSoon.addEventListener('close', syncControls);
  document.querySelectorAll('[data-pref="weights"]').forEach(link => link.addEventListener('keydown', event => {
    if (event.key === ' ') { event.preventDefault(); link.click(); }
  }));
  function renderNav() {
    const opened = mobile.matches ? mobileOpen : desktopExpanded;
    body.dataset.nav = mobile.matches ? (mobileOpen ? 'mobile-open' : 'rail') : (desktopExpanded ? 'expanded' : 'rail');
    document.querySelectorAll('[data-nav-toggle]').forEach(button => button.setAttribute('aria-expanded', String(opened)));
    backdrop.hidden = !mobile.matches || !mobileOpen;
    shell.inert = mobile.matches && mobileOpen;
    positionClosedNotice();
  }
  function openNav() {
    returnFocus = document.activeElement;
    mobileOpen = true;
    renderNav();
    nav.querySelector('[data-nav-toggle]').focus();
  }
  function closeNav() {
    mobileOpen = false;
    settings.open = false;
    renderNav();
    if (returnFocus?.isConnected) returnFocus.focus();
  }
  document.querySelectorAll('[data-nav-toggle]').forEach(button => button.addEventListener('click', () => {
    if (mobile.matches) { if (mobileOpen) closeNav(); else openNav(); }
    else { desktopExpanded = !desktopExpanded; renderNav(); persist(); }
  }));
  backdrop.addEventListener('click', closeNav);
  mobile.addEventListener('change', () => { mobileOpen = false; settings.open = false; renderNav(); });
  document.addEventListener('keydown', event => {
    if (comingSoon.open) return;
    if (event.key === 'Escape') { if (mobileOpen) closeNav(); else settings.open = false; }
    if (event.key === 'Tab' && mobile.matches && mobileOpen) {
      const focusable = [...nav.querySelectorAll('button, a, summary, input')].filter(node => !node.disabled && node.getClientRects().length);
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  nav.querySelectorAll('a[href^="#"]').forEach(link => link.addEventListener('click', () => { if (mobile.matches) closeNav(); }));
  document.querySelector('[data-open-settings]').addEventListener('click', event => {
    event.preventDefault();
    if (mobile.matches && !mobileOpen) openNav();
    settings.open = !settings.open;
    if (settings.open) settings.querySelector('a').focus();
  });
  function status(panel, message, retry) {
    const target = panel.node.querySelector('[data-feed-status]');
    target.replaceChildren(document.createTextNode(message));
    target.hidden = !message;
    if (retry) {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = copy.retry;
      button.addEventListener('click', retry, {once: true});
      target.append(button);
    }
  }
  async function load(section, more = false) {
    const panel = panels.get(section);
    if (more && (panel.pending || !panel.feed.next_cursor)) return;
    panel.controller?.abort();
    const controller = new AbortController();
    panel.controller = controller;
    const sequence = ++panel.sequence;
    panel.pending = true;
    status(panel, copy.loading);
    panel.node.setAttribute('aria-busy', 'true');
    const target = pageUrl();
    target.pathname = '/general/feed/';
    target.searchParams.set('section', section);
    if (more) target.searchParams.set('cursor', panel.feed.next_cursor); else target.searchParams.delete('cursor');
    try {
      const response = await fetch(target, {signal: controller.signal, headers: {Accept: 'application/json'}});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (sequence !== panel.sequence) return;
      if (payload.section !== section || payload.locale !== state.locale || !Array.isArray(payload.items) || typeof payload.html !== 'string') throw new Error('Invalid feed');
      const cards = panel.node.querySelector('[data-cards]');
      const fragment = document.createElement('template');
      // This same-origin partial is rendered with Django autoescaping. Source
      // text from JSON is never passed to an HTML parser by the client.
      fragment.innerHTML = payload.html;
      if (more) {
        const existing = new Set([...cards.querySelectorAll('[data-post-id]')].map(row => row.dataset.postId));
        fragment.content.querySelectorAll('[data-post-id]').forEach(row => { if (!existing.has(row.dataset.postId)) cards.append(row); });
      } else {
        cards.replaceChildren(fragment.content);
        panel.node.querySelector('.feed-scroll').scrollTop = 0;
        clockBase = Date.parse(payload.as_of); clockStart = performance.now();
      }
      panel.feed = {next_cursor: payload.next_cursor};
      panel.node.querySelector('[data-more]').hidden = !payload.next_cursor;
      status(panel, '');
      updateTimes();
    } catch (error) {
      if (sequence === panel.sequence && error.name !== 'AbortError') status(panel, copy.failed, () => load(section, more));
    } finally {
      if (sequence === panel.sequence) { panel.pending = false; panel.node.removeAttribute('aria-busy'); }
    }
  }
  document.querySelectorAll('[data-refresh]').forEach(button => button.addEventListener('click', () => load(button.dataset.refresh)));
  document.querySelectorAll('[data-more]').forEach(button => button.addEventListener('click', () => load(button.dataset.more, true)));
  document.querySelectorAll('[data-pref]').forEach(link => link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const key = link.dataset.pref, value = link.dataset.value;
    if (key === 'lang') {
      if (value !== state.locale) { state.locale = value; persist(); }
      return;
    }
    event.preventDefault();
    if (key === 'weights' && value === 'closed') { showClosedNotice(link); return; }
    if (key === 'weights') state.weights = state.weights === 'open' ? 'none' : 'open';
    else {
      if (state[key] === value) return;
      state[key] = value;
    }
    syncControls(); persist(); history.replaceState(null, '', pageUrl());
    if (key === 'weights') for (const section of panels.keys()) load(section);
    updateTimes();
  }));
  function duration(seconds) {
    if (seconds < 3600) return `${Math.max(1, Math.floor(seconds / 60))} ${copy.min}`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} ${copy.hrs}`;
    return `${Math.floor(seconds / 86400)} ${copy.days}`;
  }
  function updateTimes() {
    for (const [section, panel] of panels) panel.node.querySelectorAll('[data-time-label]').forEach(label => {
      const target = Date.parse(label.dataset.target), remaining = (target - now()) / 1000;
      const stateName = label.dataset.state;
      let text;
      if (Number.isFinite(target)) {
        label.title = new Intl.DateTimeFormat(state.locale, {dateStyle: 'medium', timeStyle: 'short', ...(state.timezone === 'ca' ? {timeZone: 'America/Los_Angeles'} : {})}).format(target);
        if (remaining <= 0) {
          text = copy.loading;
          label.classList.remove('is-live', 'is-upcoming');
          if (!panel.pending && performance.now() - panel.lastClockRefresh > 15000) { panel.lastClockRefresh = performance.now(); load(section); }
        } else {
          text = `${['live', 'open'].includes(stateName) ? copy.live : copy.start} ${duration(remaining)}`;
          label.style.setProperty('--blink-duration', `${Math.max(.7, Math.min(8, remaining / 1800))}s`);
        }
      } else if (!stateName) {
        const age = Math.max(0, (now() - Date.parse(label.dataset.fetched)) / 1000);
        const recent = section === 'jobs' && age < 86400;
        text = `${recent ? copy.recent : copy.fetched} ${duration(age)} ${copy.ago}${recent ? '!' : ''}`;
        label.classList.toggle('is-live', recent);
      }
      if (text && label.textContent !== text) label.textContent = text;
    });
  }
  syncControls(); renderNav(); updateTimes();
  if (closedNotice) {
    comingSoon.removeAttribute('open');
    showClosedNotice();
    persist();
    history.replaceState(null, '', pageUrl());
  }
  if (state.weights !== initial.state.weights) for (const section of panels.keys()) load(section);
  let timer = setInterval(updateTimes, 15000);
  window.addEventListener('pagehide', () => {
    clearInterval(timer);
    for (const panel of panels.values()) panel.controller?.abort();
  });
  window.addEventListener('pageshow', event => {
    if (!event.persisted) return;
    clearInterval(timer);
    updateTimes();
    timer = setInterval(updateTimes, 15000);
  });
})();
