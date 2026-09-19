"""Bounded, offline NeMo/Ling comparison against the saved R101 Flash primary.

Reuses the frozen public packets, primary prompt, parser and scorer. No Django
database, production configuration, automatic retry, repair or fallback is used.
Raw transport evidence is saved before any semantic validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts import u18_single_primary_conditional_pilot as primary
from scripts.u18_openrouter_two_role_pilot import (
    DEFAULT_MANIFEST, DEFAULT_REFERENCE, ROOT, _json, _quality_release_gates,
    build_public_packets, score_candidate,
)
from x_monitor.openrouter import OpenRouterChatCompletionsClient

PRIVATE = ROOT / '.context/u18/low-cost-single-primary-r104-v1'
FLOORS = ROOT / 'docs/analysis/2026-09-11-002632-classification-quality-floors-v3.json'
GATES = ROOT / 'docs/analysis/2026-09-14-213123-u18-r98-control-fallback-pilot-contract.json'
CONTROL = ROOT / '.context/u18/single-primary-conditional-pilot-r101-v1/result.json'
MAX_OUTPUT = 6000
TIMEOUT = 180
CANDIDATES = {
    'mistral_nemo': {'model':'mistralai/mistral-nemo', 'provider':'dekallm/fp8', 'provider_name':'DekaLLM', 'aliases':['mistralai/mistral-nemo'], 'input':'.018', 'output':'.030', 'reasoning':None, 'json_mode':True, 'quantization':'fp8'},
    'ling_flash': {'model':'inclusionai/ling-3.0-flash', 'provider':'novita', 'provider_name':'Novita', 'aliases':['inclusionai/ling-3.0-flash','inclusionai/ling-3.0-flash-20260723'], 'input':'.021', 'output':'.063', 'reasoning':False, 'json_mode':False, 'quantization':None},
}


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.load(response)


def request_body(candidate, packet_batch=None):
    smoke = packet_batch is None
    client = OpenRouterChatCompletionsClient(
        api_key='', model=candidate['model'], provider=candidate['provider'],
        data_collection='deny', zdr=False,
        max_input_price=float(candidate['input']),
        max_output_price=float(candidate['output']),
        reasoning_enabled=candidate['reasoning'],
        quantizations=[candidate['quantization']] if candidate['quantization'] else None,
    )
    body = client.build_request(
        max_tokens=64 if smoke else MAX_OUTPUT, temperature=0,
        system='Return only a JSON object.' if smoke else primary._PRAGMATICS_FULL_SYSTEM_PROMPT,
        messages=[{'role':'user','content':'Return {"ok":true}.' if smoke else _json(primary.primary_input(packet_batch))}],
    )
    # Novita's Ling endpoint does not advertise response_format. Keep the
    # identical JSON instructions and strict parser, omit only that API knob.
    if not candidate['json_mode']:
        body.pop('response_format')
    return body


def reserve(body, candidate):
    # UTF-8 bytes plus framing overestimate input tokens for these tokenizers.
    input_bound = len(_json(body['messages']).encode()) + 2048
    return (Decimal(input_bound) * Decimal(candidate['input']) + Decimal(body['max_tokens']) * Decimal(candidate['output'])) / 1_000_000


def endpoint_check(candidate):
    catalog = fetch_json('https://openrouter.ai/api/v1/models/' + candidate['model'] + '/endpoints')
    endpoint = next(x for x in catalog['data']['endpoints'] if x['tag'] == candidate['provider'])
    assert endpoint['status'] == 0, 'endpoint unavailable'
    assert Decimal(endpoint['pricing']['prompt']) * 1_000_000 == Decimal(candidate['input']), 'input price changed'
    assert Decimal(endpoint['pricing']['completion']) * 1_000_000 == Decimal(candidate['output']), 'output price changed'
    body = request_body(candidate)
    requested = set(body) - {'model','messages','provider'}
    assert requested <= set(endpoint['supported_parameters']), 'unsupported API parameter'
    assert endpoint['max_completion_tokens'] >= MAX_OUTPUT
    policy = fetch_json('https://openrouter.ai/api/frontend/v1/all-providers')
    policy = next(x for x in policy['data'] if x['name'] == candidate['provider_name'])
    assert policy['dataPolicy']['training'] is False
    assert policy['dataPolicy']['retainsPrompts'] is False
    return {'observed_at':now(),'endpoint':endpoint,'policy':policy}


def prepare():
    contract_path = PRIVATE / 'contract.json'
    if contract_path.exists():
        raise ValueError('frozen contract already exists')
    packets, local = build_public_packets(read(DEFAULT_MANIFEST))
    assert len(packets) == 45
    assert hashlib.sha256(primary._PRAGMATICS_FULL_SYSTEM_PROMPT.encode()).hexdigest() == read(ROOT/'docs/analysis/2026-09-15-110900-u18-r101-single-primary-conditional-contract.json')['primary_prompt_sha256']
    requests = {}
    receipts = {}
    reserved = {}
    for key, candidate in CANDIDATES.items():
        receipts[key] = endpoint_check(candidate)
        requests[key] = [request_body(candidate)] + [request_body(candidate,b) for b in primary.chunks(packets)]
        reserved[key] = str(sum(reserve(b,candidate) for b in requests[key]))
        assert Decimal(reserved[key]) < Decimal('.05')
    write(PRIVATE/'public-packets.json', packets)
    write(PRIVATE/'local-join-map.json', local)
    write(PRIVATE/'requests.json', requests)
    write(PRIVATE/'catalog-receipts.json', receipts)
    sources = [DEFAULT_MANIFEST,DEFAULT_REFERENCE,FLOORS,GATES,CONTROL,Path(__file__),ROOT/'scripts/u18_single_primary_conditional_pilot.py',ROOT/'scripts/u18_openrouter_two_role_pilot.py',ROOT/'x_monitor/attribution.py',ROOT/'x_monitor/openrouter.py',ROOT/'core/classification_contract.py',PRIVATE/'public-packets.json',PRIVATE/'requests.json']
    contract = {
        'schema_version':'u18-r104-low-cost-primary/v1','frozen_at':now(),
        'owner_authorization':'Test Mistral NeMo first, then Ling 3.0; incumbent DeepSeek V4.1 Flash; target 10x lower cost per inference.',
        'control':'Reuse R101 primary only, same prompt and 20/20/5 packets; no conditional responses.',
        'candidates':CANDIDATES,'candidate_order':list(CANDIDATES),
        'caps':{'concurrency':1,'retries':0,'repairs':0,'fallbacks':0,'max_transports_per_candidate':4,'smoke_output_tokens':64,'batch_output_tokens':MAX_OUTPUT,'timeout_seconds':TIMEOUT,'hard_cap_usd':'.10','reserved_usd':reserved},
        'schedule':'One tiny JSON/route smoke, then the original 20/20/5 batches. Complete all three after successful smoke even if a semantic batch fails, to expose failure modes; do not repair or retry.',
        'cost_gate':'Total measured dollars per valid completed row must be <= 0.10 times the incumbent on the same workload. Report ordinary inference separately from one-time smoke, and show both peak and off-peak DS repricing plus OR fee sensitivity.',
        'quality':'Preserve all current floors; incomplete rows remain failures in the 45-row denominator. Per-row salvage is diagnostic only, never publication. This consumed owner corpus is development agreement, not unseen accuracy.',
        'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sources},
        'fresh_45_packet':'Excluded because it has no owner reference yet.',
        'production_changed':False,
    }
    write(contract_path, contract)
    print(_json({'contract':str(contract_path),'reserved_usd':reserved,'transports_max':8}),flush=True)


def secret():
    value = None
    for line in Path('/Users/fuchitalee/.env.secrets').read_text().splitlines():
        match = re.match(r'^\s*(?:export\s+)?OPENROUTER_API_KEY\s*=\s*(.*)$', line)
        if match:
            parts = shlex.split(match.group(1), comments=True)
            if len(parts) != 1:
                raise ValueError('OPENROUTER_API_KEY assignment must be one literal value')
            value = parts[0]
    if not value:
        raise ValueError('OPENROUTER_API_KEY is missing')
    return value


def key_usage(api_key):
    req = urllib.request.Request('https://openrouter.ai/api/v1/key',headers={'Authorization':'Bearer '+api_key})
    with urllib.request.urlopen(req,timeout=20) as response:
        data=json.load(response)['data']
    return {k:data.get(k) for k in ['usage','usage_daily','usage_monthly','limit','limit_remaining','is_free_tier']}


def transport(body, api_key, directory, name):
    started = time.monotonic()
    write(directory/(name+'-request.json'),body)
    request=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=_json(body).encode(),headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json','X-OpenRouter-Metadata':'enabled'})
    record={'started_at':now(),'status':'attempted','request_sha256':sha(directory/(name+'-request.json'))}
    try:
        with urllib.request.urlopen(request,timeout=TIMEOUT) as response:
            raw=response.read(); record['http_status']=response.status
        safe_raw=raw.decode().replace(api_key,'[REDACTED]')
        (directory/(name+'-raw-response.json')).write_text(safe_raw)
        record['raw_response_sha256']=sha(directory/(name+'-raw-response.json'))
        decoded=json.loads(safe_raw)
        record.update(status='received',usage=decoded.get('usage'),provider=decoded.get('provider'),model=decoded.get('model'),request_id=decoded.get('id'))
    except urllib.error.HTTPError as exc:
        raw=exc.read().decode(errors='replace').replace(api_key,'[REDACTED]')
        (directory/(name+'-http-error.txt')).write_text(raw)
        record.update(status='http_error',http_status=exc.code,error=raw[:1500]); decoded=None
    except Exception as exc:
        record.update(status='transport_error',error_type=type(exc).__name__); decoded=None
    record['latency_ms']=round((time.monotonic()-started)*1000)
    return decoded,record


def content_and_identity(decoded,candidate):
    assert isinstance(decoded,dict), 'missing response'
    assert decoded.get('model') in candidate['aliases'], 'model mismatch'
    selected=[x for x in decoded.get('openrouter_metadata',{}).get('endpoints',{}).get('available',[]) if x.get('selected') is True]
    provider=selected[0].get('provider') if len(selected)==1 else decoded.get('provider')
    assert provider in {candidate['provider_name'],candidate['provider'],'NovitaAI' if candidate['provider_name']=='Novita' else candidate['provider_name']}, 'provider mismatch'
    usage=decoded.get('usage') or {}
    assert isinstance(usage.get('prompt_tokens'),int), 'missing input usage'
    assert isinstance(usage.get('completion_tokens'),int), 'missing output usage'
    assert (usage.get('completion_tokens_details') or {}).get('reasoning_tokens',0) in (0,None), 'unexpected reasoning tokens'
    choice=decoded['choices'][0]
    assert choice['finish_reason']=='stop', 'non-stop finish: '+str(choice['finish_reason'])
    content=choice['message']['content']
    assert isinstance(content,str), 'missing text'
    return json.loads(content)


def diagnostic_rows(parsed,batch,index):
    """Retain valid independent rows for diagnosis without accepting a bad batch."""
    valid=[]; errors=[]
    if not isinstance(parsed,dict) or not isinstance(parsed.get('results'),list):
        return {'batch_index':index,'batch_size':len(batch),'merged':[],'failed_row_keys':[]}, ['response envelope invalid']
    for packet in batch:
        matches=[x for x in parsed['results'] if isinstance(x,dict) and x.get('tweet_id')==packet['tweet_id']]
        try:
            if len(matches)!=1: raise ValueError('missing or duplicate response ID')
            one=primary.parse_primary({'results':matches},[packet])
            valid.extend(primary.primary_result([packet],one,index)['merged'])
        except Exception as exc:
            errors.append({'tweet_id':packet['tweet_id'],'error':str(exc)})
    return {'batch_index':index,'batch_size':len(batch),'merged':valid,'failed_row_keys':[]}, errors


def run(key):
    contract=read(PRIVATE/'contract.json')
    for relative,expected in contract['source_sha256'].items():
        assert sha(ROOT/relative)==expected, 'frozen source changed: '+relative
    candidate=contract['candidates'][key]
    endpoint_check(candidate)
    directory=PRIVATE/key; directory.mkdir(parents=True,exist_ok=True)
    with (directory/'run-start.json').open('x') as f:
        json.dump({'started_at':now(),'contract_sha256':sha(PRIVATE/'contract.json')},f)
    api_key=secret()
    write(directory/'key-usage-before.json',key_usage(api_key))
    requests=read(PRIVATE/'requests.json')[key]
    packets=read(PRIVATE/'public-packets.json')
    result={'candidate':key,'measurements':[],'batches':[],'strict_valid_batches':0,'finished':False}
    attempted_reservation=Decimal(0)
    for index,body in enumerate(requests):
        attempted_reservation += reserve(body,candidate)
        assert attempted_reservation <= Decimal(contract['caps']['reserved_usd'][key])
        name='smoke' if index==0 else f'batch-{index-1}'
        decoded,record=transport(body,api_key,directory,name)
        record.update(stage=name,reserved_usd=str(reserve(body,candidate)))
        result['measurements'].append(record)
        try:
            parsed=content_and_identity(decoded,candidate)
            write(directory/(name+'-parsed-content.json'),parsed)
            if index==0:
                assert parsed=={'ok':True}, 'smoke content mismatch'
                record['semantic_status']='valid'
            else:
                batch=primary.chunks(packets)[index-1]
                try:
                    validated=primary.parse_primary(parsed,batch)
                    result['batches'].append(primary.primary_result(batch,validated,index-1))
                    result['strict_valid_batches']+=1
                    record['semantic_status']='valid'
                except Exception as exc:
                    salvaged,errors=diagnostic_rows(parsed,batch,index-1)
                    result['batches'].append(salvaged)
                    record.update(semantic_status='invalid_batch',semantic_error=str(exc),row_errors=errors)
        except Exception as exc:
            record.update(semantic_status='invalid_response',semantic_error=str(exc))
        record['valid_diagnostic_rows']=len(result['batches'][-1]['merged']) if index and len(result['batches']) and result['batches'][-1]['batch_index']==index-1 else 0
        write(directory/'result.json',result)
        print(_json({'candidate':key,'stage':name,'http_status':record.get('http_status'),'status':record.get('semantic_status'),'rows':record['valid_diagnostic_rows'],'latency_ms':record['latency_ms'],'usage':record.get('usage'),'error':record.get('semantic_error') or record.get('error')}),flush=True)
        if index==0 and record.get('semantic_status')!='valid':
            break
    result['finished']=True; result['finished_at']=now()
    write(directory/'result.json',result)
    write(directory/'key-usage-after.json',key_usage(api_key))
    score(key)


def score(key):
    result=read(PRIVATE/key/'result.json')
    local=read(PRIVATE/'local-join-map.json'); reference=read(DEFAULT_REFERENCE)
    floors=read(FLOORS)['floors']; gates=read(GATES)
    unsupported=gates['baseline_metrics']['per_label_support_and_f1']['unsupported']
    candidate_score=score_candidate(result,reference,local,floors,unsupported)
    control=read(CONTROL)
    control_score=score_candidate(control['primary'],reference,local,floors,unsupported)
    report={'candidate':key,'result':result,'score':candidate_score,'control_score':control_score,'quality_gates':_quality_release_gates(candidate_score,gates),'control_measurements':[x for x in control['measurements'] if x['stage']=='primary'],'limits':'Owner-development agreement; not unseen accuracy. Invalid batches have diagnostic row salvage only. No release or production changes.'}
    write(PRIVATE/key/'scored-report.json',report)
    print(_json({'candidate':key,'complete_rows':candidate_score['complete_rows'],'strict_valid_batches':result['strict_valid_batches'],'post_type_f1':candidate_score['micro_f1'],'exact_all_axes':candidate_score['exact_rows'],'report':str(PRIVATE/key/'scored-report.json')}),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['prepare','run','score'])
    parser.add_argument('--candidate',choices=CANDIDATES)
    args=parser.parse_args()
    if args.command=='prepare':prepare()
    elif args.candidate is None:parser.error('--candidate required')
    elif args.command=='run':run(args.candidate)
    else:score(args.candidate)


if __name__=='__main__':main()
