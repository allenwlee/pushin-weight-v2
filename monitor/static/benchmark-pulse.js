/* Read-only Pulse: values, baselines and evidence come from the shared series API. */
(() => {
  'use strict';
  const root = document.querySelector('#pulse');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const colors = ['#4485c6', '#ba921d', '#9169c3', '#30978e', '#d78449', '#b75b78', '#60777f'];
  const ns = 'http://www.w3.org/2000/svg';
  let data, days, current = 0, mode = 'compressed';
  const visible = new Set();
  const svg = $('pulse-chart');
  const box = {left: 83, right: 872, top: 45, bottom: 385};
  const fmt = (value, raw = false) => {
    if (value === null || value === undefined) return 'Not available';
    if (raw && typeof value === 'string' && /^-?\d+$/.test(value)) return BigInt(value).toLocaleString('en-US');
    const n = Number(value);
    if (raw) return n.toLocaleString('en-US', {maximumFractionDigits: 2});
    return `${n > 0 ? '+' : ''}${n.toLocaleString('en-US', {maximumFractionDigits: 2})}%`;
  };
  const labelDate = date => new Date(`${date}T00:00:00Z`).toLocaleDateString('en-US', {month:'short', day:'numeric', timeZone:'UTC'});
  const element = (tag, attrs = {}, text) => {
    const node = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = text;
    svg.append(node);
    return node;
  };
  const html = (tag, parent, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    parent.append(node);
    return node;
  };
  const dot = (parent, index) => {
    const node = html('span', parent, undefined, 'dot');
    node.style.setProperty('--line-color', colors[index % colors.length]);
  };
  const pointValue = p => p && (mode === 'raw' ? (p.raw_value === null ? null : Number(p.raw_value)) : p.percent_change);
  const active = () => data.lines.filter(line => mode === 'raw' ? line.key === $('raw-series').value : visible.has(line.key));
  const coverageText = p => ({carried_forward:`Last published ${p.source_date}`, partial:'Partial day', missing:'No observation', not_reported_top50:'Not reported in available top-50 usage data', observed:'Observed', reconstructed:'Reconstructed; surviving relationships only'})[p.coverage] || p.coverage;
  function readout() {
    $('day-label').textContent = labelDate(days[current]);
    $('readout-date').textContent = `${labelDate(days[current])}, ${days[current].slice(0,4)} · UTC`;
    $('readout').replaceChildren();
    for (const line of active()) {
      const index = data.lines.indexOf(line), p = line.points[current];
      const row = html('div', $('readout'), undefined, 'reading');
      const title = html('div', row, undefined, 'reading-label');
      dot(title, index); html('span', title, line.label);
      html('div', row, fmt(mode === 'raw' ? p.raw_value : p.percent_change, mode === 'raw'), 'reading-value');
      html('small', row, `${fmt(p.raw_value, true)} ${line.unit}`);
      html('small', row, coverageText(p));
      const b = line.baseline;
      html('small', row, b.date ? `Baseline ${labelDate(b.date)}: ${fmt(b.value, true)}${b.status === 'later_baseline' ? ' · later than launch' : ''}` : 'Launch baseline unavailable');
      if (b.status === 'baseline_zero') html('small', row, 'Zero baseline: percentage change is undefined');
      if (p.related_values && line.metric_key === 'rating') html('small', row, `Interval ${fmt(p.related_values.rating_lower, true)}–${fmt(p.related_values.rating_upper, true)} · ${fmt(p.related_values.vote_count, true)} votes`);
      if (p.history_basis === 'reconstructed_current_relationships') html('small', row, 'Reconstructed from current relationships; removed likes/follows are excluded.');
      if (p.secondary_source) html('small', row, 'Historical community archive');
      if (line.direction === 'lower_is_better') html('small', row, 'Lower rank is better; positive % means a higher rank number.');
    }
  }
  function draw() {
    svg.querySelectorAll(':scope > :not(title):not(desc)').forEach(node => node.remove());
    const lines = active();
    const values = lines.flatMap(line => line.points.map(pointValue)).filter(v => v !== null && Number.isFinite(v));
    const transform = n => mode === 'compressed' ? Math.sign(n) * Math.log10(1 + Math.abs(n)) : n;
    const inverse = n => mode === 'compressed' ? Math.sign(n) * (10 ** Math.abs(n) - 1) : n;
    let low = transform(Math.min(0, ...values)), high = transform(Math.max(0, ...values));
    if (low === high) { low -= 1; high += 1; }
    const padding = (high-low)*.06; high += padding; low -= padding;
    const x = i => box.left + i / Math.max(1, days.length-1) * (box.right-box.left);
    const y = value => box.bottom - (transform(value)-low)/(high-low)*(box.bottom-box.top);
    const tick = value => {
      if (mode !== 'raw') return fmt(value);
      return new Intl.NumberFormat('en-US', {notation:'compact', maximumFractionDigits:1}).format(value);
    };
    const ticks = mode === 'compressed' && Math.max(Math.abs(low),Math.abs(high)) > 1
      ? [-100000000,-10000000,-1000000,-100000,-10000,-1000,-100,-10,0,10,100,1000,10000,100000,1000000,10000000,100000000].filter(v=>transform(v)>=low && transform(v)<=high)
      : Array.from({length:6},(_,i)=>inverse(low+(high-low)*i/5));
    for (const v of ticks) {
      const cy=y(v);
      element('line',{x1:box.left,y1:cy,x2:box.right,y2:cy,class:'grid'});
      element('text',{x:box.left-12,y:cy+4,'text-anchor':'end'},tick(v));
    }
    element('line',{x1:box.left,y1:y(0),x2:box.right,y2:y(0),class:'zero'});
    element('text',{x:box.left,y:18}, mode === 'raw' ? `${lines[0]?.unit || 'Value'} · original scale` : 'Change from baseline (%)');
    const tickIndices = new Set(Array.from({length:6},(_,i)=>Math.round(i*(days.length-1)/5)));
    for (const i of tickIndices) element('text',{x:x(i),y:box.bottom+27,'text-anchor':'middle'},labelDate(days[i]));
    const baselines = new Map();
    for (const line of lines) {
      if (line.baseline.status === 'later_baseline') baselines.set(line.baseline.date, line.source === 'arena' ? 'Arena begins' : `${line.source.toUpperCase()} baseline`);
    }
    for (const [date,label] of baselines) {
      const i=days.indexOf(date); if(i<0) continue;
      element('line',{x1:x(i),y1:box.top,x2:x(i),y2:box.bottom,class:'marker'});
      element('text',{x:x(i)+(i>days.length/2?-5:5),y:34,'text-anchor':i>days.length/2?'end':'start'},`${label} · ${labelDate(date)}`);
    }
    element('line',{x1:x(current),y1:box.top,x2:x(current),y2:box.bottom,class:'inspection'});
    for (const line of lines) {
      const color = colors[data.lines.indexOf(line)%colors.length];
      let path = '', previous = null;
      line.points.forEach((point,i)=>{
        const value=pointValue(point);
        if (value===null || !Number.isFinite(value)) { previous=null; return; }
        const px=x(i),py=y(value);
        if (previous === null) path+=` M ${px} ${py}`;
        else if (line.measurement_kind === 'state') path+=` H ${px} V ${py}`;
        else path+=` L ${px} ${py}`;
        previous=value;
        // Every actual observation is visible, including a single-point series.
        if (point.observed || i===current) {
          const circle=element('circle',{cx:px,cy:py,r:i===current?4:2.2,fill:point.coverage==='partial'?'white':color,stroke:color,'stroke-width':1.6});
          const title=document.createElementNS(ns,'title');
          title.textContent=`${line.label} · ${point.date}: ${fmt(mode==='raw'?point.raw_value:value,mode==='raw')} · ${coverageText(point)}`;circle.append(title);
        }
      });
      element('path',{d:path,stroke:color,class:'series','data-series':line.key});
    }
    if (!values.length) element('text',{x:470,y:210,'text-anchor':'middle'},'No values available for this view');
    $('chart-title').textContent = `${data.title} · ${mode==='raw'?'raw measurements':'change from baseline'}`;
    $('scale-explanation').textContent = mode==='compressed'
      ? 'Compressed scale: equal spacing represents larger percentage steps farther from zero. Labels and readouts show the actual change.'
      : mode==='linear' ? 'Linear scale: equal spacing represents equal percentage change. Large download changes can make other lines appear flat.'
      : 'Original provider values, one measurement at a time. Integer readouts retain their full precision.';
    readout();
  }
  function sources() {
    for (const [label,url] of [
      ['Arena leaderboard dataset · CC BY 4.0','https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset'],
      ['OpenRouter daily token totals · CC BY 4.0','https://openrouter.ai/rankings'],
      ['Hugging Face download definitions','https://huggingface.co/docs/hub/models-download-stats'],
    ]) {
      const p=html('p',$('source-details'));
      const link=html('a',p,label);link.href=url;link.target='_blank';link.rel='noopener noreferrer';
    }
    for (const credit of data.attributions || []) {
      const p=html('p', $('source-details'), credit.notice + ' ');
      const link=html('a',p,credit.publisher);link.href=credit.url;link.target='_blank';link.rel='noopener noreferrer';
      if (credit.license_url) { const license=html('a',p,' · '+credit.license);license.href=credit.license_url;license.target='_blank';license.rel='noopener noreferrer'; }
      if (credit.revision) html('small',p,' Revision '+credit.revision);
    }
    for (const line of data.lines) {
      const row=html('section',$('source-details'),undefined,'source-entry');
      html('h3',row,line.label);
      html('p',row,`Scope: ${line.subject.label || line.subject.key} · ${line.scope}. ${line.measurement_kind==='state'?'State at observation or publication':'Flow over a window'} · ${line.unit}.`);
      html('p',row,`Window: ${line.window_mode}${line.window_amount?' · '+line.window_amount:''}${line.window_unit?' '+line.window_unit:''}. Baseline: ${line.baseline.date || 'unavailable'} (${line.baseline.status.replaceAll('_',' ')}).`);
      const observed=line.points.filter(p=>p.observed);
      const sample=observed.at(-1);
      if (sample) {
        html('p',row,`Timing: ${sample.temporal_status || 'unknown'}; provider timezone: ${sample.source_timezone || 'unknown'}. Last observation: ${sample.source_date || sample.date}.`);
        if (sample.window_start_at) html('p',row,`Effective window: ${sample.window_start_at} to ${sample.window_end_at} (end exclusive).`);
        for (const e of sample.evidence || []) {
          if (e.source_identifier) html('p',row,`Provider identifier: ${e.source_identifier}`);
          if (e.source_as_of) html('p',row,`Source as of: ${e.source_as_of}`);
          if (e.archive) html('p',row,`Archive evidence: ${JSON.stringify(e.archive)}`);
        }
      }
      if (line.source==='hf' && line.metric_key==='downloads') html('p',row,'HF downloads are a rolling 30-day count. Historical community snapshots may have unknown cutoff time and timezone; they are not daily download totals.');
      if (line.source==='openrouter') html('p',row,'Usage covers OpenRouter only. A model missing from its available top-50 rows is not assigned zero.');
      if (line.source==='arena') html('p',row,`Overall text, ${line.source_configuration?.config==='text'?'no style control':'style-controlled'}. Published states carry forward between observations; score intervals and votes are retained in the evidence.`);
      const status=data.collection_status[line.source];
      if(status) html('p',row,`Last collection: ${status.status}; ${status.completed_at || status.last_attempt_at}.`);
      const health=data.collection_health?.[line.source];
      if(health) html('p',row,`Retrieval freshness: ${health.retrieval_freshness}. Effective date: ${health.latest_effective_date || 'unknown'} (${health.effective_freshness}).`);
    }
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
    $('download-data').href=url;
    window.addEventListener('pagehide',()=>URL.revokeObjectURL(url),{once:true});
  }
  async function start() {
    try {
      const endpoint=new URL(root.dataset.seriesUrl,location.origin);
      for (const key of ['start','end']) if(new URLSearchParams(location.search).has(key)) endpoint.searchParams.set(key,new URLSearchParams(location.search).get(key));
      const response=await fetch(endpoint,{headers:{Accept:'application/json'},cache:'no-store'});
      if(!response.ok) throw new Error('Measurements could not be loaded.');
      data=await response.json();
      days=data.lines[0].points.map(p=>p.date);
      current=days.length-1;
      data.lines.forEach((line,index)=>{
        visible.add(line.key);
        const button=html('button',$('legend'));
        button.type='button';button.dataset.line=line.key;button.setAttribute('aria-pressed','true');dot(button,index);html('span',button,line.label);
        button.addEventListener('click',()=>{if(visible.has(line.key)) visible.delete(line.key);else visible.add(line.key);button.setAttribute('aria-pressed',String(visible.has(line.key)));draw();});
        const option=html('option',$('raw-series'),line.label);option.value=line.key;
      });
      $('day').max=String(days.length-1);$('day').value=String(current);
      $('day').addEventListener('input',()=>{current=Number($('day').value);draw();});
      $('scale').addEventListener('change',()=>{mode=$('scale').value;$('raw-series').hidden=mode!=='raw';$('legend').hidden=mode==='raw';draw();});
      $('raw-series').addEventListener('change',draw);
      svg.addEventListener('click',event=>{const rect=svg.getBoundingClientRect();const px=(event.clientX-rect.left)*900/rect.width;current=Math.max(0,Math.min(days.length-1,Math.round((px-box.left)/(box.right-box.left)*(days.length-1))));$('day').value=String(current);draw();});
      $('launch-note').textContent=`Launch: ${data.launch_anchor.announced_date || data.launch_anchor.announced_at}. ${data.display_timezone} day labels; the announcement date does not imply a known announcement time.`;
      $('coverage-note').textContent='Gaps mean unavailable data. Hollow dots mark partial days. Dotted markers show baselines that begin after launch. Arena steps repeat the last published state.';
      sources();draw();$('chart-content').hidden=false;$('load-status').hidden=true;
    } catch(error) { $('load-status').textContent='Measurements are unavailable. Reload to try again.'; }
  }
  $('sources-open').addEventListener('click',()=>$('sources').showModal());
  $('sources-close').addEventListener('click',()=>$('sources').close());
  start();
})();
