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
    if (opts.freezeRange) {
      params.push('freeze_start=' + encodeURIComponent(opts.freezeRange.start));
      params.push('freeze_end=' + encodeURIComponent(opts.freezeRange.end));
    }
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
    div.setAttribute(
      'data-x-url',
      row.tweet_id ? 'https://x.com/i/web/status/' + encodeURIComponent(row.tweet_id) : ''
    );
    div.setAttribute('data-created-at-iso', row.created_at_iso || '');
    div.setAttribute('data-sentiments', (row.sentiment_keys || []).join(','));
    div.setAttribute('data-post-types', (row.post_type_keys || []).join(','));
    div.setAttribute('data-nat-cn', row.nat_cn || '');
    div.setAttribute('data-nat-us', row.nat_us || '');
    div.setAttribute('data-unsanctioned', row.unsanctioned ? '1' : '');
    div.setAttribute('data-enrichment-status', row.enrichment_status || 'succeeded');
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

  function enrichmentStatusHtml(row) {
    var status = row.enrichment_status || 'succeeded';
    if (status !== 'pending' && status !== 'failed') return '';
    var label = row.enrichment_status_label || ('enrichment ' + status);
    return '<span class="enrichment-status enrichment-status-' + status +
      '" role="status">' + escapeHtml(label) + '</span>';
  }

  // U3 helper: strip a leading "@" if present.
  function cleanHandle(h) {
    if (!h) return '';
    return h.replace(/^@+/, '');
  }

  function followerBin(row) {
    var allowed = ['0-1k', '1k-10k', '10k-50k', '50k-plus'];
    if (allowed.indexOf(row.follower_bin) !== -1) return row.follower_bin;
    return '0-1k';
  }

  var FOLLOWER_ICONS = {
    '0-1k': 'icon-followers-1',
    '1k-10k': 'icon-followers-2',
    '10k-50k': 'icon-followers-3',
    '50k-plus': 'icon-followers-4'
  };

  function renderIcon(symbolId, className) {
    var renderer = typeof window !== 'undefined' && window.pwIcon;
    return renderer && typeof renderer.render === 'function'
      ? renderer.render(symbolId, className)
      : '';
  }

  function accountRoleHtml(row) {
    var account = row.account || {};
    var role = account.role || '';
    if (['official', 'staff', 'community'].indexOf(role) === -1) {
      return '<span class="account-role is-empty" aria-hidden="true"></span>';
    }
    var label = account.role_label || role;
    return '<span class="account-role role-' + role + '" role="img"' +
      ' aria-label="' + escapeHtml(label) + '" title="' + escapeHtml(label) + '">' +
      renderIcon('icon-role-badge', 'account-role-icon') + '</span>';
  }

  // Render the production two-column grid. paintSignals() fills the reserved
  // signal column after the row enters the DOM.
  function renderRowHtml(row) {
    var handleRaw = (row.account && row.account.handle) || '';
    var handleLabel = (row.account && row.account.display_name) || handleRaw || '@unknown';
    var handleHtml = handleRaw
      ? '<a class="feed-handle-link" ' +
          'href="https://x.com/' + escapeHtml(cleanHandle(handleRaw)) + '" ' +
          'target="_blank" rel="noopener noreferrer" title="' +
          escapeHtml(handleLabel) + '">' +
          escapeHtml(handleLabel) + '</a>'
      : escapeHtml(handleLabel);
    var eng = row.engagement_pretty || {};
    var followersPretty = (row.account && row.account.followers_pretty) || eng.followers || '0';
    var followersLabel = row.followers_label || (followersPretty || '0') + ' followers';
    var followerClass = followerBin(row);
    var tint = row.tint_class || 'tint-neutral';
    var metaText = row.meta_text || '';
    var tsAbs = row.ts_abs_text || '';
    var sourceText = row.text_original || row.text || '';
    var commentaryZhCn = row.commentary_zh_cn || '';
    var commentaryEn = row.commentary_en || '';
    var literalCnText = row.text_zh_cn || '';
    var englishText = row.text_en || '';
    var locale = currentLocale();
    var initialText = locale === 'zh_cn' || locale === 'zh-CN' || locale === 'zh_hans'
      ? (commentaryZhCn || literalCnText || sourceText)
      : locale === 'original'
        ? sourceText
        : (commentaryEn || englishText || sourceText);
    return (
      '<div class="feed-row-shell ' + escapeHtml(tint) + '">' +
        '<div class="feed-main">' +
          '<div class="follower-lead follower-bin-' + followerClass + '">' +
            '<div class="follower-magnitude" role="img"' +
              ' aria-label="' + escapeHtml(followersLabel) + '"' +
              ' title="' + escapeHtml(followersLabel) + '">' +
              '<span class="follower-glyph" aria-hidden="true">' +
                renderIcon(FOLLOWER_ICONS[followerClass], 'follower-icon') +
              '</span>' +
              '<span class="follower-count">' + escapeHtml(followersPretty) + '</span>' +
            '</div>' +
            accountRoleHtml(row) +
          '</div>' +
          '<div class="body">' +
            '<div class="head">' +
              '<span class="handle">' + handleHtml + '</span>' +
              '<span class="meta">· ' + escapeHtml(metaText) + ' <span class="ts-abs">' + escapeHtml(tsAbs) + '</span> ' + enrichmentStatusHtml(row) + '</span>' +
            '</div>' +
            '<div class="text" data-text-cycle role="button" tabindex="0"' +
              ' data-commentary-zh-cn="' + escapeHtml(commentaryZhCn) + '"' +
              ' data-commentary-en="' + escapeHtml(commentaryEn) + '"' +
              ' data-literal-cn="' + escapeHtml(literalCnText) + '"' +
              ' data-text-en="' + escapeHtml(englishText) + '"' +
              ' data-text-source="' + escapeHtml(sourceText) + '">' +
              escapeHtml((initialText || '').toString()) +
            '</div>' +
            '<div class="engagement">' +
              '<span class="likes">' + renderIcon('icon-heart', 'engagement-icon') + escapeHtml(eng.likes || '') + '</span>' +
              '<span class="rts">' + renderIcon('icon-repost', 'engagement-icon') + escapeHtml(eng.retweets || '') + '</span>' +
              '<span class="replies">' + renderIcon('icon-reply', 'engagement-icon') + escapeHtml(eng.replies || '') + '</span>' +
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

  // Paint Cyber-Quan symbols and existing semantic tints in the right column.
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
  function semanticIcon(family, key, className) {
    var renderer = typeof window !== 'undefined' && window.pwIcon;
    if (!renderer || typeof renderer.semanticSymbol !== 'function') return '';
    var symbolId = renderer.semanticSymbol(family, key);
    var tone = typeof renderer.semanticClass === 'function'
      ? renderer.semanticClass(family, key)
      : '';
    return symbolId ? renderIcon(symbolId, className + (tone ? ' ' + tone : '')) : '';
  }
  function paintSignals(row) {
    var sents = uniqueInOrder(parseListAttr(row.getAttribute('data-sentiments')), SENT_ORDER);
    var types = uniqueInOrder(parseListAttr(row.getAttribute('data-post-types')), TYPE_ORDER);
    var natCn = (row.getAttribute('data-nat-cn') || '').trim();
    var natUs = (row.getAttribute('data-nat-us') || '').trim();
    var showCn = natCn && natCn !== 'none';
    var showUs = natUs && natUs !== 'none';
    var elS = row.querySelector('[data-sig-sentiment]');
    if (elS) {
      elS.innerHTML = sents.map(function (key) {
        return semanticIcon('sentiment', key, 'signal-icon');
      }).join('');
    }
    var elT = row.querySelector('[data-sig-post-type]');
    if (elT) {
      elT.innerHTML = types.map(function (key) {
        return semanticIcon('post_types', key, 'signal-icon');
      }).join('');
    }
    var elN = row.querySelector('[data-sig-nat]');
    if (elN) {
      if (!showCn && !showUs) { elN.innerHTML = ''; elN.classList.add('is-empty'); }
      else {
        elN.classList.remove('is-empty');
        var regions = (showCn
          ? '<span class="nationalism-region nationalism-cn">' +
              renderIcon('icon-nationalism', 'signal-icon') + '<b>中</b></span>'
          : '') + (showUs
          ? '<span class="nationalism-region nationalism-us">' +
              renderIcon('icon-nationalism', 'signal-icon') + '<b>美</b></span>'
          : '');
        elN.innerHTML = '<span class="sig-nat-prefix">' +
          renderIcon('icon-discourse', 'signal-icon') + ':</span>' + regions;
      }
    }
    var elU = row.querySelector('[data-sig-unsanctioned]');
    if (elU) {
      var uns = (row.getAttribute('data-unsanctioned') || '').trim();
      var isUn = uns === '1' || uns === 'true' || uns === 'yes';
      if (isUn) {
        elU.classList.remove('is-empty');
        elU.innerHTML = renderIcon('icon-unsanctioned', 'signal-icon tone-negative');
      }
      else      { elU.textContent = ''; elU.classList.add('is-empty'); }
    }
  }
  function paintAllSignals(root) {
    if (!root) return;
    $$('.feed-row[data-pw-feed-row]', root).forEach(paintSignals);
  }

  // Reuses the V24 mockup's text-layer interaction on real feed rows.
  function textValue(el, name) {
    var value = el.getAttribute('data-' + name);
    return value == null || value === '' ? null : value;
  }

  function uniqueTextLayers(layers) {
    var seen = Object.create(null);
    return layers.filter(function (layer) {
      if (!layer.value || seen[layer.value]) return false;
      seen[layer.value] = true;
      return true;
    });
  }

  function textLayers(el) {
    var locale = currentLocale();
    var source = textValue(el, 'text-source');
    var english = textValue(el, 'text-en');
    if (locale === 'zh_cn' || locale === 'zh-CN' || locale === 'zh_hans') {
      var zhLayers = uniqueTextLayers([
        { key: 'synthesis', label: '综合', value: textValue(el, 'commentary-zh-cn') },
        { key: 'literal_cn', label: '直译', value: textValue(el, 'literal-cn') },
        { key: 'source', label: '原文', value: source },
      ]);
      return zhLayers.length ? zhLayers : [
        { key: 'source', label: 'src', value: source },
      ].filter(function (layer) { return layer.value; });
    }
    if (locale === 'original') {
      return uniqueTextLayers([
        { key: 'source', label: 'src', value: source },
        { key: 'en', label: 'en', value: english },
      ]);
    }
    return uniqueTextLayers([
      { key: 'synthesis', label: 'synthesis', value: textValue(el, 'commentary-en') },
      { key: 'en', label: 'en', value: english },
      { key: 'source', label: 'src', value: source },
    ]);
  }

  function renderTextLayer(el) {
    var layers = textLayers(el);
    if (!layers.length) {
      el.textContent = '';
      el.removeAttribute('data-layer-key');
      return;
    }
    var index = parseInt(el.getAttribute('data-layer-idx') || '0', 10);
    if (isNaN(index) || index < 0 || index >= layers.length) index = 0;
    var layer = layers[index];
    el.setAttribute('data-layer-idx', String(index));
    el.setAttribute('data-layer-key', layer.key);
    el.innerHTML = '<span class="text-layer-tag">' + escapeHtml(layer.label) + '</span>' +
      escapeHtml(layer.value);
  }

  function advanceTextLayer(el) {
    var layers = textLayers(el);
    if (layers.length < 2) return;
    var index = parseInt(el.getAttribute('data-layer-idx') || '0', 10);
    if (isNaN(index)) index = 0;
    el.setAttribute('data-layer-idx', String((index + 1) % layers.length));
    renderTextLayer(el);
  }

  function attachRowLink(row) {
    if (!row || typeof row.getAttribute !== 'function' ||
        typeof row.addEventListener !== 'function' ||
        row.getAttribute('data-row-link-bound') === '1') return;
    row.setAttribute('data-row-link-bound', '1');
    row.addEventListener('click', function (event) {
      if (event.defaultPrevented || !event.target || !event.target.closest) return;
      var excluded = event.target.closest(
        '.text[data-text-cycle], .handle, .feed-signals, a, button, input, label'
      );
      if (excluded && row.contains(excluded)) return;
      var url = row.getAttribute('data-x-url');
      if (!url) return;
      var opened = window.open(url, '_blank', 'noopener,noreferrer');
      if (opened) opened.opener = null;
    });
  }

  function hydrateRows(rows) {
    var now = new Date();
    rows.forEach(function (row) {
      paintSignals(row);
      attachCellClickHandlers(row);
      attachRowLink(row);
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
      cancel: function () {
        if (!active) return false;
        release(active);
        if (active.controller) active.controller.abort();
        active = null;
        return true;
      },
    };
  }

  function collapseText(el) {
    el.classList.remove('is-expanded');
    el.style.removeProperty('--feed-text-expanded-max-height');
  }

  function attachCellClickHandlers(root) {
    if (!root) return;
    // iter 14: rows are divs; collapse any pre-expanded .text then wire
    // click-toggle on each .text cell. Legacy /internal/ still uses <td>
    // and is handled by its own template (unaffected by this function).
    $$('.text.is-expanded', root).forEach(collapseText);
    $$('.feed-row .text[data-text-cycle]', root).forEach(function (el) {
      if (el.getAttribute('data-text-bound') === '1') {
        renderTextLayer(el);
        return;
      }
      el.setAttribute('data-text-bound', '1');
      el.setAttribute('data-layer-idx', '0');
      renderTextLayer(el);
      el.addEventListener('click', function (e) {
        var row = el.closest('.feed-row');
        if (!row) return;
        if (!el.classList.contains('is-expanded')) {
          var rowHeight = row.getBoundingClientRect().height;
          var textHeight = el.getBoundingClientRect().height;
          var fixedHeight = Math.max(0, rowHeight - textHeight);
          var allowedTextHeight = Math.max(textHeight, rowHeight * 3 - fixedHeight);
          el.style.setProperty(
            '--feed-text-expanded-max-height', allowedTextHeight + 'px'
          );
        }
        $$('.text.is-expanded', row).forEach(function (other) {
          if (other !== el) collapseText(other);
        });
        el.classList.add('is-expanded');
        advanceTextLayer(el);
        e.stopPropagation();
      });
      el.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        el.click();
      });
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
  var freezeRange = null;
  var pendingUnfreezeRefetch = false;

  function snapshotFilters(filters) {
    return JSON.parse(JSON.stringify(filters || {}));
  }

  function hoverFreezeFilters(filters) {
    var source = filters && typeof filters === 'object' && !Array.isArray(filters)
      ? filters
      : {};
    return {
      brands: Object.prototype.hasOwnProperty.call(source, 'brands')
        ? snapshotFilters(source.brands)
        : '__all__',
      window: 1,
    };
  }

  function requestFilters(filters) {
    return freezeRange ? hoverFreezeFilters(filters) : snapshotFilters(filters);
  }

  function requestKey(filters) {
    return JSON.stringify({
      filters: filters || {},
      freeze: freezeRange,
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
      freezeRange: freezeRange,
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

  function setFeedTitle(text) {
    var root = getFeedRoot();
    var title = root && $('[data-pw-feed-title]', root);
    if (title) title.textContent = text;
  }

  function restoreFeedTitle() {
    var root = getFeedRoot();
    if (!root) return;
    var zh = ['zh_cn', 'zh-cn', 'zh_hans', 'zh-hans']
      .indexOf(String(currentLocale()).toLowerCase()) !== -1;
    setFeedTitle(root.getAttribute(zh ? 'data-pw-default-title-zh' : 'data-pw-default-title-en') ||
      (zh ? '本窗口最新' : 'Latest in window'));
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
    var committedRequestFilters = requestFilters(filters);
    var ticket = requestGate.start(FETCH_TIMEOUT_MS);
    state.fetching = true;
    showFeedStatus('loading');
    return fetchBatch(committedRequestFilters, opts, ticket.signal)
      .then(function (payload) {
        if (!requestGate.isCurrent(ticket)) return false;
        if (!isFeedPayload(payload)) throw new Error('malformed feed payload');
        commit(payload, committedRequestFilters);
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
    var filterSnapshot = filters || filtersForEvent();
    return runFeedRequest(filterSnapshot, { cursor: null }, function (payload, committedFilters) {
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
        if (state.committedKey !== requestKey(requestFilters(filters))) {
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
      pendingUnfreezeRefetch = false;
      var filters = filtersForEvent(event);
      var effective = requestFilters(filters);
      if (freezeRange && state.committedKey === requestKey(effective)) return;
      clearAndRefetch(filters);
    });
    document.addEventListener('pw:locale-change', function () {
      if (freezeRange) {
        setFeedTitle(freezeRange.title);
        return;
      }
      pendingUnfreezeRefetch = false;
      // Re-render existing rows; the JSON shape carries
      // text_translated already, so a full refetch is the simplest
      // path (cheaper than re-rendering cells with locale logic).
      clearAndRefetch();
    });
    document.addEventListener('pw:hover-freeze-start', function (event) {
      var detail = event && event.detail;
      if (!detail || !detail.start || !detail.end || !detail.title) return;
      freezeRange = {
        start: String(detail.start),
        end: String(detail.end),
        title: String(detail.title),
      };
      pendingUnfreezeRefetch = false;
      stopAutoRefresh();
      setFeedTitle(freezeRange.title);
      clearAndRefetch(filtersForEvent());
    });
    document.addEventListener('pw:hover-freeze-end', function () {
      if (!freezeRange) return;
      requestGate.cancel();
      freezeRange = null;
      restoreFeedTitle();
      startAutoRefresh();
      pendingUnfreezeRefetch = true;
      Promise.resolve().then(function () {
        if (!pendingUnfreezeRefetch || freezeRange) return;
        pendingUnfreezeRefetch = false;
        clearAndRefetch(filtersForEvent());
      });
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
    if (freezeRange) return;
    var filters = filtersForEvent();
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
        $$('.text.is-expanded').forEach(collapseText);
      }
    });
    wireSentinel();
    wireSortHeaders();
    wireFilterChange();
    startAutoRefresh();
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      buildQuery: buildQuery,
      createRequestGate: createRequestGate,
      formatRelative: formatRelative,
      formatLocalTooltip: formatLocalTooltip,
      enrichmentStatusHtml: enrichmentStatusHtml,
      textLayers: textLayers,
      hydrateRows: hydrateRows,
      paintSignals: paintSignals,
      replaceRows: replaceRows,
      isFeedPayload: isFeedPayload,
      renderRowHtml: renderRowHtml,
      hoverFreezeFilters: hoverFreezeFilters,
    };
    return;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
