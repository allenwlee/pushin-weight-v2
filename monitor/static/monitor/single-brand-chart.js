(() => {
  'use strict';
  const root = document.getElementById('ce-live-pulse');
  if (!root) return;
  const el = id => document.getElementById(id);
  const words = el('ce-labels').dataset;
  const statusWords = el('ce-status-labels').dataset;
  const locale = root.dataset.locale || 'en';
  const num = (v, options = {}) => v == null ? '—' : new Intl.NumberFormat(locale, options).format(Number(v));
  const pct = v => v == null ? '—' : `${num(v, {maximumFractionDigits: 1, signDisplay: 'always'})}%`;
  const dateLabel = value => value ? new Date(`${value}T00:00:00Z`).toLocaleDateString(locale, {month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC'}) : '—';
  const colors = ['#315ccc', '#dd734e', '#439f93', '#9e65ad', '#cfad50', '#5a769d', '#d05c69', '#8b5675', '#d89085', '#ad5962', '#6f7582', '#677e50'];
  let payload, chart, selected = 0, generation = 0, controller, searchController, searchTimer, searchGeneration = 0;
  let days = [], focusKey = 'discussion:posts';
  const hidden = new Set();
  const visiblePoints = line => line.points.filter(p => el('ce-window').value !== 'post' || p.day >= 0);
  const pointValue = (line, point) => {
    if (!point) return null;
    const v = line.source === 'arena' || !el('ce-smooth').checked ? point.percent : point.smooth_percent;
    if (v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const lineColor = (line, index) => line.color || colors[index % colors.length];
  const lineStatus = line => ({mapping_unavailable: statusWords.mappingUnavailable, mapping_ambiguous: statusWords.mappingAmbiguous, no_observations: statusWords.noObservations})[line.status] || statusWords.unavailable;
  const appendText = (parent, tag, text, className) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text;
    parent.append(node);
    return node;
  };
  function referenceText() {
    const line = payload.lines.find(item => item.key === focusKey);
    const ref = line && line.reference;
    el('ce-reference').textContent = ref ? `${line.label} · ${ref.basis === 'first_observation' ? words.first : words.week}: ${dateLabel(ref.start)}${ref.end && ref.end !== ref.start ? ` – ${dateLabel(ref.end)}` : ''}` : words.noReference;
  }
  function inspect(index) {
    if (!days.length) return;
    selected = Math.max(0, Math.min(days.length - 1, index));
    el('ce-day').value = selected;
    el('ce-day-label').textContent = dateLabel(days[selected]);
    el('ce-readout-date').textContent = `${dateLabel(days[selected])} · UTC`;
    el('ce-mode-label').textContent = el('ce-smooth').checked ? words.smoothed : words.daily;
    const box = el('ce-readout');
    box.replaceChildren();
    payload.lines.forEach((line, index) => {
      if (hidden.has(line.key)) return;
      const point = visiblePoints(line)[selected];
      const row = appendText(box, 'div', '', 'ce-reading');
      const label = appendText(row, 'div', '', 'ce-reading-label');
      const dot = document.createElement('i');
      dot.style.background = lineColor(line, index);
      label.append(dot, document.createTextNode(line.label));
      appendText(row, 'strong', pct(pointValue(line, point)));
      const origin = point?.source_date && (point.carried || line.key === 'arena:rank') ? ` · ${dateLabel(point.source_date)}` : '';
      const reported = point?.carried ? words.last : words.observed;
      const shown = point?.carried ? line.points.find(item => item.date === point.source_date)?.raw : point?.raw;
      appendText(row, 'small', `${reported}: ${num(shown, {maximumFractionDigits: 2})} ${line.unit || ''}${origin}`);
      if (line.reference) {
        const ref = line.reference;
        appendText(row, 'small', `${ref.basis === 'first_observation' ? words.first : words.week}: ${num(ref.mean, {maximumFractionDigits: 2})} · ${dateLabel(ref.start)}${ref.end && ref.end !== ref.start ? ` – ${dateLabel(ref.end)}` : ''}`);
      } else appendText(row, 'small', line.observed_dates ? words.noReference : words.empty);
    });
  }
  function draw() {
    if (!payload || !payload.lines?.length) return;
    if (!window.Chart) { el('ce-status').hidden = false; el('ce-status').textContent = words.unavailable; return; }
    days = visiblePoints(payload.lines[0]).map(point => point.date);
    selected = Math.min(selected, Math.max(days.length - 1, 0));
    if (chart) chart.destroy();
    const datasets = payload.lines.map((line, index) => {
      const points = visiblePoints(line), rank = line.key === 'arena:rank';
      return {key: line.key, label: line.label, data: points.map(point => pointValue(line, point)), borderColor: lineColor(line, index), borderWidth: 2,
        borderDash: rank ? [5, 4] : [], stepped: rank ? 'after' : false, pointRadius: rank ? points.map(p => p.raw == null ? 0 : 2) : line.source === 'arena' ? 2 : 0,
        pointHoverRadius: rank ? points.map(p => p.raw == null ? 0 : 4) : line.source === 'arena' ? 4 : 0,
        spanGaps: false, tension: 0, fill: false, hidden: hidden.has(line.key)};
    });
    chart = new Chart(el('ce-chart'), {type: 'line', data: {labels: days, datasets}, options: {responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {mode: 'index', intersect: false}, plugins: {legend: {display: false}, tooltip: {callbacks: {title: items => items.length ? `${dateLabel(days[items[0].dataIndex])} · UTC` : '',
        label: item => { const line = payload.lines.find(l => l.key === item.dataset.key); const p = line && visiblePoints(line)[item.dataIndex]; return `${item.dataset.label}: ${pct(item.parsed.y)}${line?.key === 'arena:rank' && p?.source_date ? ` · ${words.published} ${dateLabel(p.source_date)}` : ''}`; }}}},
      scales: {x: {ticks: {maxTicksLimit: 6, maxRotation: 0, callback: value => dateLabel(days[value])}}, y: {ticks: {callback: v => pct(v)}}},
      onHover: (event, _items, c) => { if (c.chartArea && event.x >= c.chartArea.left && event.x <= c.chartArea.right) inspect(Math.round(c.scales.x.getValueForPixel(event.x))); }
    }});
    const legend = el('ce-legend');
    legend.replaceChildren();
    payload.lines.forEach((line, index) => {
      const button = document.createElement('button');
      button.type = 'button'; button.dataset.series = line.key;
      button.setAttribute('aria-pressed', String(!hidden.has(line.key)));
      if (!visiblePoints(line).some(p => pointValue(line, p) !== null)) button.classList.add('ce-unavailable');
      const dot = document.createElement('i'); dot.style.background = lineColor(line, index);
      button.append(dot, document.createTextNode(`${line.label}${line.observed_dates ? '' : ` · ${lineStatus(line)}`}`));
      button.addEventListener('click', () => { hidden.has(line.key) ? hidden.delete(line.key) : hidden.add(line.key); draw(); });
      button.addEventListener('focus', () => { focusKey = line.key; referenceText(); });
      button.addEventListener('mouseenter', () => { focusKey = line.key; referenceText(); });
      legend.append(button);
    });
    el('ce-day').max = Math.max(days.length - 1, 0);
    referenceText(); inspect(selected);
    el('ce-empty-note').textContent = words.note;
  }
  async function load(refresh = false) {
    const seq = ++generation;
    controller?.abort();
    controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 85000);
    el('ce-status').hidden = false; el('ce-status').textContent = words.loading;
    el('ce-content').hidden = true; el('ce-refresh').disabled = true;
    try {
      const url = new URL(root.dataset.chartUrl, window.location.href);
      url.searchParams.set('lang', locale);
      if (refresh === true) url.searchParams.set('refresh', '1');
      const product = el('ce-product').value, release = el('ce-release').value;
      if (product || release) {
        if (!product || !release) throw new Error('Product and release date required');
        url.searchParams.set('product', product);
        url.searchParams.set('release_date', release);
      } else {
        const page = new URL(window.location.href);
        for (const key of ['product', 'release_date']) if (page.searchParams.has(key)) url.searchParams.set(key, page.searchParams.get(key));
      }
      const response = await fetch(url, {cache: 'no-store', signal: controller.signal});
      if (response.status === 429) throw new Error(statusWords.busy);
      if (!response.ok) throw new Error('Chart request failed');
      const next = await response.json();
      if (seq !== generation) return;
      if (!next.product || !Array.isArray(next.lines) || !next.lines.length) throw new Error('Chart response is incomplete');
      payload = next;
      selected = Math.max(0, payload.lines[0].points.length - 1);
      el('ce-title').textContent = payload.product.label;
      const selector = el('ce-product');
      if (![...selector.options].some(option => option.value === payload.product.key)) selector.add(new Option(payload.product.label, payload.product.key));
      selector.value = payload.product.key;
      el('ce-release').value = payload.product.release_date;
      el('ce-content').hidden = false; el('ce-status').hidden = true;
      const origin = payload.product.anchor_source === 'owner-confirmed' ? words.ownerDate : words.userDate;
      el('ce-loaded').textContent = `${words.release}: ${dateLabel(payload.product.release_date)} · ${origin} · UTC`;
      if (payload.as_of) el('ce-loaded').textContent += ` · ${statusWords.asOf}: ${new Date(payload.as_of).toLocaleString(locale)}`;
      const sources = el('ce-sources'); sources.replaceChildren();
      (payload.notes || []).forEach(note => appendText(sources, 'p', String(note)));
      payload.lines.forEach(line => appendText(sources, 'p', `${line.label}: ${line.observed_dates || 0} · ${line.identifier || lineStatus(line)}`));
      draw();
    } catch (error) {
      if (seq === generation) { el('ce-status').hidden = false; el('ce-status').textContent = error.message === statusWords.busy ? statusWords.busy : words.unavailable; }
    } finally {
      clearTimeout(timer);
      if (seq === generation) el('ce-refresh').disabled = false;
    }
  }
  el('ce-search').addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchController?.abort();
    const seq = ++searchGeneration, query = el('ce-search').value.trim();
    if (query.length < 2) return;
    searchTimer = setTimeout(async () => {
      searchController = new AbortController();
      try {
        const url = new URL(root.dataset.productsUrl, window.location.href);
        url.searchParams.set('q', query);
        const response = await fetch(url, {signal: searchController.signal});
        if (!response.ok) throw new Error('Search failed');
        const data = await response.json();
        if (seq !== searchGeneration) return;
        const selector = el('ce-product');
        const previous = selector.value;
        const previousLabel = selector.selectedOptions[0]?.textContent;
        selector.replaceChildren(new Option(data.products.length ? words.choose : words.searchEmpty, ''));
        data.products.forEach(product => selector.add(new Option(product.label, product.key)));
        if (previous && ![...selector.options].some(option => option.value === previous)) selector.add(new Option(previousLabel, previous));
        if ([...selector.options].some(option => option.value === previous)) selector.value = previous;
      } catch (error) {
        if (seq === searchGeneration && error.name !== 'AbortError') el('ce-status').textContent = words.unavailable;
      }
    }, 250);
  });
  function invalidateSelection() {
    ++generation;
    controller?.abort();
    el('ce-refresh').disabled = false;
    el('ce-content').hidden = true;
    el('ce-status').hidden = false;
    el('ce-status').textContent = words.choose;
  }
  el('ce-product').addEventListener('change', () => {
    invalidateSelection();
    if (payload && el('ce-product').value !== payload.product.key) el('ce-release').value = '';
  });
  el('ce-release').addEventListener('input', invalidateSelection);
  el('ce-smooth').addEventListener('change', draw);
  el('ce-window').addEventListener('change', () => { selected = 0; draw(); });
  el('ce-day').addEventListener('input', () => inspect(Number(el('ce-day').value)));
  el('ce-refresh').addEventListener('click', () => load(true));
  load();
})();
