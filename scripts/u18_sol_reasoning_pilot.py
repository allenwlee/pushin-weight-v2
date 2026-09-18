"""R106: paired GPT-5.6 Sol low/xhigh evaluation on the frozen owner corpus.

Experimental API settings only. Reuse the R101 prompt and R105 strict parser,
scorer, raw transport, and source packets. Never imported by the harvester.
"""
from __future__ import annotations

import argparse
import fcntl
import json
from decimal import Decimal
from pathlib import Path

from scripts import u18_nemo_adaptation_pilot as shared
from scripts.u18_openrouter_two_role_pilot import _quality_release_gates, score_candidate
from x_monitor.openrouter import OpenRouterChatCompletionsClient

old = shared.old
primary = shared.primary
ROOT = shared.ROOT
PRIVATE = ROOT / '.context/u18/sol-reasoning-r106-v1'
STEM = '2026-09-15-134818-u18-r106-sol-reasoning'
MODEL = 'openai/gpt-5.6-sol'
ALIAS = 'openai/gpt-5.6-sol-20260709'
EFFORTS = ('low', 'xhigh')
MAX_OUTPUT = 28000
TIMEOUT = 300
HARD_CAP = Decimal('2.50')
FEE_FACTOR = Decimal('1.055')
INPUT_PRICE = Decimal('2')
CACHE_WRITE_PRICE = Decimal('2.5')
OUTPUT_PRICE = Decimal('10')
write = shared.write


def request(batch, effort):
    if effort not in EFFORTS:
        raise ValueError('unfrozen effort')
    client = OpenRouterChatCompletionsClient(
        api_key='', model=MODEL, provider='openai', data_collection='allow',
        zdr=False, max_input_price=float(INPUT_PRICE), max_output_price=float(OUTPUT_PRICE),
    )
    body = client.build_request(
        max_tokens=MAX_OUTPUT, system=primary._PRAGMATICS_FULL_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': old._json(primary.primary_input(batch))}],
    )
    body['response_format'] = {'type': 'json_schema', 'json_schema': {
        'name': 'post_classification', 'strict': True,
        'schema': shared.response_schema(batch, compact=False),
    }}
    body['reasoning'] = {'effort': effort, 'exclude': True}
    return body


def reservation(body):
    # Include schema/framing and the more expensive cache-write rate in the
    # conservative input bound. Reasoning is INCLUDED in max_tokens/output.
    inputs = len(old._json(body).encode()) + 2048
    return (Decimal(inputs) * CACHE_WRITE_PRICE + Decimal(body['max_tokens']) * OUTPUT_PRICE) / 1_000_000 * FEE_FACTOR


def endpoint_check():
    catalog = old.fetch_json('https://openrouter.ai/api/v1/models/' + MODEL + '/endpoints')
    endpoint = next(e for e in catalog['data']['endpoints'] if e['tag'] == 'openai')
    assert endpoint['status'] == 0
    assert ALIAS in endpoint['name']
    assert Decimal(endpoint['pricing']['prompt']) * 1_000_000 == INPUT_PRICE
    assert Decimal(endpoint['pricing']['completion']) * 1_000_000 == OUTPUT_PRICE
    assert Decimal(endpoint['pricing']['input_cache_write']) * 1_000_000 <= CACHE_WRITE_PRICE
    assert endpoint['max_completion_tokens'] >= MAX_OUTPUT
    assert {'max_tokens', 'reasoning', 'response_format', 'structured_outputs'} <= set(endpoint['supported_parameters'])
    policy = next(p for p in old.fetch_json('https://openrouter.ai/api/frontend/v1/all-providers')['data'] if p['name'] == 'OpenAI')
    assert policy['dataPolicy']['training'] is False
    assert policy['dataPolicy'].get('trainingOpenRouter') is False
    return {'observed_at': old.now(), 'endpoint': endpoint, 'policy': policy}


def prepare():
    if (PRIVATE/'contract.json').exists():
        raise ValueError('contract already frozen')
    packets = old.read(old.PRIVATE/'public-packets.json')
    assert len(packets) == 45
    bodies = {effort: [request(batch, effort) for batch in primary.chunks(packets)] for effort in EFFORTS}
    for low, high in zip(bodies['low'], bodies['xhigh']):
        assert {k:v for k,v in low.items() if k != 'reasoning'} == {k:v for k,v in high.items() if k != 'reasoning'}
    reserved = sum(reservation(b) for requests in bodies.values() for b in requests)
    assert reserved < HARD_CAP
    receipt = endpoint_check()
    write(PRIVATE/'requests.json', bodies)
    write(PRIVATE/'public-packets.json', packets)
    write(PRIVATE/'provider-receipt.json', receipt)
    sources = [Path(__file__), ROOT/'scripts/u18_nemo_adaptation_pilot.py', ROOT/'scripts/u18_low_cost_single_primary_pilot.py', ROOT/'scripts/u18_single_primary_conditional_pilot.py', ROOT/'scripts/u18_openrouter_two_role_pilot.py', ROOT/'core/classification_contract.py', ROOT/'x_monitor/openrouter.py', ROOT/'x_monitor/attribution.py', old.DEFAULT_REFERENCE, old.FLOORS, old.GATES, old.CONTROL, old.PRIVATE/'local-join-map.json', PRIVATE/'requests.json', PRIVATE/'public-packets.json']
    contract = {
        'schema_version': 'u18-r106-sol-reasoning/v1', 'frozen_at': old.now(),
        'owner_authorization': 'Test frontier GPT-5.6 Sol and evaluate whether xhigh reasoning effort matters.',
        'model': MODEL, 'response_model_alias': ALIAS, 'provider': 'openai',
        'efforts': list(EFFORTS), 'execution_order': ['low_0', 'xhigh_0', 'xhigh_1', 'low_1', 'low_2', 'xhigh_2'],
        'batches': [20,20,5], 'prompt': 'Unchanged full R101 primary',
        'request_differences_between_arms': ['reasoning.effort'],
        'parameter_adaptation': 'Strict JSON schema, no temperature/top_p, no reasoning disable. 28,000 completion tokens include reasoning and final output. No tools, lookups, prior messages or answer-sheet data.',
        'budget': {'reserved_usd_including_5_5_percent_fee': str(reserved), 'hard_cap_usd_including_fee': str(HARD_CAP), 'max_transports': 6, 'concurrency': 1, 'retries': 0, 'repairs': 0, 'fallbacks': 0, 'max_tokens_per_request': MAX_OUTPUT, 'timeout_seconds': TIMEOUT},
        'prices_per_million': {'input': str(INPUT_PRICE), 'output': str(OUTPUT_PRICE), 'cache_read': '.2', 'cache_write': str(CACHE_WRITE_PRICE), 'discount': 'OpenRouter endpoint advertises 50% off standard $4/$20; verify before each pair'},
        'data_policy': 'Existing authorized public-X inputs only. OpenAI declares no training and retention possible. data_collection=allow, zdr=false, matching prior R98 OpenAI policy. Owner reference remains local.',
        'evaluation': 'Same consumed owner 45-case current-v3 reference, frozen sources and deterministic parser/scorer. Missing/invalid rows wrong on every exact axis. Show strict batches and independent-row diagnostics separately; no extra LLM judge. Preserve all quality floors. New unreviewed 45 not used.',
        'cost_comparison': 'Actual billed completion count already includes reasoning. Report reasoning separately without adding twice; normalize cache effects and regular pricing. Saved R101 primary usage repriced at current DeepSeek peak/offpeak. Frontier capability experiment, not a claim of tenfold saving or $150/mo compliance.',
        'limits': 'One run per effort on consumed development data, no unseen-generalization estimate. Same full prompt, no new author affiliations/media. Current-v3 only; future Audience Topics/Geopolitical axes absent. One job positive and no personnel/bug positives.',
        'source_sha256': {str(p.relative_to(ROOT)): old.sha(p) for p in sources},
    }
    write(PRIVATE/'contract.json', contract)
    write(ROOT/'docs/analysis'/(STEM+'-contract.json'), contract)
    write(PRIVATE/'ledger.json', {'attempts': [], 'reserved_usd_including_fee': '0'})
    print(old._json({'contract': str(PRIVATE/'contract.json'), 'reserved_usd_including_fee': str(reserved), 'requests': 6}), flush=True)


def parse_response(decoded):
    assert isinstance(decoded, dict), 'missing response'
    assert decoded.get('model') in {MODEL, ALIAS}, 'model identity mismatch'
    available = decoded.get('openrouter_metadata',{}).get('endpoints',{}).get('available',[])
    selected = [p for p in available if p.get('selected') is True]
    provider = selected[0].get('provider') if len(selected) == 1 else decoded.get('provider')
    assert provider in {'OpenAI','openai'}, 'provider identity mismatch'
    if selected and selected[0].get('model') is not None:
        assert selected[0]['model'] in {MODEL, ALIAS}, 'routed model mismatch'
    usage = decoded.get('usage') or {}
    assert isinstance(usage.get('prompt_tokens'), int)
    assert isinstance(usage.get('completion_tokens'), int) and usage['completion_tokens'] <= MAX_OUTPUT
    reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
    assert isinstance(reasoning, int) and 0 <= reasoning <= usage['completion_tokens'], 'missing/invalid reasoning accounting'
    assert isinstance(usage.get('cost'), (int,float)), 'missing billed cost'
    choice = decoded['choices'][0]
    assert choice['finish_reason'] == 'stop', 'incomplete: ' + str(choice['finish_reason'])
    content = choice['message'].get('content')
    assert isinstance(content, str), 'missing final output'
    return json.loads(content)


def transport(body, key, directory, name):
    # Reuse the verified raw-before-parse transport with this experiment's
    # timeout. This runs in an isolated CLI process with a single-flight lock.
    previous = old.TIMEOUT
    try:
        old.TIMEOUT = TIMEOUT
        return old.transport(body, key, directory, name)
    finally:
        old.TIMEOUT = previous


def score(effort):
    result = old.read(PRIVATE/effort/'result.json')
    strict = shared.metrics(result['strict_batches'])
    diagnostic = shared.metrics(result['batches'])
    raw = score_candidate({'batches': result['strict_batches']}, old.read(old.DEFAULT_REFERENCE), old.read(old.PRIVATE/'local-join-map.json'), old.read(old.FLOORS)['floors'], old.read(old.GATES)['baseline_metrics']['per_label_support_and_f1']['unsupported'])
    for axis in shared.AXES:
        if axis in ('post_types','product_labels'):
            raw['quality'][axis]['exact_set_accuracy']['value'] = strict['correct_by_axis'][axis]/45
        else:
            raw['quality'][axis]['accuracy'] = strict['correct_by_axis'][axis]/45
    gates = _quality_release_gates(raw, old.read(old.GATES))
    usage = {'prompt_tokens':0, 'cached_tokens':0, 'completion_tokens':0, 'reasoning_tokens':0, 'non_reasoning_completion_tokens':0}
    cost = Decimal(0)
    missing_usage = 0
    for m in result['measurements']:
        u=m.get('usage') or {}
        if not isinstance(u.get('cost'),(int,float)): missing_usage += 1
        cost += Decimal(str(u.get('cost',0)))
        usage['prompt_tokens'] += u.get('prompt_tokens',0)
        usage['cached_tokens'] += (u.get('prompt_tokens_details') or {}).get('cached_tokens',0)
        usage['completion_tokens'] += u.get('completion_tokens',0)
        usage['reasoning_tokens'] += (u.get('completion_tokens_details') or {}).get('reasoning_tokens',0)
    usage['non_reasoning_completion_tokens'] = usage['completion_tokens'] - usage['reasoning_tokens']
    cold_cost = (Decimal(usage['prompt_tokens'])*INPUT_PRICE + Decimal(usage['completion_tokens'])*OUTPUT_PRICE)/1_000_000
    output = {'effort':effort, 'strict':strict, 'diagnostic':diagnostic, 'quality_gates':gates,
              'all_quality_gates_pass':strict['valid_rows']==45 and all(g['passed'] for g in gates.values()),
              'valid_batches':len(result['strict_batches']), 'attempted_calls':len(result['measurements']),
              'finished':result.get('finished',False), 'usage':usage, 'billed_usd':str(cost),
              'billed_with_fee_usd':str(cost*FEE_FACTOR), 'cold_cache_current_price_usd':str(cold_cost),
              'normal_price_same_cache_estimate_usd':str(cost*2), 'normal_price_cold_cache_estimate_usd':str(cold_cost*2),
              'unknown_billing_calls':missing_usage, 'serial_seconds':sum(m['latency_ms'] for m in result['measurements'])/1000}
    write(PRIVATE/effort/'score.json',output)
    print(old._json({'effort':effort,'strict_rows':strict['valid_rows'],'post_type_f1':strict['labels']['post_types']['micro_f1'],'product_f1':strict['labels']['product_labels']['micro_f1'],'cost_usd':str(cost),'reasoning_tokens':usage['reasoning_tokens'],'quality_gates_pass':output['all_quality_gates_pass']}),flush=True)
    return output


def run():
    contract = old.read(PRIVATE/'contract.json')
    for relative, expected in contract['source_sha256'].items():
        assert old.sha(ROOT/relative)==expected, 'frozen source changed: '+relative
    with (PRIVATE/'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (PRIVATE/'run-start.json').open('x') as f:
            json.dump({'started_at':old.now(),'contract_sha256':old.sha(PRIVATE/'contract.json')},f)
        key=old.secret()
        write(PRIVATE/'key-usage-before.json',old.key_usage(key))
        packets=old.read(PRIVATE/'public-packets.json')
        requests=old.read(PRIVATE/'requests.json')
        results={e:{'effort':e,'measurements':[],'batches':[],'strict_batches':[],'finished':False} for e in EFFORTS}
        blocked=set()
        for stage in contract['execution_order']:
            effort, index=stage.rsplit('_',1); index=int(index)
            if effort in blocked: continue
            if index==0 or stage.startswith('xhigh_1') or stage.startswith('low_2'):
                write(PRIVATE/(stage+'-provider-receipt.json'),endpoint_check())
            body=requests[effort][index]; batch=primary.chunks(packets)[index]
            ledger=old.read(PRIVATE/'ledger.json')
            amount=reservation(body)
            assert len(ledger['attempts'])<6
            assert Decimal(ledger['reserved_usd_including_fee'])+amount <= HARD_CAP
            ledger['attempts'].append({'stage':stage,'started_at':old.now(),'reserved_usd_including_fee':str(amount)})
            ledger['reserved_usd_including_fee']=str(Decimal(ledger['reserved_usd_including_fee'])+amount)
            write(PRIVATE/'ledger.json',ledger)
            directory=PRIVATE/effort; directory.mkdir(exist_ok=True)
            decoded, record=transport(body,key,directory,f'batch-{index}')
            record.update(stage=stage,batch_index=index,batch_size=len(batch),requested_effort=effort)
            result=results[effort]; result['measurements'].append(record)
            write(directory/'result.json',result)
            try:
                parsed=parse_response(decoded)
                write(directory/f'batch-{index}-parsed.json',parsed)
                try:
                    validated=shared.validate(parsed,batch)
                    accepted=primary.primary_result(batch,validated,index)
                    result['strict_batches'].append(accepted);result['batches'].append(accepted)
                    record['contract_status']='valid'
                except Exception as exc:
                    diagnostic,errors=old.diagnostic_rows(parsed,batch,index)
                    result['batches'].append(diagnostic)
                    record.update(contract_status='invalid_batch',error=str(exc),row_errors=errors)
            except Exception as exc:
                record.update(contract_status='invalid_response',error=str(exc))
            write(directory/'result.json',result)
            print(old._json({'stage':stage,'status':record['contract_status'],'seconds':record['latency_ms']/1000,'usage':record.get('usage'),'error':record.get('error')}),flush=True)
            if record.get('http_status') in (400,404,422): blocked.add(effort)
        for effort,result in results.items():
            directory=PRIVATE/effort;directory.mkdir(exist_ok=True)
            result['finished']=len(result['measurements'])==3
            result['finished_at']=old.now()
            write(directory/'result.json',result)
            score(effort)
        write(PRIVATE/'key-usage-after.json',old.key_usage(key))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=('prepare','run','score'))
    parser.add_argument('--effort',choices=EFFORTS)
    args=parser.parse_args()
    if args.command=='prepare':prepare()
    elif args.command=='run':run()
    elif args.effort:score(args.effort)
    else:parser.error('--effort required')


if __name__=='__main__':main()
