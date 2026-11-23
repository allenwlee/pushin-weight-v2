"""Blind chronological replay of a saved personalized trends watch."""
import argparse
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re

from monitor.editorial import chatter_windows as windows

BASE = Path(__file__).resolve().parents[1]
PROFILE = BASE / 'config/editorial-chatter-staging.yaml'
SCOPE = 'chatter-staging-20261119-u51'
LIMIT = Decimal('50')
STEP = timedelta(minutes=30)


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def write(path, obj):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


def read(path):
    return json.loads(path.read_bytes())


def observations(path):
    obs, terminals = [], {}
    for line in path.read_text().splitlines():
        r = json.loads(line)
        clock = windows.instant(r['scheduled_at_jst'])
        slot = clock.replace(minute=clock.minute // 15 * 15, second=0, microsecond=0)
        if slot in terminals:
            raise ValueError('duplicate scheduled slot')
        receipt = windows.instant(r['observed_at_jst']) if r.get('observed_at_jst') else None
        terminals[slot] = receipt
        if r.get('success') and r['status'] == 200:
            if receipt is None:
                raise ValueError('successful capture missing receipt time')
            obs.append(dict(slot=slot.isoformat(), observed_at=receipt.isoformat(),
                            request_id=f"watch-slot-{r['slot']}", headlines=r['payload']['data']))
    if not terminals:
        raise ValueError('empty watch')
    return obs, terminals


def bounds(terminals):
    start, end = min(terminals), max(terminals)
    if start.minute % 30:
        start += windows.QUARTER
    while start <= end:
        terminal = terminals.get(start)
        yield start, min(terminal, start + windows.GRACE) if terminal else start + windows.GRACE
        start += STEP


def profile():
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
    django.setup()
    from monitor.editorial.config import load_editorial_config
    return load_editorial_config(PROFILE)


def manifest(path, labels_sha256, cfg):
    from monitor.editorial.providers import text_reservation
    if not re.fullmatch('[a-f0-9]{64}', labels_sha256):
        raise ValueError('supply the frozen SHA256 of the separate labels file')
    obs, terminals = observations(path)
    cutoffs = list(bounds(terminals))
    if not 1 <= len(cutoffs) <= 28:
        raise ValueError('expected 1 to 28 decision boundaries')
    size = cfg.max_packet_bytes + cfg.max_schema_bytes + 30000
    route = cfg.chatter.ranking
    worst = text_reservation(route, bytes(size))
    sources = [Path(__file__), Path(windows.__file__), windows.PROMPT,
               Path(__file__).with_name('chatter_replay_score.py'), PROFILE]
    return {'watch_sha256':checksum(path.read_bytes()), 'labels_sha256':labels_sha256,
            'algorithm_sha256':{s.name:checksum(s.read_bytes()) for s in sources},
            'route':route.model_dump(mode='json'), 'scope':SCOPE,'limit_usd':str(LIMIT),
            'successful_snapshots':len(obs),'returned_rows':sum(len(o['headlines']) for o in obs),
            'wordings':len({windows.wording(h['trend_name']) for o in obs for h in o['headlines']}),
            'window_count':len(cutoffs),'max_wire_bytes':size,'worst_per_call_usd':str(worst),
            'worst_total_usd':str(worst*len(cutoffs))}


def guard(status, worst):
    if status['scope'] != SCOPE or Decimal(str(status['limit_usd'])) != LIMIT:
        raise ValueError('wrong trial scope or limit')
    used = Decimal(str(status['exposure_usd']))
    if not used.is_finite() or used < 0 or used + worst > LIMIT:
        raise ValueError('insufficient authorized balance')


@contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def run(path, labels_hash, out, adapter):
    cfg = profile()
    from monitor.editorial.providers import request_fingerprint, request_payload, text_reservation
    m = manifest(path, labels_hash, cfg)
    route = cfg.chatter.ranking
    obs, terminals = observations(path)
    with locked(out):
        mpath = out / 'manifest.json'
        if mpath.exists() and read(mpath) != m:
            raise ValueError('frozen manifest changed')
        completed = sum((out / f'{n:02}-receipt.json').exists() for n in range(m['window_count']))
        guard(adapter.budget_status(), Decimal(m['worst_per_call_usd'])*(m['window_count']-completed))
        if not mpath.exists():
            write(mpath, m)
        history, decisions = {}, []
        for n,(cutoff, freeze) in enumerate(bounds(terminals)):
            packet = windows.decision_packet([o for o in obs if windows.instant(o['observed_at']) <= freeze],
                                             cutoff, history)
            data, receipt_info = None, None
            if packet['needs_ranking']:
                body = request_payload(route, windows.selection_request(packet))
                wire, digest = request_fingerprint(body)
                if len(wire) > m['max_wire_bytes']:
                    raise ValueError('request exceeds preflight limit')
                reserve = text_reservation(route, wire)
                stage = f'chatter-replay-{n:02}'
                claim = {'request_sha256':digest,'model':route.model,'stage':stage,'reserved_usd':str(reserve)}
                fence, receipt = out / f'{n:02}-request.json', out / f'{n:02}-receipt.json'
                if fence.exists():
                    if read(fence) != claim or not receipt.exists():
                        raise ValueError(f'{stage} needs receipt reconciliation before resuming')
                    stored = read(receipt)
                    if stored['claim'] != claim:
                        raise ValueError('receipt mismatch')
                else:
                    if receipt.exists():
                        raise ValueError('orphan receipt')
                    guard(adapter.budget_status(), reserve)
                    write(fence, claim)
                    result = adapter.rank(stage=stage, route=route, body=body, request_sha256=digest,
                                          reserved_usd=str(reserve), directory=out)
                    stored = {'claim':claim,'result':result}
                    write(receipt, stored)
                result = stored['result']
                if result['model'] != route.model or not result['call_id']:
                    raise ValueError('provider route or call ID mismatch')
                usage = result['usage']
                charge = usage.get('provider_reported_cost_usd')
                if charge is not None and not (0 <= Decimal(str(charge)) <= reserve):
                    raise ValueError('provider charge outside reservation')
                receipt_info = {**claim,'call_id':result['call_id'],'usage':usage,
                                'receipt_sha256':checksum(receipt.read_bytes())}
                data = result['data']
            # The worker holds an invalid decision and uses its most recent
            # committed history at the next boundary. Never repeat the paid call.
            try:
                selection = windows.apply_selection(packet, data)
            except ValueError as error:
                if receipt_info is None:
                    raise
                selection = {'leads': [], 'expired': []}
                held = str(error)
            else:
                history = selection['history']
                held = None
            decisions.append({'cutoff':cutoff.isoformat(),'freeze':freeze.isoformat(),
                'missing_slots':packet['missing_slots'],'receipt':receipt_info,'leads':selection['leads'],
                'pending':history.get('pending', []),'held':held,'expired':selection['expired']})
            write(out / f'{n:02}-decision.json', decisions[-1])
        frozen = {'manifest_sha256':checksum(mpath.read_bytes()),'decisions':decisions,
                  'trailing_quarter_hours':int((max(terminals)-windows.instant(decisions[-1]['cutoff']))/windows.QUARTER)}
        write(out / 'decisions.json', frozen)
        return {'decisions_sha256':checksum((out/'decisions.json').read_bytes()),
                'windows':len(decisions),'calls':sum(d['receipt'] is not None for d in decisions)}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('mode',choices=['preflight','run','score'])
    parser.add_argument('--snapshots', required=True,type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--labels-sha256')
    parser.add_argument('--labels',type=Path)
    parser.add_argument('--adapter',type=Path)
    parser.add_argument('--exposure-usd',type=Decimal)
    args = parser.parse_args()
    if args.mode == 'score':
        from scripts.chatter_replay_score import score
        result = score(args.snapshots,args.labels,args.output)
    elif args.mode == 'preflight':
        result = manifest(args.snapshots,args.labels_sha256,profile())
        if args.exposure_usd is None:
            parser.error('preflight requires --exposure-usd')
        guard({'scope':SCOPE,'limit_usd':LIMIT,'exposure_usd':args.exposure_usd}, Decimal(result['worst_total_usd']))
    else:
        if args.labels or not args.adapter or not args.output:
            parser.error('run requires --adapter and --output, with only label digest as input')
        spec = importlib.util.spec_from_file_location('chatter_replay_operator',args.adapter)
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        result = run(args.snapshots,args.labels_sha256,args.output,adapter)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
