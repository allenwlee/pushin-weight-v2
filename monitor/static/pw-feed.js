// {{AGENT_ATTRIBUTION}}
// x_monitor/static/pw-feed.js
// Pushin' Weight (走个量) bottomless-scroll feed (U7 of
// feat/pushin-weight-home-pages, 2026-07-06, U2/U3/U4/U5 of
// feat/feed-pretty-dates-and-links, 2026-07-16).
//
// - Wires IntersectionObserver on a `.feed-sentinel` element.
// - When sentinel enters viewport, fetch
//   `/feed/?cursor=<last>&filters=<encoded>&limit=50`
//   and appends rows.
// - Subscribes to `pw:filter-change` (clears the feed and re-fetches
//   from row 1); `pw:sort-change` (re-fetches with new sort / order);
//   `pw:locale-change` (re-renders the existing rows with localized
//   labels — does NOT re-fetch).
// - Sort header buttons cycle through `desc / asc / default` per click.
// - Auto-refreshes the first page every 60s (U5).

(function () {
  'use strict';

  var HARD_CAP = 500;     // mirror _FEED_HARD_CAP from the data layer
  var BATCH = 50;
  var REFRESH_MS = 60_000;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function getFeedRoot() {
    return $('section.feed[data-pw-feed]');
  }

  function buildQuery(filters, opts) {
    opts = opts || {};
    var params = [];
    if (opts.cursor) params.push('cursor=' + encodeURIComponent(opts.cursor));
    if (opts.sort) params.push('sort=' + encodeURIComponent(opts.sort));
    if (opts.order) params.push('order=' + encodeURIComponent(opts.order));
    params.push('limit=' + (opts.limit || BATCH));
    if (filters) {
      params.push('filters=' + encodeURIComponent(JSON.stringify(filters)));
    }
    return params.join('&');
  }

  function getBrandScope() {
    var root = getFeedRoot();
    if (!root) return null;
    return root.getAttribute('data-pw-brand-scope') || null;
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

  // U2: re-render visible timestamps in place. Used on init() and
  // every auto-refresh tick so the relative-time chips stay current
  // even when the page doesn't reload.
  function formatVisibleTimestamps() {
    var now = new Date();
    $$('[data-pw-feed-row]').forEach(function (tr) {
      var iso = tr.getAttribute('data-created-at-iso');
      if (!iso) return;
      var a = tr.querySelector('a.feed-date-link');
      if (a) {
        a.textContent = formatRelative(iso, now);
        a.setAttribute('title', formatLocalTooltip(iso));
      }
    });
  }

  // Exposed for unit tests (Node).
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { formatRelative: formatRelative, formatLocalTooltip: formatLocalTooltip };
    return;
  }

  function renderRow(row) {
    var tr = document.createElement('tr');
    tr.setAttribute('data-pw-feed-row', '');
    tr.setAttribute('data-tweet-id', row.tweet_id || '');
    tr.setAttribute('data-created-at-iso', row.created_at_iso || '');
    tr.innerHTML = renderRowHtml(row);
    return tr;
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

  function renderRowHtml(row) {
    var now = new Date();
    var relTime = formatRelative(row.created_at_iso || row.created_at, now);
    var tooltip = formatLocalTooltip(row.created_at_iso || row.created_at);
    var dateCell = '<a class="feed-date-link" ' +
      'href="https://x.com/i/status/' + escapeHtml(row.tweet_id || '') + '" ' +
      'target="_blank" rel="noopener noreferrer" ' +
      'title="' + escapeHtml(tooltip) + '">' + escapeHtml(relTime) + '</a>';
    var langSub = row.lang_detected
      ? '<div class="lang-sub">translated from: [' + escapeHtml(row.lang_detected) + ']</div>'
      : '';
    var brandPills = (row.brands || []).map(function (b) {
      var label = b.display_name_zh_cn || b.display_name_en || b.nickname || '';
      return '<span class="pill">' + escapeHtml(label) + '</span>';
    }).join('');
    // U4: per-brand grouped classifications.
    var classBlocks = [];
    var nicknames = row.brand_nicknames || [];
    var byBrand = row.classifications || {};
    var brandMeta = {};
    (row.brands || []).forEach(function (b) {
      if (b && b.nickname) brandMeta[b.nickname] = b;
    });
    nicknames.forEach(function (nick) {
      var cls = byBrand[nick] || {};
      var meta = brandMeta[nick] || {};
      var headerLabel = meta.display_name_zh_cn || meta.display_name_en || meta.nickname || nick;
      var lines = [];
      var pts = cls.post_types || [];
      var disc = cls.discourse || [];
      var sents = cls.sentiments || [];
      if (pts.length) {
        lines.push(
          '<span class="cls-label">types:</span> ' +
          pts.map(function (v) { return '<span class="pill">' + escapeHtml(v) + '</span>'; }).join('')
        );
      }
      if (disc.length) {
        lines.push(
          '<span class="cls-label">discourses:</span> ' +
          disc.map(function (v) {
            return v == null
              ? '<span class="pill muted">—</span>'
              : '<span class="pill">' + escapeHtml(v) + '</span>';
          }).join('')
        );
      }
      if (sents.length) {
        lines.push(
          '<span class="cls-label">sentiments:</span> ' +
          sents.map(function (v) { return '<span class="pill">' + escapeHtml(v) + '</span>'; }).join('')
        );
      }
      if (cls.cn_nationalism) {
        lines.push('<span class="cls-label">cn:</span> <span class="pill muted">' + escapeHtml(cls.cn_nationalism) + '</span>');
      }
      if (cls.us_nationalism) {
        lines.push('<span class="cls-label">us:</span> <span class="pill muted">' + escapeHtml(cls.us_nationalism) + '</span>');
      }
      classBlocks.push(
        '<div class="cls-block">' +
          '<span class="cls-brand">' + escapeHtml(headerLabel) + '</span>' +
          (lines.length ? lines.join('<br>') : '') +
        '</div>'
      );
    });
    if (row.unsanctioned) {
      classBlocks.push('<div class="cls-block"><span class="pill flagged">unsanctioned</span></div>');
    }
    var handleRaw = (row.account && row.account.handle) || '';
    var handleLabel = handleRaw || '@unknown';
    var handleCell = handleRaw
      ? '<a class="feed-handle-link" ' +
          'href="https://x.com/' + escapeHtml(cleanHandle(handleRaw)) + '" ' +
          'target="_blank" rel="noopener noreferrer">' +
          escapeHtml(handleLabel) + '</a>'
      : escapeHtml(handleLabel);
    var role = (row.account && row.account.role) || '';
    var roleLabel = (row.account && row.account.role_label) || role;
    return (
      '<td class="muted-cell">' + dateCell + '</td>' +
      '<td>' + brandPills + '</td>' +
      '<td>' + langSub +
        '<div class="cell-truncated" data-pw-cell-truncated>' + escapeHtml(row.text_translated || '') + '</div>' +
        '<div class="muted-cell">★ ' + (row.like_count || 0) + '</div>' +
      '</td>' +
      '<td><div class="cell-truncated" data-pw-cell-truncated>' + escapeHtml(row.text || '') + '</div></td>' +
      '<td>' + classBlocks.join('') + '</td>' +
      '<td>' + handleCell + ' · <span class="pill role-' + escapeHtml(role) + '">' + escapeHtml(roleLabel) + '</span></td>'
    );
  }

  function attachCellClickHandlers(root) {
    $$('td.is-expanded', root).forEach(function (td) { td.classList.remove('is-expanded'); });
    $$('[data-pw-cell-truncated]', root).forEach(function (el) {
      el.onclick = function (e) {
        var td = el.closest('td');
        if (!td) return;
        var wasExpanded = td.classList.contains('is-expanded');
        // Collapse all in this row.
        var tr = td.closest('tr');
        if (tr) {
          $$('td.is-expanded', tr).forEach(function (other) { other.classList.remove('is-expanded'); });
        }
        if (!wasExpanded) td.classList.add('is-expanded');
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
  };

  function readCursorFromLastRow(tbody) {
    var rows = tbody.querySelectorAll('[data-pw-feed-row]');
    if (rows.length === 0) return null;
    var last = rows[rows.length - 1];
    var twid = last.getAttribute('data-tweet-id');
    var iso = last.getAttribute('data-created-at-iso');
    if (!iso || !twid) return null;
    return iso + '|' + twid;
  }

  function fetchBatch(filters) {
    var url = '/feed/?' + buildQuery(filters || {}, {
      cursor: state.cursor,
      sort: state.sort,
      order: state.order,
      limit: BATCH,
    });
    var brandScope = getBrandScope();
    if (brandScope) url += '&brand=' + encodeURIComponent(brandScope);
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); });
  }

  function clearAndRefetch() {
    var root = getFeedRoot();
    if (!root) return;
    var tbody = $('[data-pw-feed-body]', root);
    if (!tbody) return;
    state.cursor = null;
    state.total = 0;
    state.exhausted = false;
    // Clear the body but preserve the first batch (already rendered by
    // Jinja). For the simplest behavior, refetch from the server and
    // replace the entire tbody. U4 (2026-07-16): pass the current
    // control-panel filter so the immediate refetch honors it (was
    // previously fetching the un-filtered feed on every toggle).
    var filters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
    fetchBatch(filters).then(function (payload) {
      if (!payload || !payload.rows) return;
      tbody.innerHTML = '';
      payload.rows.forEach(function (row) {
        tbody.appendChild(renderRow(row));
      });
      attachCellClickHandlers(tbody);
      state.cursor = payload.next_cursor;
      state.total = payload.rows.length;
      if (!state.cursor) {
        state.exhausted = true;
        showEnd();
      } else {
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
    var tbody = $('[data-pw-feed-body]', root);
    if (!tbody) return;

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        if (state.fetching || state.exhausted) return;
        if (state.total >= HARD_CAP) {
          state.exhausted = true;
          showEnd();
          return;
        }
        state.fetching = true;
        // Read the current cursor from the last rendered row
        // (covers filter changes that re-fetched the first page).
        state.cursor = readCursorFromLastRow(tbody);
        var filters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
        fetchBatch(filters).then(function (payload) {
          if (!payload || !payload.rows) {
            state.fetching = false;
            return;
          }
          payload.rows.forEach(function (row) {
            tbody.appendChild(renderRow(row));
          });
          attachCellClickHandlers(tbody);
          formatVisibleTimestamps();
          state.cursor = payload.next_cursor;
          state.total += payload.rows.length;
          state.fetching = false;
          if (!state.cursor || state.total >= HARD_CAP) {
            state.exhausted = true;
            showEnd();
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
    document.addEventListener('pw:filter-change', function () {
      clearAndRefetch();
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
  function startAutoRefresh() {
    stopAutoRefresh();
    refreshTimer = setInterval(function () {
      if (document.hidden) return;
      var root = getFeedRoot();
      if (!root) return;
      var tbody = $('[data-pw-feed-body]', root);
      if (!tbody) return;
      // Refetch the first page and replace the body. U4: pass the
      // current control-panel filter so the auto-refresh keeps the
      // feed aligned with whatever the user has selected.
      state.cursor = null;
      var filters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
      fetchBatch(filters).then(function (payload) {
        if (!payload || !payload.rows) return;
        tbody.innerHTML = '';
        payload.rows.forEach(function (row) {
          tbody.appendChild(renderRow(row));
        });
        attachCellClickHandlers(tbody);
        formatVisibleTimestamps();
        state.cursor = payload.next_cursor;
        state.total = payload.rows.length;
        if (!state.cursor) {
          state.exhausted = true;
          showEnd();
        } else {
          state.exhausted = false;
          hideEnd();
        }
      });
    }, REFRESH_MS);
  }
  function stopAutoRefresh() {
    if (refreshTimer != null) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  function init() {
    if (!getFeedRoot()) return;
    var tbody = $('[data-pw-feed-body]');
    if (tbody) attachCellClickHandlers(tbody);
    // Format the server-rendered timestamps immediately so the
    // user never sees the raw Twitter-format string.
    formatVisibleTimestamps();
    // Click anywhere outside the expanded cell collapses it.
    document.addEventListener('click', function (e) {
      if (!e.target.closest('[data-pw-cell-truncated]')) {
        $$('td.is-expanded').forEach(function (td) { td.classList.remove('is-expanded'); });
      }
    });
    wireSentinel();
    wireSortHeaders();
    wireFilterChange();
    startAutoRefresh();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
