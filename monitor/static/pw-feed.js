// Pushin' Weight (走个量) bottomless-scroll feed.
//
// - Wires IntersectionObserver on a `.feed-sentinel` element.
// - When sentinel enters viewport, fetch
//   `/feed/?cursor=<last>&filters=<encoded>&limit=50`
//   and appends rows.
// - Subscribes to `pw:filter-change` (clears the feed and re-fetches
//   from row 1); `pw:sort-change` (re-fetches with new sort / order);
//   `pw:locale-change` (re-fetches through the same replacement path).
// - Sort header buttons cycle through `desc / asc / default` per click.
// - Auto-refreshes the first page every 60s (U5).

(function () {
  'use strict';

  var HARD_CAP = 500;     // mirror _FEED_HARD_CAP from the data layer
  var BATCH = 50;
  var REFRESH_MS = 60_000;
  var FETCH_TIMEOUT_MS = 15_000;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function getFeedRoot() {
    return $('[data-pw-feed]') || $('#feed');
  }

  function buildQuery(filters, opts) {
    opts = opts || {};
    var params = [];
    if (opts.cursor) params.push('cursor=' + encodeURIComponent(opts.cursor));
    if (opts.sort) params.push('sort=' + encodeURIComponent(opts.sort));
    if (opts.order) params.push('order=' + encodeURIComponent(opts.order));
    if (opts.locale) params.push('locale=' + encodeURIComponent(opts.locale));
    params.push('limit=' + (opts.limit || BATCH));
    if (filters) {
      params.push('filters=' + encodeURIComponent(JSON.stringify(filters)));
      params.push('window=' + encodeURIComponent(filters.window || 1));
    }
    return params.join('&');
  }

  function getBrandScope() {
    var root = getFeedRoot();
    if (!root) return null;
    return root.getAttribute('data-pw-brand-scope') || null;
  }

  function currentLocale() {
    var bodyLocale = document.body && document.body.getAttribute('data-pw-locale');
    var root = getFeedRoot();
    return bodyLocale || (root && root.getAttribute('data-pw-locale')) || 'en';
  }

  // ---------------------------------------------------------------------
  // U2: pretty relative-time formatter
  // ---------------------------------------------------------------------

  // Thresholds in seconds. <60s: "just now"; <60min: "Nm ago"; <24h:
  // "Nh ago"; <7d: weekday short (e.g. "Mon"); same year: "Mon DD";
  // older: "Mon DD YYYY".
  function formatRelative(isoOrDate, now) {
    if (!isoOrDate) return '';
    var d = (isoOrDate instanceof Date) ? isoOrDate : new Date(isoOrDate);
    if (isNaN(d.getTime())) return '';
    var n = now || new Date();
    var deltaSec = Math.max(0, Math.floor((n.getTime() - d.getTime()) / 1000));
    if (deltaSec < 60) return 'just now';
    if (deltaSec < 60 * 60) return Math.floor(deltaSec / 60) + 'm ago';
    if (deltaSec < 60 * 60 * 24) return Math.floor(deltaSec / 3600) + 'h ago';
    // 24h - 7d: weekday
    if (deltaSec < 60 * 60 * 24 * 7) {
      return d.toLocaleDateString(undefined, { weekday: 'short' });
    }
    // Same year: "Mon DD"; older: "Mon DD YYYY"
    if (d.getFullYear() === n.getFullYear()) {
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    }
    return d.toLocaleDateString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
    });
  }

  // U2: absolute timestamp in the user's local timezone, for the
  // hover tooltip. Falls back to the raw ISO string if Intl is missing.
  function formatLocalTooltip(isoOrDate) {
    if (!isoOrDate) return '';
    var d = (isoOrDate instanceof Date) ? isoOrDate : new Date(isoOrDate);
    if (isNaN(d.getTime())) return '';
    try {
      return d.toLocaleString(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      });
    } catch (e) {
      return d.toISOString();
    }
  }

  function formatRowTimestamp(row, now) {
    var iso = row.getAttribute('data-created-at-iso');
    if (!iso) return;
    var a = row.querySelector('a.feed-date-link');
    if (a) {
      a.textContent = formatRelative(iso, now);
      a.setAttribute('title', formatLocalTooltip(iso));
    }
  }

  function renderRow(row) {
    var div = document.createElement('div');
    var tint = row.tint_class || 'tint-neutral';
    div.className = 'feed-row';
    div.setAttribute('data-pw-feed-row', '');
    div.setAttribute('data-tweet-id', row.tweet_id || '');
    div.setAttribute('data-created-at-iso', row.created_at_iso || '');
    div.setAttribute('data-sentiments', (row.sentiment_keys || []).join(','));
    div.setAttribute('data-post-types', (row.post_type_keys || []).join(','));
    div.setAttribute('data-nat-cn', row.nat_cn || '');
    div.setAttribute('data-nat-us', row.nat_us || '');
    div.setAttribute('data-unsanctioned', row.unsanctioned ? '1' : '');
    div.setAttribute('data-tint', tint);
    div.innerHTML = renderRowHtml(row);
    return div;
  }

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // U3 helper: strip a leading "@" if present.
  function cleanHandle(h) {
    if (!h) return '';
    return h.replace(/^@+/, '');
  }

  // iter 14 (U5): render mockup-canon 2-column grid. Emoji + tint are
  // populated by paintSignals() once the row is in the DOM.
  function renderRowHtml(row) {
    var handleRaw = (row.account && row.account.handle) || '';
    var handleLabel = handleRaw || '@unknown';
    var handleHtml = handleRaw
      ? '<a class="feed-handle-link" ' +
          'href="https://x.com/' + escapeHtml(cleanHandle(handleRaw)) + '" ' +
          'target="_blank" rel="noopener noreferrer">' +
          escapeHtml(handleLabel) + '</a>'
      : escapeHtml(handleLabel);
    var followersPretty = (row.account && row.account.followers_pretty) || '';
    var eng = row.engagement_pretty || {};
    var tint = row.tint_class || 'tint-neutral';
    var metaText = row.meta_text || '';
    var tsAbs = row.ts_abs_text || '';
    return (
      '<div class="feed-row-shell ' + escapeHtml(tint) + '">' +
        '<div class="feed-main">' +
          '<span class="avatar" style="background: ' + escapeHtml(row.avatar_color || '') + '">' + escapeHtml(row.avatar_initials || '?') + '</span>' +
          '<div class="body">' +
            '<div class="head">' +
              '<span class="handle">' + handleHtml + '</span>' +
              '<span class="meta">· ' + escapeHtml(metaText) + ' <span class="ts-abs">' + escapeHtml(tsAbs) + '</span></span>' +
            '</div>' +
            '<div class="text" data-text-cycle role="button" tabindex="0">' +
              escapeHtml((row.text_translated || row.text_en || row.text || '').toString().slice(0, 600)) +
            '</div>' +
            '<div class="engagement">' +
              '<span class="followers">' + escapeHtml(eng.followers || '') + '</span>' +
              '<span class="likes">' + escapeHtml(eng.likes || '') + '</span>' +
              '<span class="rts">' + escapeHtml(eng.retweets || '') + '</span>' +
              '<span class="replies">' + escapeHtml(eng.replies || '') + '</span>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="feed-signals" aria-hidden="true">' +
          '<div class="sig-row sig-sentiment" data-sig-sentiment></div>' +
          '<div class="sig-row sig-post-type" data-sig-post-type></div>' +
          '<div class="sig-row sig-nat" data-sig-nat></div>' +
          '<div class="sig-row sig-unsanctioned" data-sig-unsanctioned></div>' +
        '</div>' +
      '</div>'
    );
  }

  // ---------------------------------------------------------------------
  // iter 14 (U5): signal painter — emoji + tint for the right column.
  // Mirrors mockup script (06-tier1-composed.v22-master.html ~L1660).
  // ---------------------------------------------------------------------
  var SENT_FACE = {
    positive: '\uD83D\uDE0A',  // 😊
    neutral:  '\uD83D\uDE36',  // 😶
    negative: '\uD83D\uDE41',  // 🙁
    mixed:    '\uD83D\uDE10'   // 😐
  };
  var POST_TYPE_EMOJI = {
    hands_on_usage:           '\uD83E\uDD1A', // 🤚
    performance_comparisons:  '\uD83D\uDCCA', // 📊
    buzz_releases:            '\uD83D\uDCE2', // 📢
    feedback_questions:       '\u2754',         // ❓
    advertising_marketing:    '\u5186',         // 円 (intentional, matches mockup)
    event_announcement:       '\uD83D\uDCC5'  // 📅
  };
  var SENT_ORDER = ['positive', 'neutral', 'negative', 'mixed'];
  var TYPE_ORDER = [
    'buzz_releases', 'hands_on_usage', 'performance_comparisons',
    'feedback_questions', 'advertising_marketing', 'event_announcement'
  ];

  function parseListAttr(raw) {
    if (!raw) return [];
    return raw.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
  }
  function uniqueInOrder(keys, order) {
    var seen = {}, out = [];
    order.forEach(function (k) {
      if (keys.indexOf(k) !== -1 && !seen[k]) { seen[k] = true; out.push(k); }
    });
    keys.forEach(function (k) {
      if (!seen[k]) { seen[k] = true; out.push(k); }
    });
    return out;
  }
  function paintSignals(row) {
    var sents = uniqueInOrder(parseListAttr(row.getAttribute('data-sentiments')), SENT_ORDER);
    var types = uniqueInOrder(parseListAttr(row.getAttribute('data-post-types')), TYPE_ORDER);
    var natCn = (row.getAttribute('data-nat-cn') || '').trim();
    var natUs = (row.getAttribute('data-nat-us') || '').trim();
    var showCn = natCn && natCn !== 'none';
    var showUs = natUs && natUs !== 'none';
    var elS = row.querySelector('[data-sig-sentiment]');
    if (elS) elS.textContent = sents.map(function (k) { return SENT_FACE[k] || ''; }).join('');
    var elT = row.querySelector('[data-sig-post-type]');
    if (elT) elT.textContent = types.map(function (k) { return POST_TYPE_EMOJI[k] || ''; }).join('');
    var elN = row.querySelector('[data-sig-nat]');
    if (elN) {
      if (!showCn && !showUs) { elN.innerHTML = ''; elN.classList.add('is-empty'); }
      else {
        elN.classList.remove('is-empty');
        var flags = (showCn ? '\uD83C\uDDE8\uD83C\uDDF3' : '') +
                    (showUs ? '\uD83C\uDDFA\uD83C\uDDF8' : '');
        elN.innerHTML = '<span class="sig-nat-prefix">\uD83D\uDDAC:</span> ' + flags;
      }
    }
    var elU = row.querySelector('[data-sig-unsanctioned]');
    if (elU) {
      var uns = (row.getAttribute('data-unsanctioned') || '').trim();
      var isUn = uns === '1' || uns === 'true' || uns === 'yes';
      if (isUn) { elU.classList.remove('is-empty'); elU.textContent = '\uD83D\uDEAB'; }
      else      { elU.textContent = ''; elU.classList.add('is-empty'); }
    }
  }
  function paintAllSignals(root) {
    if (!root) return;
    $$('.feed-row[data-pw-feed-row]', root).forEach(paintSignals);
  }

  function hydrateRows(rows) {
    var now = new Date();
    rows.forEach(function (row) {
      paintSignals(row);
      attachCellClickHandlers(row);
      formatRowTimestamp(row, now);
    });
  }

  function appendRows(body, rows) {
    var inserted = rows.map(renderRow);
    inserted.forEach(function (row) { body.appendChild(row); });
    hydrateRows(inserted);
    return inserted;
  }

  function renderEmptyState(body) {
    var root = getFeedRoot();
    var emptyText = root ? (root.getAttribute('data-pw-empty-text') || '') : '';
    body.innerHTML =
      '<div class="feed-row"><div class="feed-row-shell tint-neutral">' +
        '<div class="feed-main"><div class="body"><div class="text muted-cell">' +
          escapeHtml(emptyText) +
        '</div></div></div><div class="feed-signals" aria-hidden="true"></div>' +
      '</div></div>';
  }

  function replaceRows(body, rows) {
    body.innerHTML = '';
    if (!rows.length) {
      renderEmptyState(body);
      return [];
    }
    return appendRows(body, rows);
  }

  function isFeedPayload(payload) {
    if (!payload || !Array.isArray(payload.rows)) return false;
    if (!payload.rows.every(function (row) {
      return row && typeof row === 'object' && !Array.isArray(row);
    })) return false;
    if (payload.next_cursor != null && typeof payload.next_cursor !== 'string') return false;
    if (payload.has_more != null && typeof payload.has_more !== 'boolean') return false;
    return true;
  }

  function createRequestGate(options) {
    options = options || {};
    var createController = options.createController || function () {
      return typeof AbortController === 'undefined' ? null : new AbortController();
    };
    var schedule = options.setTimer || setTimeout;
    var cancelTimer = options.clearTimer || clearTimeout;
    var generation = 0;
    var active = null;

    function release(ticket) {
      if (ticket && ticket.timeoutId != null) {
        cancelTimer(ticket.timeoutId);
        ticket.timeoutId = null;
      }
    }

    return {
      start: function (timeoutMs) {
        if (active) {
          release(active);
          if (active.controller) active.controller.abort();
        }
        var controller = createController();
        var ticket = {
          generation: ++generation,
          controller: controller,
          signal: controller ? controller.signal : undefined,
          timeoutId: null,
        };
        if (controller && timeoutMs > 0) {
          ticket.timeoutId = schedule(function () { controller.abort(); }, timeoutMs);
        }
        active = ticket;
        return ticket;
      },
      isCurrent: function (ticket) {
        return active === ticket;
      },
      finish: function (ticket) {
        if (active !== ticket) return false;
        release(ticket);
        active = null;
        return true;
      },
    };
  }

  function attachCellClickHandlers(root) {
    if (!root) return;
    // iter 14: rows are divs; collapse any pre-expanded .text then wire
    // click-toggle on each .text cell. Legacy /internal/ still uses <td>
    // and is handled by its own template (unaffected by this function).
    $$('.text.is-expanded', root).forEach(function (t) { t.classList.remove('is-expanded'); });
    $$('.feed-row .text[data-text-cycle]', root).forEach(function (el) {
      el.onclick = function (e) {
        var row = el.closest('.feed-row');
        if (!row) return;
        $$('.text.is-expanded', row).forEach(function (other) { other.classList.remove('is-expanded'); });
        el.classList.add('is-expanded');
        e.stopPropagation();
      };
    });
  }

  var state = {
    cursor: null,
    total: 0,
    fetching: false,
    sort: 'created_at',
    order: 'desc',
    exhausted: false,
    committedKey: null,
  };
  var requestGate = createRequestGate();

  function snapshotFilters(filters) {
    return JSON.parse(JSON.stringify(filters || {}));
  }

  function requestKey(filters) {
    return JSON.stringify({
      filters: filters || {},
      locale: currentLocale(),
      sort: state.sort,
      order: state.order,
    });
  }

  function readCursorFromLastRow(body) {
    var rows = body.querySelectorAll('.feed-row[data-pw-feed-row]');
    if (rows.length === 0) return null;
    var last = rows[rows.length - 1];
    var twid = last.getAttribute('data-tweet-id');
    var iso = last.getAttribute('data-created-at-iso');
    if (!iso || !twid) return null;
    return iso + '|' + twid;
  }

  function fetchBatch(filters, opts, signal) {
    opts = opts || {};
    var url = '/feed/?' + buildQuery(filters || {}, {
      cursor: Object.prototype.hasOwnProperty.call(opts, 'cursor') ? opts.cursor : state.cursor,
      sort: state.sort,
      order: state.order,
      limit: BATCH,
      locale: currentLocale(),
    });
    var brandScope = getBrandScope();
    if (brandScope) url += '&brand=' + encodeURIComponent(brandScope);
    return fetch(url, { credentials: 'same-origin', signal: signal })
      .then(function (r) {
        if (!r.ok) throw new Error('feed request failed with status ' + r.status);
        return r.json();
      });
  }

  function filtersForEvent(event) {
    var filters = event && event.detail && event.detail.filters;
    if (filters && typeof filters === 'object' && !Array.isArray(filters)) return filters;
    return (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
  }

  function showFeedStatus(kind) {
    var root = getFeedRoot();
    if (!root) return;
    var status = $('[data-pw-feed-status]', root);
    if (!status) return;
    var attribute = kind === 'error' ? 'data-pw-error-text' : 'data-pw-loading-text';
    status.textContent = root.getAttribute(attribute) || status.textContent;
    status.hidden = false;
  }

  function hideFeedStatus() {
    var root = getFeedRoot();
    var status = root && $('[data-pw-feed-status]', root);
    if (status) status.hidden = true;
  }

  function runFeedRequest(filters, opts, commit) {
    var requestFilters = snapshotFilters(filters);
    var ticket = requestGate.start(FETCH_TIMEOUT_MS);
    state.fetching = true;
    showFeedStatus('loading');
    return fetchBatch(requestFilters, opts, ticket.signal)
      .then(function (payload) {
        if (!requestGate.isCurrent(ticket)) return false;
        if (!isFeedPayload(payload)) throw new Error('malformed feed payload');
        commit(payload, requestFilters);
        hideFeedStatus();
        return true;
      })
      .catch(function () {
        if (requestGate.isCurrent(ticket)) showFeedStatus('error');
        return false;
      })
      .then(function (committed) {
        if (requestGate.finish(ticket)) state.fetching = false;
        return committed;
      });
  }

  function clearAndRefetch(filters) {
    var root = getFeedRoot();
    if (!root) return;
    var body = $('[data-pw-feed-body]', root);
    if (!body) return;
    // Clear the body but preserve the first batch (already rendered by
    // Jinja). For the simplest behavior, refetch from the server and
    // replace the entire body. U4 (2026-07-16): pass the current
    // control-panel filter so the immediate refetch honors it (was
    // previously fetching the un-filtered feed on every toggle).
    var requestFilters = filters || filtersForEvent();
    return runFeedRequest(requestFilters, { cursor: null }, function (payload, committedFilters) {
      replaceRows(body, payload.rows);
      state.cursor = payload.next_cursor;
      state.total = payload.rows.length;
      state.committedKey = requestKey(committedFilters);
      if (!state.cursor) {
        state.exhausted = true;
        showEnd();
      } else {
        state.exhausted = false;
        hideEnd();
      }
    });
  }

  function showEnd() {
    var root = getFeedRoot();
    if (!root) return;
    var end = $('[data-pw-feed-end]', root);
    var sentinel = $('[data-pw-feed-sentinel]', root);
    if (end) end.hidden = false;
    if (sentinel) sentinel.hidden = true;
  }
  function hideEnd() {
    var root = getFeedRoot();
    if (!root) return;
    var end = $('[data-pw-feed-end]', root);
    var sentinel = $('[data-pw-feed-sentinel]', root);
    if (end) end.hidden = true;
    if (sentinel) sentinel.hidden = false;
  }

  function wireSentinel() {
    var root = getFeedRoot();
    if (!root) return;
    var sentinel = $('[data-pw-feed-sentinel]', root);
    if (!sentinel) return;
    var body = $('[data-pw-feed-body]', root);
    if (!body) return;

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        if (state.fetching || state.exhausted) return;
        if (state.total >= HARD_CAP) {
          state.exhausted = true;
          showEnd();
          return;
        }
        // Read the current cursor from the last rendered row
        // (covers filter changes that re-fetched the first page).
        var filters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
        if (state.committedKey !== requestKey(filters)) {
          clearAndRefetch(filters);
          return;
        }
        var cursor = readCursorFromLastRow(body);
        runFeedRequest(filters, { cursor: cursor }, function (payload, committedFilters) {
          appendRows(body, payload.rows);
          state.cursor = payload.next_cursor;
          state.total += payload.rows.length;
          state.committedKey = requestKey(committedFilters);
          if (!state.cursor || state.total >= HARD_CAP) {
            state.exhausted = true;
            showEnd();
          } else {
            state.exhausted = false;
            hideEnd();
          }
        });
      });
    }, { root: null, rootMargin: '100px' });
    observer.observe(sentinel);
  }

  function wireSortHeaders() {
    var root = getFeedRoot();
    if (!root) return;
    var thead = root.querySelector('thead');
    if (!thead) return;
    var buttons = thead.querySelectorAll('[data-pw-sort]');
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sort = btn.getAttribute('data-pw-sort');
        // Cycle: default(desc) -> asc -> desc (no "default" cycle for now)
        if (state.sort === sort) {
          state.order = state.order === 'desc' ? 'asc' : 'desc';
        } else {
          state.sort = sort;
          state.order = 'desc';
        }
        document.dispatchEvent(new CustomEvent('pw:sort-change', {
          detail: { sort: state.sort, order: state.order },
        }));
        clearAndRefetch();
      });
    });
  }

  function wireFilterChange() {
    document.addEventListener('pw:filter-change', function (event) {
      clearAndRefetch(filtersForEvent(event));
    });
    document.addEventListener('pw:locale-change', function () {
      // Re-render existing rows; the JSON shape carries
      // text_translated already, so a full refetch is the simplest
      // path (cheaper than re-rendering cells with locale logic).
      clearAndRefetch();
    });
  }

  // U5: auto-refresh the first page every REFRESH_MS so newly-arrived
  // posts surface and relative timestamps stay current. Pause when the
  // tab is hidden.
  var refreshTimer = null;
  function refreshFirstPage() {
    if (document.hidden) return;
    var root = getFeedRoot();
    if (!root) return;
    var body = $('[data-pw-feed-body]', root);
    if (!body) return;
    var filters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
    return runFeedRequest(filters, { cursor: null }, function (payload, committedFilters) {
        replaceRows(body, payload.rows);
        state.cursor = payload.next_cursor;
        state.total = payload.rows.length;
        state.committedKey = requestKey(committedFilters);
        if (!state.cursor) {
          state.exhausted = true;
          showEnd();
        } else {
          state.exhausted = false;
          hideEnd();
        }
    });
  }
  function startAutoRefresh() {
    stopAutoRefresh();
    refreshTimer = setInterval(refreshFirstPage, REFRESH_MS);
  }
  function stopAutoRefresh() {
    if (refreshTimer != null) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  function init() {
    if (!getFeedRoot()) return;
    var body = $('[data-pw-feed-body]');
    if (body) {
      var initialRows = $$('.feed-row[data-pw-feed-row]', body);
      hydrateRows(initialRows);
      state.total = initialRows.length;
      state.cursor = readCursorFromLastRow(body);
    }
    var initialFilters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
    state.committedKey = requestKey(initialFilters);
    // Format the server-rendered timestamps immediately so the
    // user never sees the raw Twitter-format string.
    // Click anywhere outside the expanded cell collapses it.
    document.addEventListener('click', function (e) {
      if (!e.target.closest('.feed-row .text[data-text-cycle]')) {
        $$('.text.is-expanded').forEach(function (el) { el.classList.remove('is-expanded'); });
      }
    });
    wireSentinel();
    wireSortHeaders();
    wireFilterChange();
    startAutoRefresh();
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      createRequestGate: createRequestGate,
      formatRelative: formatRelative,
      formatLocalTooltip: formatLocalTooltip,
      hydrateRows: hydrateRows,
      paintSignals: paintSignals,
      replaceRows: replaceRows,
      isFeedPayload: isFeedPayload,
    };
    return;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
