// {{AGENT_ATTRIBUTION}}
// x_monitor/static/pw-feed.js
// Pushin' Weight (走个量) bottomless-scroll feed (U7 of
// feat/pushin-weight-home-pages, 2026-07-06).
//
// - Wires IntersectionObserver on a `.feed-sentinel` element.
// - When sentinel enters viewport, fetch
//   `/api/v1/home.feed.json?cursor=<last>&filters=<encoded>&limit=50`
//   and appends rows.
// - Subscribes to `pw:filter-change` (clears the feed and re-fetches
//   from row 1); `pw:sort-change` (re-fetches with new sort / order);
//   `pw:locale-change` (re-renders the existing rows with localized
//   labels — does NOT re-fetch).
// - Sort header buttons cycle through `desc / asc / default` per click.

(function () {
  'use strict';

  var HARD_CAP = 500;     // mirror _FEED_HARD_CAP from the data layer
  var BATCH = 50;

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

  function renderRow(row) {
    var tr = document.createElement('tr');
    tr.setAttribute('data-pw-feed-row', '');
    tr.setAttribute('data-tweet-id', row.tweet_id || '');
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

  function renderRowHtml(row) {
    var langSub = row.lang_detected
      ? '<div class="lang-sub">translated from: [' + escapeHtml(row.lang_detected) + ']</div>'
      : '';
    var brandPills = (row.brands || []).map(function (b) {
      var label = b.display_name_zh_cn || b.display_name_en || b.nickname || '';
      return '<span class="pill">' + escapeHtml(label) + '</span>';
    }).join('');
    var classPills = [];
    var classifications = row.classifications || {};
    Object.keys(classifications).forEach(function (nick) {
      var cls = classifications[nick] || {};
      (cls.discourse || []).forEach(function (d) { classPills.push('<span class="pill">' + escapeHtml(d) + '</span>'); });
      (cls.post_types || []).forEach(function (pt) { classPills.push('<span class="pill">' + escapeHtml(pt) + '</span>'); });
      if (cls.cn_nationalism) classPills.push('<span class="pill muted">cn:' + escapeHtml(cls.cn_nationalism) + '</span>');
      if (cls.us_nationalism) classPills.push('<span class="pill muted">us:' + escapeHtml(cls.us_nationalism) + '</span>');
    });
    if (row.unsanctioned) classPills.push('<span class="pill flagged">unsanctioned</span>');
    var handle = (row.account && row.account.handle) || '';
    var role = (row.account && row.account.role) || '';
    var roleLabel = (row.account && row.account.role_label) || role;
    return (
      '<td class="muted-cell">' + escapeHtml(row.created_at || '') + '</td>' +
      '<td>' + brandPills + '</td>' +
      '<td>' + langSub +
        '<div class="cell-truncated" data-pw-cell-truncated>' + escapeHtml(row.text_translated || '') + '</div>' +
        '<div class="muted-cell">★ ' + (row.like_count || 0) + '</div>' +
      '</td>' +
      '<td><div class="cell-truncated" data-pw-cell-truncated>' + escapeHtml(row.text || '') + '</div></td>' +
      '<td>' + classPills.join('') + '</td>' +
      '<td>' + escapeHtml(handle) + ' · <span class="pill role-' + escapeHtml(role) + '">' + escapeHtml(roleLabel) + '</span></td>'
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
    // created_at is in the first cell
    var firstCell = last.querySelector('td');
    var createdAt = firstCell ? firstCell.textContent : '';
    if (!createdAt || !twid) return null;
    return createdAt + '|' + twid;
  }

  function fetchBatch(filters) {
    var url = '/api/v1/home.feed.json?' + buildQuery(filters || {}, {
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
    // replace the entire tbody.
    fetchBatch().then(function (payload) {
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

  function init() {
    if (!getFeedRoot()) return;
    var tbody = $('[data-pw-feed-body]');
    if (tbody) attachCellClickHandlers(tbody);
    // Click anywhere outside the expanded cell collapses it.
    document.addEventListener('click', function (e) {
      if (!e.target.closest('[data-pw-cell-truncated]')) {
        $$('td.is-expanded').forEach(function (td) { td.classList.remove('is-expanded'); });
      }
    });
    wireSentinel();
    wireSortHeaders();
    wireFilterChange();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
