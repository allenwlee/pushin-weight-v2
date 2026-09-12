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

  var synthesisGeneration = 0;
  var synthesisVisibleObserver = null;
  var synthesisLookaheadObserver = null;
  var synthesisLookaheadCount = 0;
  var synthesisQueues = { visible: {}, expanded: {}, lookahead: {} };
  var synthesisFlushTimer = null;
  var synthesisPollTimers = [];
  var synthesisControllers = [];
  var SYNTHESIS_POLL_DELAYS = [2000, 4000, 8000, 16000, 30000, 30000];

  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function synthesisLabel(status) {
    var locale = currentLocale();
    if (locale === 'ja' || locale === 'ja-JP') {
      return status === 'failed' ? '分析を生成できませんでした' :
        status === 'cancelled' ? '分析リクエストは期限切れです' : '分析を生成中';
    }
    if (locale === 'zh_cn' || locale === 'zh-CN' || locale === 'zh_hans') {
      return status === 'failed' ? '分析生成失败' :
        status === 'cancelled' ? '分析请求已过期' : '正在生成分析';
    }
    return status === 'failed' ? 'Analysis failed' :
      status === 'cancelled' ? 'Analysis request expired' : 'Analysis pending';
  }

  function resetSynthesisDemand() {
    synthesisGeneration += 1;
    if (synthesisVisibleObserver) synthesisVisibleObserver.disconnect();
    if (synthesisLookaheadObserver) synthesisLookaheadObserver.disconnect();
    synthesisVisibleObserver = null;
    synthesisLookaheadObserver = null;
    synthesisLookaheadCount = 0;
    synthesisQueues = { visible: {}, expanded: {}, lookahead: {} };
    if (synthesisFlushTimer != null) clearTimeout(synthesisFlushTimer);
    synthesisFlushTimer = null;
    synthesisPollTimers.forEach(clearTimeout);
    synthesisPollTimers = [];
    synthesisControllers.forEach(function (controller) { controller.abort(); });
    synthesisControllers = [];
  }

  function updateSynthesisRow(result) {
    var row = $$('.feed-row[data-tweet-id]').find(function (candidate) {
      return candidate.getAttribute('data-tweet-id') === String(result.post_id);
    });
    if (!row) return;
    var status = result.status || 'pending';
    row.setAttribute('data-synthesis-status', status);
    var text = $('.text[data-text-cycle]', row);
    var synthesis = result.synthesis || {};
    var literal = result.literal || {};
    if (text) {
      if (synthesis.en) text.setAttribute('data-commentary-en', synthesis.en);
      if (synthesis['zh-cn']) text.setAttribute('data-commentary-zh-cn', synthesis['zh-cn']);
      if (synthesis.ja) text.setAttribute('data-commentary-ja', synthesis.ja);
      if (literal.en) text.setAttribute('data-text-en', literal.en);
      if (literal['zh-cn']) text.setAttribute('data-literal-cn', literal['zh-cn']);
      if (literal.ja) text.setAttribute('data-text-ja', literal.ja);
      text.setAttribute('data-layer-idx', '0');
      renderTextLayer(text);
    }
    var badge = $('.synthesis-status', row);
    if (status === 'ready') {
      if (badge) badge.remove();
      return;
    }
    if (!badge) {
      badge = document.createElement('span');
      badge.setAttribute('role', 'status');
      badge.setAttribute('aria-live', 'polite');
      var meta = $('.meta', row);
      if (meta) meta.appendChild(badge);
    }
    badge.className = 'enrichment-status synthesis-status synthesis-status-' + status;
    badge.textContent = synthesisLabel(status);
  }

  function requestSynthesis(postIds, reason, generation, pollAttempt) {
    if (!postIds.length || document.hidden || generation !== synthesisGeneration) return;
    var controller = typeof AbortController === 'undefined' ? null : new AbortController();
    if (controller) synthesisControllers.push(controller);
    fetch('/api/v2/post-synthesis-demands/', {
      method: 'POST',
      credentials: 'same-origin',
      signal: controller ? controller.signal : undefined,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({
        post_ids: postIds,
        reason: reason,
        poll_only: pollAttempt > 0,
      }),
    }).then(function (response) {
      if (!response.ok) throw new Error('synthesis request failed');
      return response.json();
    }).then(function (payload) {
      if (generation !== synthesisGeneration || !payload || !Array.isArray(payload.results)) return;
      payload.results.forEach(updateSynthesisRow);
      var pending = payload.results.filter(function (result) {
        return ['ready', 'failed', 'cancelled'].indexOf(result.status) === -1;
      }).map(function (result) { return String(result.post_id); });
      if (pending.length && pollAttempt < SYNTHESIS_POLL_DELAYS.length) {
        var timer = setTimeout(function () {
          synthesisPollTimers = synthesisPollTimers.filter(function (item) {
            return item !== timer;
          });
          requestSynthesis(pending, reason, generation, pollAttempt + 1);
        }, SYNTHESIS_POLL_DELAYS[pollAttempt]);
        synthesisPollTimers.push(timer);
      }
    }).catch(function () {
      // Feed content remains readable from source/literal text during outages.
    }).finally(function () {
      if (!controller) return;
      synthesisControllers = synthesisControllers.filter(function (item) {
        return item !== controller;
      });
    });
  }

  function flushSynthesisQueues() {
    synthesisFlushTimer = null;
    if (document.hidden) return;
    var generation = synthesisGeneration;
    ['expanded', 'visible', 'lookahead'].forEach(function (reason) {
      var cap = reason === 'lookahead' ? 10 : 20;
      var ids = Object.keys(synthesisQueues[reason]).slice(0, cap);
      synthesisQueues[reason] = {};
      requestSynthesis(ids, reason, generation, 0);
    });
  }

  function queueSynthesis(row, reason) {
    if (!row || document.hidden ||
        ['ready', 'failed', 'cancelled'].indexOf(
          row.getAttribute('data-synthesis-status')
        ) !== -1) return;
    var postId = row.getAttribute('data-tweet-id');
    if (!postId) return;
    synthesisQueues[reason][postId] = true;
    if (synthesisFlushTimer == null) {
      synthesisFlushTimer = setTimeout(flushSynthesisQueues, 50);
    }
  }

  function observeSynthesisRows(rows) {
    if (typeof IntersectionObserver === 'undefined') return;
    var scrollRoot = $('[data-pw-feed-scroll]') || null;
    if (!synthesisVisibleObserver) {
      synthesisVisibleObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) queueSynthesis(entry.target, 'visible');
        });
      }, { root: scrollRoot, rootMargin: '0px' });
    }
    if (!synthesisLookaheadObserver) {
      synthesisLookaheadObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting || synthesisLookaheadCount >= 10) return;
          synthesisLookaheadCount += 1;
          queueSynthesis(entry.target, 'lookahead');
          synthesisLookaheadObserver.unobserve(entry.target);
        });
      }, { root: scrollRoot, rootMargin: '250px 0px' });
    }
    rows.forEach(function (row) {
      if (row.getAttribute('data-synthesis-status') === 'ready') return;
      synthesisVisibleObserver.observe(row);
      synthesisLookaheadObserver.observe(row);
    });
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
    div.setAttribute('data-source-kind', row.source_kind || 'x_post');
    div.setAttribute('data-source-url', row.source_url || '');
    div.setAttribute('data-tweet-id', row.tweet_id || '');
    div.setAttribute(
      'data-x-url',
      row.source_kind === 'official_job'
        ? ''
        : (row.tweet_id ? 'https://x.com/i/web/status/' + encodeURIComponent(row.tweet_id) : '')
    );
    div.setAttribute('data-created-at-iso', row.created_at_iso || '');
    div.setAttribute('data-sentiments', (row.sentiment_keys || []).join(','));
    div.setAttribute('data-post-types', (row.post_type_keys || []).join(','));
    div.setAttribute('data-product-labels', (row.product_label_keys || []).join(','));
    div.setAttribute(
      'data-classification-statuses',
      (row.classification_statuses || []).join(',')
    );
    div.setAttribute(
      'data-classification-status-labels',
      (row.classification_status_labels || []).join(',')
    );
    div.setAttribute('data-nat-cn', row.nat_cn || '');
    div.setAttribute('data-nat-us', row.nat_us || '');
    div.setAttribute('data-signal-inspections', JSON.stringify(row.signal_inspections || {}));
    div.setAttribute('data-unsanctioned', row.unsanctioned ? '1' : '');
    div.setAttribute('data-enrichment-status', row.enrichment_status || 'succeeded');
    div.setAttribute('data-synthesis-status', row.synthesis_status || 'not_requested');
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

  function synthesisStatusHtml(row) {
    var status = row.synthesis_status || 'not_requested';
    if (status === 'ready') return '';
    var label = row.synthesis_status_label || synthesisLabel(status);
    return '<span class="enrichment-status synthesis-status synthesis-status-' +
      escapeHtml(status) + '" role="status" aria-live="polite">' +
      escapeHtml(label) + '</span>';
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
      return '';
    }
    var label = account.role_label || role;
    return '<button type="button" class="account-role role-' + role +
      ' pw-inspection-trigger" data-pw-inspection="' + escapeHtml(label) + '"' +
      ' aria-label="' + escapeHtml(label) + '" aria-expanded="false">' +
      renderIcon('icon-role-badge', 'account-role-icon') + '</button>';
  }

  function approvedFlag(flag) {
    if (!flag || typeof flag !== 'object') return null;
    var code = typeof flag.code === 'string' ? flag.code : '';
    var symbolId = typeof flag.symbol_id === 'string' ? flag.symbol_id : '';
    var label = typeof flag.label === 'string' ? flag.label : '';
    if (!/^[A-Z]{2}$/.test(code) || symbolId !== 'flag-' + code.toLowerCase() || !label) {
      return null;
    }
    if (countryFlagSpriteUrl()) {
      var body = document.body;
      var rawCodes = body && body.getAttribute('data-pw-country-flag-codes');
      var codes;
      try { codes = JSON.parse(rawCodes || '[]'); } catch (_error) { codes = []; }
      if (!Array.isArray(codes) || codes.indexOf(code) === -1) return null;
    } else if (typeof document !== 'undefined' &&
               typeof document.getElementById === 'function' &&
               !document.getElementById(symbolId)) {
      return null;
    }
    return { code: code, symbolId: symbolId, label: label };
  }

  function countryFlagSpriteUrl() {
    var body = typeof document !== 'undefined' ? document.body : null;
    var spriteUrl = body && body.getAttribute('data-pw-country-flag-sprite-url');
    return spriteUrl && spriteUrl.indexOf('country-flags.svg') !== -1 ? spriteUrl : '';
  }

  function countryFlagHref(symbolId) {
    return countryFlagSpriteUrl() + '#' + symbolId;
  }

  function accountGeographyHtml(row) {
    var account = row.account || {};
    var geography = account.geography;
    if (!geography || typeof geography !== 'object') return '';
    var kind = geography.kind;
    if (['country', 'hierarchy', 'taiwan', 'region'].indexOf(kind) === -1) return '';
    var accessibleLabel = typeof geography.accessible_label === 'string'
      ? geography.accessible_label : '';
    var label = typeof geography.label === 'string' ? geography.label : '';
    var text = typeof geography.text === 'string' ? geography.text : '';
    var relationship = typeof geography.relationship_type === 'string'
      ? geography.relationship_type : '';
    if (!accessibleLabel || !label) return '';
    var rawFlags = Array.isArray(geography.flags) ? geography.flags : [];
    var flags = rawFlags.map(approvedFlag).filter(Boolean);
    if (flags.length !== rawFlags.length || flags.length > 2) return '';
    if (kind === 'country' && (flags.length !== 1 || text)) return '';
    if (kind === 'hierarchy' && (flags.length !== 2 || text)) return '';
    if (kind === 'taiwan' &&
        (flags.length !== 1 || flags[0].code !== 'CN' || text.indexOf('TW · ') !== 0)) {
      return '';
    }
    if (kind === 'region' && (flags.length || !text)) return '';

    var content = '';
    flags.forEach(function (flag, index) {
      if (kind === 'hierarchy' && index > 0) {
        content += '<span class="account-geography-elbow" aria-hidden="true"></span>';
      }
      content += '<button type="button" class="account-geography-flag pw-inspection-trigger' +
        (kind === 'hierarchy' ? (index === 0 ? ' is-parent' : ' is-child') : '') + '"' +
        ' data-pw-inspection="' + escapeHtml(flag.label) + '"' +
        ' aria-label="' + escapeHtml(flag.label) + '" aria-expanded="false">' +
        '<svg class="account-country-flag" viewBox="0 0 16 9"' +
        ' preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">' +
        '<use href="' + escapeHtml(countryFlagHref(flag.symbolId)) + '"></use></svg></button>';
      if (kind === 'taiwan' && text) {
        content += '<span class="account-geography-connector" aria-hidden="true"></span>';
      }
    });
    if (text) {
      content += '<button type="button" class="account-geography-text pw-inspection-trigger"' +
        ' data-pw-inspection="' + escapeHtml(label) + '"' +
        ' aria-label="' + escapeHtml(label) + '" aria-expanded="false">' +
        escapeHtml(text) + '</button>';
    }
    return '<span class="account-geography geography-' + kind + '"' +
      ' data-geography-kind="' + kind + '"' +
      (relationship ? ' data-geography-relationship="' + escapeHtml(relationship) + '"' : '') +
      ' role="group" aria-label="' + escapeHtml(accessibleLabel) + '">' +
      content + '</span>';
  }

  function accountLeadMetadataHtml(row) {
    var account = row.account || {};
    var roleHtml = accountRoleHtml(row);
    var geographyHtml = accountGeographyHtml(row);
    if (account.role === 'official') return roleHtml + geographyHtml;
    if (geographyHtml) {
      return geographyHtml +
        (['staff', 'community'].indexOf(account.role) !== -1 ? roleHtml : '');
    }
    return roleHtml;
  }

  // Render the production two-column grid. paintSignals() fills the reserved
  // signal column after the row enters the DOM.
  function officialJobActionLabel() {
    var locale = currentLocale();
    return locale === 'zh_cn' || locale === 'zh-CN' || locale === 'zh_hans'
      ? '查看官方职位' : (locale === 'ja' || locale === 'ja-JP')
        ? '公式求人を見る' : 'View official job';
  }

  function renderOfficialJobRowHtml(row) {
    var actionLabel = officialJobActionLabel();
    var sourceUrl = row.source_url || row.application_url || '';
    var applicationUrl = row.application_url || sourceUrl;
    return (
      '<div class="feed-row-shell ' + escapeHtml(row.tint_class || 'tint-neutral') + '">' +
        '<div class="feed-main"><div class="body official-job-body">' +
          '<div class="head"><span class="handle">' +
            '<a class="feed-handle-link official-job-source" href="' + escapeHtml(sourceUrl) +
              '" target="_blank" rel="noopener noreferrer">' +
              escapeHtml(row.source_name || '') + '</a></span>' +
            '<span class="meta">· ' +
              escapeHtml(row.job_meta_text || row.location_text || '') +
              ' <span class="ts-abs">' + escapeHtml(row.ts_abs_text || '') + '</span></span></div>' +
          '<div class="text official-job-text"><strong class="official-job-title">' +
            escapeHtml(row.title || '') + '</strong>' +
            (row.text_original ? '<span class="official-job-description">' +
              escapeHtml(row.text_original) + '</span>' : '') + '</div>' +
          '<div class="engagement official-job-actions"><a class="official-job-link" href="' +
            escapeHtml(applicationUrl) + '" target="_blank" rel="noopener noreferrer">' +
            escapeHtml(actionLabel) + '</a></div>' +
        '</div></div>' +
        '<div class="feed-signals">' +
          '<div class="sig-row sig-sentiment" data-sig-sentiment></div>' +
          '<div class="sig-row sig-post-type" data-sig-post-type></div>' +
          '<div class="sig-row sig-product" data-sig-product></div>' +
          '<div class="sig-row sig-classification-status" data-sig-classification-status></div>' +
          '<div class="sig-row sig-nat" data-sig-nat></div>' +
          '<div class="sig-row sig-unsanctioned" data-sig-unsanctioned></div>' +
        '</div>' +
      '</div>'
    );
  }

  function renderRowHtml(row) {
    if (row.source_kind === 'official_job') return renderOfficialJobRowHtml(row);
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
    var commentaryJa = row.commentary_ja || '';
    var literalCnText = row.text_zh_cn || '';
    var englishText = row.text_en || '';
    var japaneseText = row.text_ja || '';
    var languageDisplay = row.language_display || 'undetected';
    var leadMetadata = accountLeadMetadataHtml(row);
    var locale = currentLocale();
    var initialText = locale === 'zh_cn' || locale === 'zh-CN' || locale === 'zh_hans'
      ? (commentaryZhCn || literalCnText || sourceText)
      : locale === 'ja' || locale === 'ja-JP'
        ? (commentaryJa || japaneseText || sourceText)
      : locale === 'original'
        ? sourceText
        : (commentaryEn || englishText || sourceText);
    return (
      '<div class="feed-row-shell ' + escapeHtml(tint) + '">' +
        '<div class="feed-main">' +
          '<div class="follower-lead follower-bin-' + followerClass +
            (leadMetadata ? ' has-account-metadata' : '') + '">' +
            '<button type="button" class="follower-magnitude pw-inspection-trigger"' +
              ' data-pw-inspection="' + escapeHtml(followersLabel) + '"' +
              ' aria-label="' + escapeHtml(followersLabel) + '" aria-expanded="false">' +
              '<span class="follower-glyph" aria-hidden="true">' +
                renderIcon(FOLLOWER_ICONS[followerClass], 'follower-icon') +
              '</span>' +
              '<span class="follower-count">' + escapeHtml(followersPretty) + '</span>' +
            '</button>' +
            leadMetadata +
          '</div>' +
          '<div class="body">' +
            '<div class="head">' +
              '<span class="handle">' + handleHtml + '</span>' +
              '<span class="meta">· ' + escapeHtml(metaText) + ' <span class="ts-abs">' + escapeHtml(tsAbs) + '</span> ' + enrichmentStatusHtml(row) + synthesisStatusHtml(row) + '</span>' +
            '</div>' +
            '<div class="text" data-text-cycle role="button" tabindex="0"' +
              ' data-language-display="' + escapeHtml(languageDisplay) + '"' +
              ' data-commentary-zh-cn="' + escapeHtml(commentaryZhCn) + '"' +
              ' data-commentary-en="' + escapeHtml(commentaryEn) + '"' +
              ' data-commentary-ja="' + escapeHtml(commentaryJa) + '"' +
              ' data-literal-cn="' + escapeHtml(literalCnText) + '"' +
              ' data-text-en="' + escapeHtml(englishText) + '"' +
              ' data-text-ja="' + escapeHtml(japaneseText) + '"' +
              ' data-text-source="' + escapeHtml(sourceText) + '">' +
              '<span class="post-language-tag">' + escapeHtml(languageDisplay) + '</span>' +
              escapeHtml((initialText || '').toString()) +
            '</div>' +
            '<div class="engagement">' +
              '<span class="likes">' + renderIcon('icon-heart', 'engagement-icon') + escapeHtml(eng.likes || '') + '</span>' +
              '<span class="rts">' + renderIcon('icon-repost', 'engagement-icon') + escapeHtml(eng.retweets || '') + '</span>' +
              '<span class="replies">' + renderIcon('icon-reply', 'engagement-icon') + escapeHtml(eng.replies || '') + '</span>' +
              '<a class="feed-x-link" href="https://x.com/i/web/status/' +
                encodeURIComponent(row.tweet_id || '') + '" target="_blank"' +
                ' rel="noopener noreferrer" aria-label="' +
                escapeHtml((locale === 'zh_cn' || locale === 'zh-CN' || locale === 'zh_hans')
                  ? '在 X 查看原帖' : (locale === 'ja' || locale === 'ja-JP')
                    ? 'X で元の投稿を表示' : 'Open original post on X') + '">' +
                '<svg class="feed-x-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
                  '<path fill="currentColor" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24h-6.657l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231 5.45-6.231Zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77Z"></path>' +
                '</svg></a>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="feed-signals">' +
          '<div class="sig-row sig-sentiment" data-sig-sentiment></div>' +
          '<div class="sig-row sig-post-type" data-sig-post-type></div>' +
          '<div class="sig-row sig-product" data-sig-product></div>' +
          '<div class="sig-row sig-classification-status" data-sig-classification-status></div>' +
          '<div class="sig-row sig-nat" data-sig-nat></div>' +
          '<div class="sig-row sig-unsanctioned" data-sig-unsanctioned></div>' +
        '</div>' +
      '</div>'
    );
  }

  function renderOfficialJobTableRowHtml(row) {
    var actionLabel = officialJobActionLabel();
    var sourceUrl = row.source_url || row.application_url || '';
    var applicationUrl = row.application_url || sourceUrl;
    var brand = (row.brands || [])[0] || {};
    return (
      '<td class="muted-cell"><a class="feed-date-link" href="' +
        escapeHtml(sourceUrl) + '" target="_blank" rel="noopener noreferrer">' +
        escapeHtml(row.created_at || '') + '</a></td>' +
      '<td><span class="pill">' +
        escapeHtml(brand.display_name || brand.display_name_en || brand.nickname || '') +
        '</span></td>' +
      '<td><strong class="official-job-table-title">' + escapeHtml(row.title || '') +
        '</strong>' + (row.text_original
          ? '<div class="cell-truncated official-job-table-description" ' +
              'data-pw-cell-truncated>' + escapeHtml(row.text_original) + '</div>'
          : '') + '</td>' +
      '<td class="official-job-table-meta">' +
        escapeHtml(row.job_meta_text || row.location_text || '') + '</td>' +
      '<td><span class="pill" data-key="job_listings">' +
        escapeHtml(row.job_listing_label || 'job listings') + '</span></td>' +
      '<td><div class="official-job-table-source">' +
        escapeHtml(row.source_name || '') + '</div>' +
        '<a class="official-job-table-link" href="' + escapeHtml(applicationUrl) +
        '" target="_blank" rel="noopener noreferrer">' +
        escapeHtml(actionLabel) + '</a></td>'
    );
  }

  function renderOfficialJobTableRow(row) {
    var element = document.createElement('tr');
    element.className = 'official-job-table-row';
    element.setAttribute('data-pw-feed-row', '');
    element.setAttribute('data-source-kind', 'official_job');
    element.setAttribute('data-source-url', row.source_url || '');
    element.setAttribute('data-tweet-id', '');
    element.setAttribute('data-created-at-iso', row.created_at_iso || '');
    element.setAttribute('data-post-types', 'job_listings');
    element.innerHTML = renderOfficialJobTableRowHtml(row);
    return element;
  }

  // Paint Cyber-Quan symbols and existing semantic tints in the right column.
  var SENT_ORDER = ['positive', 'neutral', 'negative', 'mixed'];
  var TYPE_ORDER = [
    'releases_updates', 'hands_on_usage', 'results_evaluations',
    'questions_requests', 'advertising_marketing', 'events', 'opportunities',
    'job_listings', 'personnel_changes',
    'opinions_reactions', 'research_explanations', 'business_finance', 'other'
  ];
  var PRODUCT_ORDER = [
    'bug', 'complaint', 'testimonial', 'ideas_requests', 'misinformation'
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
  function signalInspections(row) {
    var raw = row.getAttribute('data-signal-inspections') || '{}';
    try {
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    } catch (error) {
      return {};
    }
  }
  function signalInspectionText(inspections, family, key) {
    var familyEntries = inspections[family];
    var entries = familyEntries && familyEntries[key];
    if (!Array.isArray(entries)) return '';
    return entries.map(function (entry) {
      return entry && typeof entry.text === 'string' ? entry.text : '';
    }).filter(Boolean).join('\n');
  }
  function inspectionTriggerHtml(content, inspection, className) {
    if (!content) return '';
    if (!inspection) return content;
    return '<button type="button" class="pw-inspection-trigger ' +
      escapeHtml(className || '') + '" data-pw-inspection="' +
      escapeHtml(inspection) + '" aria-label="' + escapeHtml(inspection) +
      '" aria-expanded="false">' + content + '</button>';
  }
  function paintSignals(row) {
    var sents = uniqueInOrder(parseListAttr(row.getAttribute('data-sentiments')), SENT_ORDER);
    var types = uniqueInOrder(parseListAttr(row.getAttribute('data-post-types')), TYPE_ORDER);
    var products = uniqueInOrder(
      parseListAttr(row.getAttribute('data-product-labels')), PRODUCT_ORDER
    );
    var classificationStatuses = parseListAttr(
      row.getAttribute('data-classification-statuses')
    );
    var classificationStatusLabels = parseListAttr(
      row.getAttribute('data-classification-status-labels')
    );
    var natCn = (row.getAttribute('data-nat-cn') || '').trim();
    var natUs = (row.getAttribute('data-nat-us') || '').trim();
    var showCn = natCn && natCn !== 'none';
    var showUs = natUs && natUs !== 'none';
    var inspections = signalInspections(row);
    var elS = row.querySelector('[data-sig-sentiment]');
    if (elS) {
      elS.innerHTML = sents.map(function (key) {
        return inspectionTriggerHtml(
          semanticIcon('sentiment', key, 'signal-icon'),
          signalInspectionText(inspections, 'sentiment', key),
          'signal-inspection-trigger'
        );
      }).join('');
    }
    var elT = row.querySelector('[data-sig-post-type]');
    if (elT) {
      elT.innerHTML = types.map(function (key) {
        return inspectionTriggerHtml(
          semanticIcon('post_types', key, 'signal-icon'),
          signalInspectionText(inspections, 'post_type', key),
          'signal-inspection-trigger'
        );
      }).join('');
    }
    var elP = row.querySelector('[data-sig-product]');
    if (elP) {
      elP.innerHTML = products.map(function (key) {
        return inspectionTriggerHtml(
          semanticIcon('product_labels', key, 'signal-icon'),
          signalInspectionText(inspections, 'product_label', key),
          'signal-inspection-trigger product-signal product-' + key
        );
      }).join('');
      elP.classList.toggle('is-empty', products.length === 0);
    }
    var elClassification = row.querySelector('[data-sig-classification-status]');
    if (elClassification) {
      elClassification.innerHTML = classificationStatuses.map(function (status, index) {
        var inspection = signalInspectionText(
          inspections, 'classification_status', status
        );
        return inspectionTriggerHtml(
          '<span class="classification-state-label">' +
            escapeHtml(classificationStatusLabels[index] || status) + '</span>',
          inspection,
          'signal-inspection-trigger classification-state classification-state-' + status
        );
      }).join('');
      elClassification.classList.toggle(
        'is-empty', classificationStatuses.length === 0
      );
    }
    var elN = row.querySelector('[data-sig-nat]');
    if (elN) {
      if (!showCn && !showUs) { elN.innerHTML = ''; elN.classList.add('is-empty'); }
      else {
        elN.classList.remove('is-empty');
        var regions = (showCn
          ? inspectionTriggerHtml(
              renderIcon('icon-nationalism', 'signal-icon') + '<b>中</b>',
              signalInspectionText(inspections, 'nat_cn', natCn),
              'signal-inspection-trigger nationalism-region nationalism-cn'
            )
          : '') + (showUs
          ? inspectionTriggerHtml(
              renderIcon('icon-nationalism', 'signal-icon') + '<b>美</b>',
              signalInspectionText(inspections, 'nat_us', natUs),
              'signal-inspection-trigger nationalism-region nationalism-us'
            )
          : '');
        elN.innerHTML = regions;
      }
    }
    var elU = row.querySelector('[data-sig-unsanctioned]');
    if (elU) {
      var uns = (row.getAttribute('data-unsanctioned') || '').trim();
      var isUn = uns === '1' || uns === 'true' || uns === 'yes';
      if (isUn) {
        elU.classList.remove('is-empty');
        elU.innerHTML = inspectionTriggerHtml(
          renderIcon('icon-unsanctioned', 'signal-icon tone-negative'),
          signalInspectionText(inspections, 'unsanctioned', 'true'),
          'signal-inspection-trigger'
        );
      }
      else      { elU.textContent = ''; elU.classList.add('is-empty'); }
    }
  }
  function paintAllSignals(root) {
    if (!root) return;
    $$('.feed-row[data-pw-feed-row]', root).forEach(paintSignals);
  }

  var inspectionPopover = null;

  function createInspectionPopoverController() {
    var popover = document.createElement('div');
    popover.id = 'pw-feed-inspection-popover';
    popover.className = 'pw-feed-inspection-popover';
    popover.setAttribute('role', 'tooltip');
    popover.hidden = true;
    document.body.appendChild(popover);
    var activeTrigger = null;
    var pinned = false;

    function position() {
      if (!activeTrigger || !activeTrigger.isConnected || popover.hidden) {
        close();
        return;
      }
      var margin = 8;
      var gap = 6;
      var rect = activeTrigger.getBoundingClientRect();
      var width = popover.offsetWidth;
      var height = popover.offsetHeight;
      var left = rect.left + (rect.width - width) / 2;
      left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
      var top = rect.bottom + gap;
      if (top + height > window.innerHeight - margin) {
        top = rect.top - height - gap;
      }
      top = Math.max(margin, Math.min(top, window.innerHeight - height - margin));
      popover.style.left = Math.round(left) + 'px';
      popover.style.top = Math.round(top) + 'px';
    }

    function close() {
      if (activeTrigger) {
        activeTrigger.setAttribute('aria-expanded', 'false');
        activeTrigger.removeAttribute('aria-describedby');
      }
      activeTrigger = null;
      pinned = false;
      popover.hidden = true;
      popover.textContent = '';
    }

    function open(trigger, shouldPin) {
      var content = trigger && trigger.getAttribute('data-pw-inspection');
      if (!content) return;
      if (activeTrigger && activeTrigger !== trigger) {
        activeTrigger.setAttribute('aria-expanded', 'false');
        activeTrigger.removeAttribute('aria-describedby');
      }
      activeTrigger = trigger;
      pinned = Boolean(shouldPin);
      trigger.setAttribute('aria-expanded', 'true');
      trigger.setAttribute('aria-describedby', popover.id);
      popover.textContent = content;
      popover.hidden = false;
      position();
    }

    function toggle(trigger) {
      if (activeTrigger === trigger && pinned) {
        close();
        return;
      }
      open(trigger, true);
    }

    document.addEventListener('pointerover', function (event) {
      var trigger = event.target.closest('.pw-inspection-trigger');
      if (!trigger || (activeTrigger && pinned)) return;
      open(trigger, false);
    });
    document.addEventListener('pointerout', function (event) {
      var trigger = event.target.closest('.pw-inspection-trigger');
      if (!trigger || pinned || activeTrigger !== trigger) return;
      if (event.relatedTarget && (
        trigger.contains(event.relatedTarget) || popover.contains(event.relatedTarget)
      )) return;
      close();
    });
    document.addEventListener('focusin', function (event) {
      var trigger = event.target.closest('.pw-inspection-trigger');
      if (trigger && !(activeTrigger && pinned)) open(trigger, false);
    });
    document.addEventListener('focusout', function (event) {
      if (pinned || event.target !== activeTrigger) return;
      if (event.relatedTarget && popover.contains(event.relatedTarget)) return;
      close();
    });
    document.addEventListener('click', function (event) {
      var trigger = event.target.closest('.pw-inspection-trigger');
      if (!trigger) return;
      event.preventDefault();
      event.stopPropagation();
      toggle(trigger);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && activeTrigger) {
        var prior = activeTrigger;
        close();
        prior.focus();
      }
    });
    document.addEventListener('pointerdown', function (event) {
      if (!pinned || !activeTrigger) return;
      if (event.target.closest('.pw-inspection-trigger') || popover.contains(event.target)) return;
      close();
    });
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, true);

    return {
      close: close,
      activeTrigger: function () { return activeTrigger; },
    };
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
    if (locale === 'ja' || locale === 'ja-JP') {
      return uniqueTextLayers([
        { key: 'synthesis', label: '分析', value: textValue(el, 'commentary-ja') },
        { key: 'literal_ja', label: '直訳', value: textValue(el, 'text-ja') },
        { key: 'source', label: '原文', value: source },
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
      el.innerHTML = '<span class="post-language-tag">' +
        escapeHtml(el.getAttribute('data-language-display') || 'undetected') + '</span>';
      el.removeAttribute('data-layer-key');
      return;
    }
    var index = parseInt(el.getAttribute('data-layer-idx') || '0', 10);
    if (isNaN(index) || index < 0 || index >= layers.length) index = 0;
    var layer = layers[index];
    el.setAttribute('data-layer-idx', String(index));
    el.setAttribute('data-layer-key', layer.key);
    el.innerHTML = '<span class="post-language-tag">' +
      escapeHtml(el.getAttribute('data-language-display') || 'undetected') + '</span>' +
      '<span class="text-layer-tag">' + escapeHtml(layer.label) + '</span>' +
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

  function hydrateRows(rows) {
    var now = new Date();
    rows.forEach(function (row) {
      paintSignals(row);
      attachCellClickHandlers(row);
      formatRowTimestamp(row, now);
    });
    observeSynthesisRows(rows);
  }

  function appendRows(body, rows) {
    var inserted = rows.map(function (row) {
      if (body.tagName === 'TBODY' && row.source_kind === 'official_job') {
        return renderOfficialJobTableRow(row);
      }
      return renderRow(row);
    });
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
        '</div></div></div><div class="feed-signals"></div>' +
      '</div></div>';
  }

  function replaceRows(body, rows) {
    resetSynthesisDemand();
    if (inspectionPopover) {
      var trigger = inspectionPopover.activeTrigger();
      if (trigger && body.contains(trigger)) inspectionPopover.close();
    }
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
        queueSynthesis(row, 'expanded');
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
    var ja = ['ja', 'ja-jp'].indexOf(String(currentLocale()).toLowerCase()) !== -1;
    setFeedTitle(root.getAttribute(zh ? 'data-pw-default-title-zh' :
      ja ? 'data-pw-default-title-ja' : 'data-pw-default-title-en') ||
      (zh ? '本窗口最新' : ja ? 'この期間の最新投稿' : 'Latest in window'));
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
    resetSynthesisDemand();
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
        var filters = (window.pwFilter && window.pwFilter.get) ? window.pwFilter.get() : {};
        if (state.committedKey !== requestKey(requestFilters(filters))) {
          clearAndRefetch(filters);
          return;
        }
        runFeedRequest(filters, { cursor: state.cursor }, function (payload, committedFilters) {
          appendRows(body, payload.rows);
          state.cursor = payload.next_cursor;
          state.total += payload.rows.length;
          state.committedKey = requestKey(committedFilters);
          if (!state.cursor) {
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
    inspectionPopover = createInspectionPopoverController();
    var body = $('[data-pw-feed-body]');
    if (body) {
      var initialRows = $$('.feed-row[data-pw-feed-row]', body);
      hydrateRows(initialRows);
      state.total = initialRows.length;
      var root = getFeedRoot();
      state.cursor = root && root.getAttribute('data-pw-next-cursor') || null;
      state.exhausted = root && root.getAttribute('data-pw-has-more') === 'false';
      if (state.exhausted) showEnd();
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
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        resetSynthesisDemand();
        return;
      }
      var currentBody = $('[data-pw-feed-body]');
      if (currentBody) {
        observeSynthesisRows($$('.feed-row[data-pw-feed-row]', currentBody));
      }
    });
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      buildQuery: buildQuery,
      createRequestGate: createRequestGate,
      formatRelative: formatRelative,
      formatLocalTooltip: formatLocalTooltip,
      enrichmentStatusHtml: enrichmentStatusHtml,
      synthesisStatusHtml: synthesisStatusHtml,
      textLayers: textLayers,
      hydrateRows: hydrateRows,
      paintSignals: paintSignals,
      replaceRows: replaceRows,
      isFeedPayload: isFeedPayload,
      renderRowHtml: renderRowHtml,
      renderOfficialJobTableRowHtml: renderOfficialJobTableRowHtml,
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
