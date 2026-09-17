import csv,json,hashlib
from decimal import Decimal as D
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
base=Path('docs/research/2026-09-17-143812-openrouter-pricing-snapshot')
manifest=json.loads((base/'manifest.json').read_text())
for name,digest in manifest['sha256'].items():assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest
models=list(csv.DictReader((base/'models.csv').open()));eps=list(csv.DictReader((base/'candidate-endpoints.csv').open()))
# Exact saved experimental token totals / source-post or submitted-commentary counts.
workloads={'classification':(D(45512)/40,D(5538)/40),'translation':(D(95535)/100,D(51298)/100),'commentary':(D(26747)/96,D(43638)/96)}
baseline=next(e for e in eps if e['model_id']=='deepseek/deepseek-v4-flash-0731' and e['endpoint_tag']=='deepinfra/fp8' and e['tier']=='base')
def costs(row):
 if not row['input_usd_per_million'] or not row['output_usd_per_million']:return {k:'' for k in workloads}
 i,o=D(row['input_usd_per_million']),D(row['output_usd_per_million'])
 return {k:(a*i+b*o)/1000 for k,(a,b) in workloads.items()}
bc=costs(baseline)
rows=[]
for r in models:
 c=costs(r);p=json.loads(r['pricing_json_original_units']);modal=json.loads(r['output_modalities']);im=json.loads(r['input_modalities'])
 text_eligible=im is not None and 'text' in im and modal==['text']
 special='batch' if ':batch' in r['model_id'] else 'moving_alias_or_router' if r['model_id'].startswith(('~','openrouter/')) else 'zero_or_free' if c['classification']==0 else 'standard'
 row={'model_id':r['model_id'],'price_basis':'catalog headline; endpoint not verified by this row','input_usd_per_million':r['input_usd_per_million'],'output_usd_per_million':r['output_usd_per_million'],'text_to_text_eligible':text_eligible,'offering':special,'has_price_overrides':bool(p.get('overrides')),'quality_on_our_tasks':'unscored in this catalog table; see experiment report for tested configurations','raw_pricing_json':r['pricing_json_original_units']}
 for k,v in c.items():
  row[k+'_usd_per_1000_fixed_workload']='' if v=='' else format(v,'.6f')
  row[k+'_within_2x_0731_screen']=text_eligible and special=='standard' and v!='' and v<=2*bc[k]
 rows.append(row)
stem=datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d-%H%M%S')+'-snapshot-only-model-task-cost-screen'
out=Path('docs/research')/stem;out.mkdir()
with (out/'all-model-task-costs.csv').open('x',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
by_id={m['model_id']:m for m in models}
def selected(model,tag=None):
 return next(e for e in eps if e['model_id']==model and e['endpoint_tag']==tag and e['tier']=='base') if tag else by_id[model]
selection=[('0731 baseline','deepseek/deepseek-v4-flash-0731','deepinfra/fp8','Measured baseline; material translation/commentary errors and provider failures.'),('Qwen 3.7 Flash','qwen/qwen3.7-flash','alibaba','First general-purpose trial; quality unknown; prompt must stay below 32K for quoted tier.'),('Gemini 2.5 Flash-Lite Flex','google/gemini-2.5-flash-lite','google-ai-studio/flex','Second general-purpose trial; quality unknown; Flex latency/availability must pass.'),('Hy-MT2-1.8B','tencent/hy-mt2-1.8b',None,'Translation-only specialist candidate, catalog-described; exact endpoint and language coverage not yet captured.'),('Hy-MT2-7B','tencent/hy-mt2-7b',None,'Larger translation specialist alternative; defer until smaller specialist result; endpoint not captured.'),('GPT-OSS-120B','openai/gpt-oss-120b',None,'Reserve classification/commentary trial; reasoning could inflate output; endpoint not captured.'),('GPT-5 Nano','openai/gpt-5-nano',None,'Reserve input-heavy classification trial; output/reasoning spend unknown; endpoint not captured.'),('4.1 Flash, off-peak','deepseek/deepseek-v4.1-flash','deepseek','Quality control was measured via direct API; displayed price here comes exclusively from saved OpenRouter endpoint, not a direct-provider quote.')]
lines=[]
for name,mid,tag,status in selection:
 r=selected(mid,tag);c=costs(r)
 lines.append('| '+ ' | '.join([name,r['input_usd_per_million'],r['output_usd_per_million']]+[format(c[k],'.3f') for k in workloads])+ ' |')
report=f'''# Snapshot-only model costs by task

Price source: `../{base.name}/manifest.json`, captured 2026-09-17. All source file hashes verified before analysis. No live price lookups or inference calls. [All {len(rows)} catalog entries, computed task costs](all-model-task-costs.csv).

This is a cost screen to identify models worth testing. It is not an intelligence ranking or proof of cost per successful result. Each row is repriced at the SAME observed task token volume, so tokenizer differences, extra reasoning, prompt changes, retries, completeness and actual quality remain unmeasured for untested candidates.

## Workloads

- Classification: 45,512 input and 5,538 output tokens / 40 source posts, two-role 20-post batches, 0731 R116. Includes observed multiple-brand work but is not a per-brand-row denominator.
- Translation: 95,535 input and 51,298 output tokens / 100 source posts, direct 4.1 frozen random-100. Includes all generated target languages; native copies do not add model calls.
- Commentary: 26,747 input and 43,638 output tokens / 96 submitted posts; each response covers three locales. Four pre-call cap rejections excluded. Production demand rate is separate.

Formula: cost per 1,000 task executions = (mean input tokens × input USD/M + mean output tokens × output USD/M) / 1,000. Uncached, base text usage, no reasoning multiplier, funding fees, tax, tool usage or retry costs. Costs are estimates, not actual bills.

## Candidate comparison

All prices USD/M; task cost columns USD per 1,000 posts at the fixed workload.

| Candidate | Input/M | Output/M | Classification | Translation | Commentary |
| --- | ---: | ---: | ---: | ---: | ---: |
'''+'\n'.join(lines)+'''

For the three task columns, cheaper does not mean better: some candidates are specialized for just one task. No quality score is inferred from parameter count, vendor descriptions, context window, valid JSON or price.

'''+ '\n'.join('- **'+name+'**: '+status for name,mid,tag,status in selection)+'''

## Suggested order, not model-selection decisions

1. Qwen 3.7 Flash and Gemini 2.5 Flash-Lite Flex: general-purpose comparison against stored 0731/4.1 controls, with each task scored independently.
2. Hy-MT2-1.8B: translation-only probe if a separately authorized endpoint snapshot and model instructions confirm required language pairs and prompt compatibility. Its existing catalog rate is only a screening quote. Keep unsupported languages on a measured general model rather than silently dropping them.
3. GPT-OSS-120B or GPT-5 Nano: reserve classifier candidates if the first group leaves semantic gaps. Cheap input helps, but hidden reasoning tokens can overturn the visible-output estimate.
4. Hy-MT2-7B: follow only if the smaller translation specialist makes a credible showing or reveals a capacity limit.

Schematron V2 Turbo is NOT prioritized merely for structured outputs: the saved catalog describes HTML-to-JSON extraction, which differs from our contextual multi-label social-post judgment. Prior NeMo/Ling failures remain relevant negatives, but they do not justify excluding every small model or every Qwen model.

## Screening scope and limitations

The CSV preserves all catalog entries, including free offerings, batch services, routers, non-text models and missing prices. The task screen flags only paid, concrete-ID, standard offerings accepting text and returning text alone. A model qualifies separately for a task when its catalog-based estimated cost is at most twice the tested 0731 endpoint cost. This 2× band is an analyst's exploratory screen, NOT an owner-approved spending ceiling or quality floor. A dedicated Flex endpoint can qualify even when its standard catalog row does not.

Do not rank free previews or batch offers as production replacements without separately evaluating their availability, latency and pricing conditions. Missing prices are unknown; zero rates alone are not proof that every usage dimension is free. Threshold and time-of-day overrides remain visible in the original snapshot; base-rate CSV costs require checking applicability.

Endpoint prices are authoritative for a selected route. The 0731 catalog headline is $0.06/$0.12 in this snapshot while our tested DeepInfra endpoint is $0.06/$0.18; silently substituting the headline would understate the tested route's output cost.

For a genuine two-axis cost/quality map, test the shortlist on fixed inputs. Plot separate maps for classification, translation and commentary; quality is presently UNKNOWN for new candidates. Preserve precision/recall and attribution mistakes for classification, fidelity errors for translation, unsupported claims for commentary, and operational failures separately. Exclude configuration failures from claims of semantic inferiority, but include them in usable-result economics.

Total monthly cost = classified posts × classifier unit cost + translated posts × translation unit cost + requested commentary posts × commentary unit cost + other LLM jobs (especially headlines). Do not multiply every post by commentary cost when commentary is on demand. Do not use these normalized costs to claim a verified $150 monthly forecast.
'''
counts={k:sum(bool(r[k+'_within_2x_0731_screen']) for r in rows) for k in workloads}
report+='\nTask-specific screen counts (catalog rows, not proven usable models): '+json.dumps(counts)+'.\n'
(out/'README.md').write_text(report)
(out/'analysis.py').write_bytes(Path(__file__).read_bytes())
(out/'provenance.json').write_text(json.dumps({'source_manifest':str(base/'manifest.json'),'source_manifest_sha256':hashlib.sha256((base/'manifest.json').read_bytes()).hexdigest(),'model_rows':len(rows),'workloads':{k:[str(i),str(o)] for k,(i,o) in workloads.items()},'screen_counts':counts,'price_source_exclusively_saved_snapshot':True},indent=2))
with (out/'all-model-task-costs.csv').open() as f:assert len(list(csv.DictReader(f)))==len(rows)
print('SAVED',out);print('\n'.join(lines));print('SCREEN COUNTS',counts)
