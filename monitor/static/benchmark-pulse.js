/* Read-only Pulse: values, baselines and evidence come from the shared series API. */
(() => {
  'use strict';
  const root = document.querySelector('#pulse');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const translations=JSON.parse($('pulse-labels')?.textContent || '{}');
  const t=text=>translations[text] || text;
  const colors = ['#4485c6', '#ba921d', '#9169c3', '#30978e', '#d78449', '#b75b78', '#60777f'];
  const ns = 'http://www.w3.org/2000/svg';
  let data, days, current = 0, mode = 'compressed', smoothing = '3', responseView = false;
  const visible = new Set();
  const svg = $('pulse-chart');
  const box = {left: 83, right: 872, top: 45, bottom: 385};
  const fmt = (value, raw = false) => {
    if (value === null || value === undefined) return t('Not available');
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
  const pointValue = p => p && (mode === 'raw' ? (p.raw_value === null ? null : Number(p.raw_value)) : (responseView && smoothing === '1' ? p.daily_percent_change : p.percent_change));
  const launchDate = () => data.launch_anchor.announced_date || data.launch_anchor.announced_at.slice(0,10);
  const axisDate = date => $('date-axis')?.value === 'relative' ? `Day ${Math.round((Date.parse(date)-Date.parse(launchDate()))/86400000)}` : labelDate(date);
  const active = () => data.lines.filter(line => mode === 'raw' ? line.key === $('raw-series').value : visible.has(line.key));
  const displayLabel = line => line.interpretation ? 'Arena · rank (release history)' : line.label;
  const coverageText = p => ({carried_forward:`Last published ${p.source_date}`, partial:'Partial day', missing:'No observation', missing_adjacent_snapshot:'Adjacent actual HF snapshots unavailable', not_reported_top50:'Not reported in available top-50 usage data', observed:'Observed', reconstructed:'Reconstructed; surviving relationships only'})[p.coverage] || p.coverage;
  function readout() {
    $('day-label').textContent = labelDate(days[current]);
    $('readout-date').textContent = `${labelDate(days[current])}, ${days[current].slice(0,4)} · UTC`;
    $('readout').replaceChildren();
    for (const line of active()) {
      const index = data.lines.indexOf(line), p = line.points[current];
      const row = html('div', $('readout'), undefined, 'reading');
      const title = html('div', row, undefined, 'reading-label');
      dot(title, index); html('span', title, displayLabel(line));
      html('div', row, fmt(mode === 'raw' ? p.raw_value : pointValue(p), mode === 'raw'), 'reading-value');
      html('small', row, `${fmt(p.raw_value, true)} ${line.unit}`);
      html('small', row, coverageText(p));
      if (p.proxy_label) html('small', row, p.proxy_label);
      else if (p.measured_subject) html('small', row, `Measured model: ${p.measured_subject.label}`);
      if (p.model_changed) html('small', row, 'Model changed · first successor evaluation');
      const b = line.baseline;
      html('small', row, responseView ? (b.date ? `${t('Reference mean')}: ${fmt(b.value, true)} ${line.unit}` : t('Reference week unavailable')) : (b.date ? `Baseline ${labelDate(b.date)}: ${fmt(b.value, true)}${b.status === 'later_baseline' ? ' · later than launch' : ''}` : 'Launch baseline unavailable'));
      if (responseView && smoothing === '3' && mode !== 'raw') html('small', row, `${t('Three-day mean')}: ${fmt(p.smoothed_value, true)} ${line.unit}`);
      if (p.provider_raw_value !== undefined) html('small', row, `${t('Reported rolling 30-day counter')}: ${fmt(p.provider_raw_value, true)}`);
      if (b.status === 'reference_nonpositive') html('small', row, t('Nonpositive reference mean: percentage change is unavailable'));
      if (line.source === 'opencode') html('small', row, t('OpenCode Go + free traffic only'));
      if (b.measured_subject) html('small', row, `Baseline model: ${b.measured_subject.label}${b.proxy ? ' · previous release proxy' : ''}`);
      if (b.status === 'baseline_zero') html('small', row, 'Zero baseline: percentage change is undefined');
      if (p.related_values && line.metric_key === 'rating') html('small', row, `Interval ${fmt(p.related_values.rating_lower, true)}–${fmt(p.related_values.rating_upper, true)} · ${fmt(p.related_values.vote_count, true)} votes`);
      if (p.history_basis === 'reconstructed_current_relationships') html('small', row, 'Reconstructed from current relationships; removed likes/follows are excluded.');
      if (p.secondary_source) html('small', row, 'Historical community archive');
      if (line.direction === 'lower_is_better') html('small', row, 'Lower rank is better; rank % is not a change in model capability.');
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
    element('text',{x:box.left,y:18}, mode === 'raw' ? `${lines[0]?.unit || 'Value'} · original scale` : (responseView ? t(data.normalization_label) : 'Change from baseline (%)'));
    if (responseView && data.reference.dates.length) {
      const first = Math.max(0, (Date.parse(data.reference.dates[0])-Date.parse(days[0]))/86400000);
      const last = Math.min(days.length-1, (Date.parse(data.reference.dates.at(-1))-Date.parse(days[0]))/86400000);
      if (first <= last) {
        const band=element('rect',{x:x(first),y:box.top,width:Math.max(1,x(last)-x(first)),height:box.bottom-box.top,fill:'#e6eef6','fill-opacity':'.6',class:'reference-band'});
        svg.insertBefore(band,svg.querySelector('line.grid'));
      }
    }
    const tickIndices = new Set(Array.from({length:6},(_,i)=>Math.round(i*(days.length-1)/5)));
    for (const i of tickIndices) element('text',{x:x(i),y:box.bottom+27,'text-anchor':'middle'},axisDate(days[i]));
    const baselines = new Map();
    for (const line of lines) {
      if (line.baseline.status === 'later_baseline') baselines.set(line.baseline.date, line.source === 'arena' ? 'Arena begins' : `${line.source.toUpperCase()} baseline`);
    }
    for (const [date,label] of baselines) {
      const i=days.indexOf(date); if(i<0) continue;
      element('line',{x1:x(i),y1:box.top,x2:x(i),y2:box.bottom,class:'marker'});
      element('text',{x:x(i)+(i>days.length/2?-5:5),y:34,'text-anchor':i>days.length/2?'end':'start'},`${label} · ${labelDate(date)}`);
    }
    if (responseView || data.lines.some(line => line.interpretation)) {
      const launch = data.launch_anchor.announced_date || data.launch_anchor.announced_at?.slice(0,10);
      const events = [[launch, 'Launch'], ...lines.filter(line => line.interpretation?.switch_date).map(line => [line.interpretation.switch_date, 'Model changed'])];
      events.forEach(([date,label], index) => {
        const i=days.indexOf(date); if (i<0) return;
        element('line',{x1:x(i),y1:box.top,x2:x(i),y2:box.bottom,class:'baseline','data-event':label});
        element('text',{x:x(i)+(i>days.length/2?-5:5),y:34+index*14,'text-anchor':i>days.length/2?'end':'start'},`${label} · ${labelDate(date)}`);
      });
    }
    element('line',{x1:x(current),y1:box.top,x2:x(current),y2:box.bottom,class:'inspection'});
    for (const line of lines) {
      const color = colors[data.lines.indexOf(line)%colors.length];
      let path = '', proxyPath = '', previous = null, previousSegment = null;
      line.points.forEach((point,i)=>{
        const value=pointValue(point);
        if (value===null || !Number.isFinite(value)) { previous=null; return; }
        const px=x(i),py=y(value);
        let piece;
        if (previous === null || previousSegment !== point.segment) piece=` M ${px} ${py}`;
        else if (line.measurement_kind === 'state') piece=` H ${px} V ${py}`;
        else piece=` L ${px} ${py}`;
        if (point.proxy) proxyPath+=piece; else path+=piece;
        previous=value; previousSegment=point.segment;
        // Every actual observation is visible, including a single-point series.
        if (point.observed || i===current) {
          const circle=element('circle',{cx:px,cy:py,r:i===current?4:2.2,fill:point.coverage==='partial'?'white':color,stroke:color,'stroke-width':1.6});
          const title=document.createElementNS(ns,'title');
          title.textContent=`${displayLabel(line)} · ${point.date}: ${fmt(mode==='raw'?point.raw_value:value,mode==='raw')} · ${coverageText(point)}${point.proxy_label ? ' · '+point.proxy_label : ''}`;circle.append(title);
        }
      });
      element('path',{d:path,stroke:color,class:'series','data-series':line.key});
      if (proxyPath) element('path',{d:proxyPath,stroke:color,fill:'none','stroke-width':2,'stroke-dasharray':'6 4',class:'series-proxy','data-series':line.key});
    }
    if (!values.length) element('text',{x:470,y:210,'text-anchor':'middle'},'No values available for this view');
    $('chart-title').textContent = `${data.title} · ${mode==='raw'?'raw measurements':responseView?data.normalization_label:'change from baseline'}`;
    $('scale-explanation').textContent = mode==='compressed'
      ? 'Compressed scale: equal spacing represents larger percentage steps farther from zero. Labels and readouts show the actual change.'
      : mode==='linear' ? (responseView ? `${t('Linear scale')} · ${t(smoothing==='3'?'trailing three-day means':'daily values')} · ${t('relative to fixed raw reference-week means')}.` : 'Linear scale: equal spacing represents equal percentage change. Large download changes can make other lines appear flat.')
      : 'Original provider values, one measurement at a time. Integer readouts retain their full precision.';
    readout(); drawArena();
  }
  function drawArena() {
    const panel=data.arena_panel, target=$('arena-chart');
    if (!panel || !target) return;
    target.querySelectorAll(':scope > :not(title)').forEach(node=>node.remove());
    const add=(tag,attrs={},text)=>{const node=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));if(text!==undefined)node.textContent=text;target.append(node);return node;};
    const x=i=>box.left+i/Math.max(1,days.length-1)*(box.right-box.left);
    const rank=$('arena-measurement').value==='rank';
    for (const [field,top,bottom,color,label] of [[rank?'rank':'score',35,165,'#30978e',t(rank?'Rank · lower is better':'Arena score')],['battles',210,292,'#ba921d',t('Reported battles')]]) {
      const numeric=panel.points.flatMap(p=>field==='score'?[p.score,p.lower,p.upper]:[p[field]]).filter(v=>v!==null&&v!==undefined).map(Number);
      let low=Math.min(...numeric),high=Math.max(...numeric);
      if (!numeric.length) {add('text',{x:box.left,y:top+30},`${label} · Not available`);continue;}
      if (low===high) {low-=1;high+=1;}
      const padding=(high-low)*.1; low-=padding;high+=padding;
      const y=v=>rank&&field==='rank'?top+(Number(v)-low)/(high-low)*(bottom-top):bottom-(Number(v)-low)/(high-low)*(bottom-top);
      add('text',{x:box.left,y:top-12},label);
      for (let i=0;i<3;i++) {const value=low+(high-low)*i/2;const cy=y(value);add('line',{x1:box.left,x2:box.right,y1:cy,y2:cy,class:'grid'});add('text',{x:box.left-10,y:cy+4,'text-anchor':'end'},new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(value));}
      let path='',previous=null;
      panel.points.forEach((point,i)=>{
        const value=point[field];
        if(value===null||value===undefined){previous=null;return;}
        const px=x(i),py=y(value);
        path+=previous!==null&&(field!=='score'||point.segment===previous.segment)?` H ${px} V ${py}`:` M ${px} ${py}`;
        previous=point;
        if(point.actual_publication){
          if(field==='score'&&point.lower!==null&&point.upper!==null){add('line',{x1:px,x2:px,y1:y(point.lower),y2:y(point.upper),stroke:color,'stroke-width':10,'stroke-opacity':'.18',class:'confidence-interval'});}
          const dot=add('circle',{cx:px,cy:py,r:3.5,fill:color,class:'publication-point','data-date':point.publication_date});
          const title=document.createElementNS(ns,'title');title.textContent=`Published ${point.publication_date}: ${value}`;dot.append(title);
        }
      });
      add('path',{d:path,fill:'none',stroke:color,'stroke-width':1.7,'stroke-dasharray':'4 3',class:`arena-${field}`});
    }
    add('line',{x1:x(current),x2:x(current),y1:25,y2:292,class:'inspection'});
    for(const i of new Set(Array.from({length:6},(_,i)=>Math.round(i*(days.length-1)/5))))add('text',{x:x(i),y:320,'text-anchor':'middle'},axisDate(days[i]));
    const point=panel.points[current];
    $('arena-readout').textContent=`${panel.source_identifiers.join(', ')} · ${labelDate(point.date)} · ${t('Score')} ${fmt(point.score,true)} · ${t('interval')} ${fmt(point.lower,true)}–${fmt(point.upper,true)} · ${t('Reported battles')} ${fmt(point.battles,true)} · ${t('rank')} ${fmt(point.rank,true)} · ${t(point.actual_publication?'actual publication':point.publication_date?'held published state':'unavailable')} ${point.publication_date||''} · ${t('score comparability')} ${point.comparability}; ${t('source timezone')} ${point.source_timezone}.`;
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
      html('h3',row,displayLabel(line));
      if (line.interpretation) html('p',row,'Dashed rank segment: previous release proxy. The measured model changes at its first valid Arena evaluation; this is not a single model improving. '+line.interpretation.rationale);
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
      if (responseView && line.source==='hf') html('p',row,'HF line is the net change between adjacent observed rolling counters, not new daily downloads. Missing snapshots create gaps; negative changes are retained.');
      if (line.source==='opencode') html('p',row,'OpenCode Go + free traffic only; external-provider client traffic is excluded. Tokens include input, output, cache read and cache write. Daily users and sessions are approximate distinct counts; never sum these across models. Current UTC-day reports are partial; hourly refreshes are revised daily totals, not hourly usage.');
      const status=data.collection_status[line.source];
      if(status) html('p',row,`Last collection: ${status.status}; ${status.completed_at || status.last_attempt_at}.`);
      const health=data.collection_health?.[line.source];
      if(health) html('p',row,`Retrieval freshness: ${health.retrieval_freshness}. Effective date: ${health.latest_effective_date || 'unknown'} (${health.effective_freshness}).`);
    }
    if (data.arena_panel) {
      html('h3',$('source-details'),'Arena evaluation history');
      html('p',$('source-details'),`Exact model: ${data.arena_panel.source_identifiers.join(', ')}. Overall text, no style control. ${data.arena_panel.battle_semantics} ${data.arena_panel.score_comparability} ${data.arena_panel.time_alignment}`);
    }
    if (responseView) html('p',$('source-details'),`Reference ${data.reference.dates.join(' to ')}; revision ${data.reference.revision}. Dependency dates ${data.dependency_range.start} to ${data.dependency_range.end}. Each line uses its own raw mean. Controls preserve these denominators; corrections produce a new revision.`);
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
    $('download-data').href=url;
    window.addEventListener('pagehide',()=>URL.revokeObjectURL(url),{once:true});
  }
  async function start() {
    try {
      const endpoint=new URL(root.dataset.seriesUrl,location.origin);
      for (const key of ['start','end']) if(new URLSearchParams(location.search).has(key)) endpoint.searchParams.set(key,new URLSearchParams(location.search).get(key));
      const preload=$('pulse-preloaded');
      if(preload) data=JSON.parse(preload.textContent);
      else {const response=await fetch(endpoint,{headers:{Accept:'application/json'},cache:'no-store'});if(!response.ok) throw new Error('Measurements could not be loaded.');data=await response.json();}
      responseView=data.chart_kind==='release_response_v1';
      if(responseView) {mode='linear';$('scale').value='linear';$('reference-note').textContent=data.reference.dates.length?`${t('Reference week')}: ${labelDate(data.reference.dates[0])}–${labelDate(data.reference.dates.at(-1))} · ${t('fixed raw means')} · ${data.reference.revision.slice(0,12)}`:t('A common complete reference week is unavailable. Raw values remain inspectable.');}
      days=data.lines[0].points.map(p=>p.date);
      current=days.length-1;
      data.lines.forEach((line,index)=>{
        visible.add(line.key);
        const button=html('button',$('legend'));
        button.type='button';button.dataset.line=line.key;button.setAttribute('aria-pressed','true');dot(button,index);html('span',button,displayLabel(line));
        button.addEventListener('click',()=>{if(visible.has(line.key)) visible.delete(line.key);else visible.add(line.key);button.setAttribute('aria-pressed',String(visible.has(line.key)));draw();});
        const option=html('option',$('raw-series'),displayLabel(line));option.value=line.key;
      });
      $('day').max=String(days.length-1);$('day').value=String(current);
      $('day').addEventListener('input',()=>{current=Number($('day').value);draw();});
      $('scale').addEventListener('change',()=>{mode=$('scale').value;$('raw-series').hidden=mode!=='raw';$('legend').hidden=mode==='raw';draw();});
      $('raw-series').addEventListener('change',draw);
      if(responseView){
        $('smoothing').addEventListener('change',()=>{smoothing=$('smoothing').value;draw();});
        $('date-axis').addEventListener('change',draw);
        $('arena-measurement')?.addEventListener('change',drawArena);
        $('usage-provider')?.addEventListener('change',()=>{const url=new URL($('usage-provider').value,location.origin);url.search=location.search;location.assign(url);});
        $('range').disabled=Boolean(preload);
        $('range').value=new URLSearchParams(location.search).has('start')?'available':'release';
        $('range').addEventListener('change',()=>{const url=new URL(location.href);if($('range').value==='available'){url.searchParams.set('start',data.available_range.start);url.searchParams.set('end',data.available_range.end);}else{url.searchParams.delete('start');url.searchParams.delete('end');}location.assign(url);});
      }
      svg.addEventListener('click',event=>{const rect=svg.getBoundingClientRect();const px=(event.clientX-rect.left)*900/rect.width;current=Math.max(0,Math.min(days.length-1,Math.round((px-box.left)/(box.right-box.left)*(days.length-1))));$('day').value=String(current);draw();});
      let hoverFrame;
      const inspect=event=>{const rect=event.currentTarget.getBoundingClientRect();const px=(event.clientX-rect.left)*900/rect.width;const day=Math.max(0,Math.min(days.length-1,Math.round((px-box.left)/(box.right-box.left)*(days.length-1))));if(day===current)return;cancelAnimationFrame(hoverFrame);hoverFrame=requestAnimationFrame(()=>{current=day;$('day').value=String(current);draw();});};
      if(responseView){svg.addEventListener('pointermove',inspect);$('arena-chart')?.addEventListener('pointermove',inspect);}
      $('launch-note').textContent=`Launch: ${data.launch_anchor.announced_date || data.launch_anchor.announced_at}. ${data.display_timezone} day labels; the announcement date does not imply a known announcement time.`;
      $('coverage-note').textContent=responseView?'Gaps mean unavailable evidence. HF changes are net rolling-counter differences. Arena dots are actual publications; dashed steps hold published states. Co-moving lines do not establish causation.':'Gaps mean unavailable data. Hollow dots mark partial days. Dotted markers show baselines that begin after launch. Arena steps repeat the last published state.';
      sources();draw();$('chart-content').hidden=false;$('load-status').hidden=true;
    } catch(error) { $('load-status').textContent='Measurements are unavailable. Reload to try again.'; }
  }
  $('sources-open').addEventListener('click',()=>$('sources').showModal());
  $('sources-close').addEventListener('click',()=>$('sources').close());
  start();
})();
