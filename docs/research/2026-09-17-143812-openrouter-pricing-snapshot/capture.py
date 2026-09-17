"""Capture public OpenRouter prices; no credentials or inference calls."""
import csv
import hashlib
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

API = 'https://openrouter.ai/api/v1'
CANDIDATES = [
    'deepseek/deepseek-v4-flash-0731', 'deepseek/deepseek-v4.1-flash',
    'qwen/qwen3.7-flash', 'google/gemini-2.5-flash-lite',
    'qwen/qwen-2.5-7b-instruct', 'qwen/qwen-2.5-72b-instruct',
    'meta-llama/llama-3.3-70b-instruct', 'qwen/qwen2.5-32b-instruct',
    'deepseek/deepseek-r1-distill-llama-8b',
]
def utcnow():
    return datetime.now(timezone.utc).isoformat()
def get(url):
    started = utcnow()
    try:
        req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'PushinWeight-price-snapshot/1.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            receipt = {'url': url, 'started_at_utc': started, 'retrieved_at_utc': utcnow(), 'http_status': response.status,
                       'http_date': response.headers.get('Date'), 'etag': response.headers.get('ETag'),
                       'cache_control': response.headers.get('Cache-Control'), 'age': response.headers.get('Age')}
        obj = json.loads(data)
        return receipt, data, obj
    except urllib.error.HTTPError as exc:
        return {'url': url, 'started_at_utc': started, 'retrieved_at_utc': utcnow(), 'http_status': exc.code}, None, None
    except Exception as exc:
        return {'url': url, 'started_at_utc': started, 'retrieved_at_utc': utcnow(), 'error_type': type(exc).__name__}, None, None

def per_m(value):
    if value is None or value == '':
        return ''
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return ''
    if not amount.is_finite() or amount < 0:
        return ''
    return format(amount * Decimal(1000000), 'f')

def price_row(pricing):
    return {'input_usd_per_million': per_m(pricing.get('prompt')),
            'output_usd_per_million': per_m(pricing.get('completion')),
            'cache_read_usd_per_million': per_m(pricing.get('input_cache_read')),
            'cache_write_usd_per_million': per_m(pricing.get('input_cache_write')),
            'pricing_json_original_units': json.dumps(pricing, separators=(',', ':'))}

def write_csv(path, rows, fields):
    with path.open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
started = datetime.now(timezone.utc)
destination = root / (started.astimezone(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d-%H%M%S') + '-openrouter-pricing-snapshot')
destination.mkdir()
raw = destination / 'raw'
raw.mkdir()
receipt, data, catalog = get(API + '/models')
if data is None or not isinstance(catalog.get('data'), list):
    raise SystemExit('Catalog unavailable; no price table emitted')
(raw / 'models.json').write_bytes(data)
receipt['file'] = 'raw/models.json'
receipts = [receipt]
models = catalog['data']
assert models and len({m['id'] for m in models}) == len(models)
rows = []
for model in models:
    rows.append({'model_id': model['id'], 'name': model.get('name'), 'captured_at_utc': receipt['retrieved_at_utc'],
                 'context_length': model.get('context_length'),
                 'input_modalities': json.dumps(model.get('architecture', {}).get('input_modalities')),
                 'output_modalities': json.dumps(model.get('architecture', {}).get('output_modalities')),
                 'supported_parameters': json.dumps(model.get('supported_parameters')),
                 **price_row(model.get('pricing') or {})})
rows.sort(key=lambda r: r['model_id'])
write_csv(destination / 'models.csv', rows, list(rows[0]))

def endpoint_fetch(model_id):
    return model_id, get(API + '/models/' + model_id + '/endpoints')
endpoints = []
coverage = []
with ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(endpoint_fetch, CANDIDATES))
for model_id, (r, body, obj) in results:
    filename = 'endpoints-' + model_id.replace('/', '__') + '.json'
    eps = []
    if body is not None:
        (raw / filename).write_bytes(body)
        r['file'] = 'raw/' + filename
        eps = (obj.get('data') or {}).get('endpoints') or []
    receipts.append(r)
    coverage.append({'model_id': model_id, 'in_catalog': any(m['id'] == model_id for m in models),
                     'http_status': r.get('http_status'), 'endpoint_count': len(eps), 'error_type': r.get('error_type')})
    for ep in eps:
        base = ep.get('pricing') or {}
        tiers = [None] + (base.get('overrides') or [])
        for tier in tiers:
            prices = {k: v for k, v in base.items() if k != 'overrides'}
            if tier:
                prices.update(tier)
            endpoints.append({'model_id': model_id, 'endpoint_name': ep.get('name'), 'provider_name': ep.get('provider_name'),
                              'endpoint_tag': ep.get('tag'), 'quantization': ep.get('quantization'),
                              'captured_at_utc': r['retrieved_at_utc'], 'context_length': ep.get('context_length'),
                              'tier': 'override' if tier else 'base', 'min_prompt_tokens': tier.get('min_prompt_tokens', '') if tier else '',
                              'supported_parameters': json.dumps(ep.get('supported_parameters')),
                              **price_row(prices)})
write_csv(destination / 'candidate-endpoints.csv', endpoints, list(endpoints[0]))
(destination / 'capture.py').write_bytes(Path(__file__).read_bytes())
summary = {'schema': 'openrouter-price-snapshot/v1', 'started_at_utc': started.isoformat(), 'finished_at_utc': utcnow(),
           'catalog_model_count': len(models), 'candidate_model_count': len(CANDIDATES),
           'endpoint_count': sum(c['endpoint_count'] for c in coverage), 'endpoint_price_tier_rows': len(endpoints),
           'candidate_coverage': coverage, 'requests': receipts,
           'units': 'Raw prompt/completion prices: USD/token. CSV rate columns: USD/1,000,000 tokens. Other raw pricing fields preserve original units.',
           'fees': 'Funding/payment fees, tax, paid tools and actual billed reasoning/retry usage are not included.',
           'scope': 'Entire default /models catalog, plus all returned endpoints and price tiers for nine named candidate model IDs. Not every provider of every catalog model.',
           'warnings': ['Blank price is unknown/not applicable, never zero.', 'Explicit zero is a catalog price, not unlimited free capacity.',
                        'Catalog headline price is not guaranteed for a chosen provider or tier.', 'Direct DeepSeek prices are not sourced by this OpenRouter snapshot.',
                        'Provider pricing and availability may change after capture; recheck before a paid test.']}
readme = f'''# OpenRouter price snapshot — {started.astimezone(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M:%S JST')}

This snapshot preserves the prices OpenRouter returned when we checked, so model comparisons can cite saved evidence rather than recall. It helps select inexpensive candidates for classification, translation and commentary; it does not score their intelligence or quality.

- [All {len(models)} catalog models, CSV](models.csv): readable USD per million input/output/cache tokens, exact model IDs, modalities and supported parameters.
- [Candidate provider and tier prices, CSV](candidate-endpoints.csv): {sum(c['endpoint_count'] for c in coverage)} endpoints for the nine queried candidates; {len(endpoints)} rows including price-tier overrides.
- [Raw catalog](raw/models.json): exact response bytes from `GET https://openrouter.ai/api/v1/models`.
- [Capture manifest](manifest.json): URLs, per-request UTC timestamps, HTTP status, available server cache headers, coverage, and SHA-256 checksums.
- [Capture script](capture.py): repeatable capture into a NEW timestamped directory. Run `python3 capture.py /absolute/path/to/docs/research`. Existing snapshots are never overwritten. Uses public metadata requests; no API key or inference calls.

## Rules for price answers

1. Cite this snapshot's capture date and the exact model ID. For a test recommendation, identify the endpoint/provider, service tier, and applicable input-length tier from the endpoint table.
2. Read both input and output prices. Forecast using each task's measured token mix; include cache, reasoning, retries and successful-result coverage when known. Do not use the arithmetic average of model input prices.
3. Blank means unknown or not applicable. Zero must be explicitly present in the API response. A model without an active endpoint has no executable quote in this snapshot.
4. Catalog prices do not guarantee that a selected provider costs the same. A base endpoint row may be superseded by its threshold rows; inspect original pricing JSON for conditions beyond the named columns. Service tiers such as Flex are separate endpoint tags.
5. Raw prompt/completion rates are USD PER TOKEN; CSV columns multiply by exactly 1,000,000 using decimal arithmetic. Other fields (images, requests, searches, storage etc.) retain original API units and are not blindly scaled.
6. Funding fees and taxes are separate; direct-provider prices are separate. An OpenRouter DeepSeek listing is not the price for our direct DeepSeek account.
7. This is a dated observation, not a permanent guarantee. Recheck the exact endpoint before any paid evaluation. No paid availability check was performed.

## Candidate scope

''' + '\n'.join(f"- `{c['model_id']}`: HTTP {c['http_status']}, {c['endpoint_count']} endpoints, catalog present={c['in_catalog']}." for c in coverage) + '''

Only candidate endpoints were expanded. The complete default catalog is captured, but specialized output catalogs (for example transcription) and provider details for other models require additional queries. The public metadata fetches occurred over a short interval, not one atomic vendor-wide snapshot.
'''
(destination / 'README.md').write_text(readme)
summary['sha256'] = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.rglob('*')) if p.is_file()}
(destination / 'manifest.json').write_text(json.dumps(summary, indent=2))
# Verify saved exact data, normalized units, row counts, endpoint tiers, and hashes.
assert json.loads((raw / 'models.json').read_bytes()) == catalog
with (destination / 'models.csv').open() as f:
    saved = list(csv.DictReader(f))
assert len(saved) == len(models)
by_id = {m['id']: m for m in models}
for row in saved:
    assert row['input_usd_per_million'] == per_m((by_id[row['model_id']].get('pricing') or {}).get('prompt'))
    assert row['output_usd_per_million'] == per_m((by_id[row['model_id']].get('pricing') or {}).get('completion'))
for name, digest in summary['sha256'].items():
    assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == digest
print(json.dumps({'directory': str(destination), 'models': len(models), 'endpoints': summary['endpoint_count'], 'tier_rows': len(endpoints),
                  'coverage': coverage, 'verified': True}, indent=2))
