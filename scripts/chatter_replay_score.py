"""Offline scoring rubric. Match original wording to the frozen screen's row IDs."""
from collections import Counter, defaultdict
from decimal import Decimal

from monitor.editorial.chatter_windows import HORIZON, instant, wording
from scripts.chatter_replay import checksum, observations, read, write


def capacity(decisions, slots):
    """Hold observed rankings fixed, then drain remaining eligible episodes by rank."""
    pending, done, traces = {}, set(), []
    for d in decisions:
        now = instant(d['freeze'])
        pending = {k:e for k,e in pending.items() if instant(e['last_seen']) > now-HORIZON}
        ranked = {}
        for e in d['leads'] + d['pending']:
            key = (e['episode_id'],e['material_change'])
            if key not in done:
                ranked[key] = e
        pending = {**ranked, **{k:e for k,e in pending.items() if k not in ranked}}
        admitted = list(pending)[:slots]
        for k in admitted:
            pending.pop(k)
            done.add(k)
        traces.append({'cutoff':d['cutoff'],'admitted':[i[0] for i in admitted],
                       'queue_size':len(pending),'oldest_pending_first_observed':min(
                           (h['first_seen'] for e in pending.values() for h in e['headlines']),default=None)})
    return {'slots':slots,'count':len(done),'windows':traces,'end_pending':[k[0] for k in pending]}


def score(path, labels_path, directory):
    frozen = read(directory/'decisions.json')
    manifest = read(directory/'manifest.json')
    if (checksum(labels_path.read_bytes()) != manifest['labels_sha256']
            or checksum(path.read_bytes()) != manifest['watch_sha256']
            or checksum((directory/'manifest.json').read_bytes()) != frozen['manifest_sha256']):
        raise ValueError('frozen inputs differ')
    labels = read(labels_path)
    obs,_ = observations(path)
    rows = {e['row']:wording(e['headline']) for e in labels['entries']}
    by_word = defaultdict(set)
    topics = {t['topic_key']:t['decision'] for t in labels['topics']}
    for t in labels['topics']:
        for n in t['headline_rows']:
            by_word[rows[n]].add(t['topic_key'])
    first = {}
    offsets = []
    for interval in (15,30,60):
        for offset in range(0,interval,15):
            words = set()
            for o in obs:
                if instant(o['slot']).minute % interval != offset:
                    continue
                for h in o['headlines']:
                    w = wording(h['trend_name'])
                    words.add(w)
                    if interval == 15:
                        for f in by_word[w]:
                            first[f] = min(instant(o['observed_at']),first.get(f,instant(o['observed_at'])))
            fams = set().union(*(by_word[w] for w in words))
            offsets.append({'interval':interval,'offset':offset,'wordings':len(words),
                            'strong_families':sorted(f for f in fams if topics[f]=='strong')})
    seen, possible, unrelated, mixed, duplicates, updates = {}, set(), {}, [], [], []
    decisions = frozen['decisions']
    for d in decisions:
        for e in d['leads']:
            fams = set().union(*(by_word[w] for w in e['wordings']))
            if e['material_change']:
                updates.append({'cutoff':d['cutoff'],'title':e['title'],'reason':e['material_change']})
            if len(fams)>1 or (fams and any(not by_word[w] for w in e['wordings'])):
                mixed.append({'title':e['title'],'families':sorted(fams),'cutoff':d['cutoff']})
            elif not fams:
                unrelated[e['episode_id']] = e['title']
            else:
                f = next(iter(fams))
                if topics[f] == 'strong':
                    if f in seen:
                        duplicates.append({'family':f,'cutoff':d['cutoff'],'material_change':e['material_change']})
                    else:
                        seen[f] = {'first_capture':first[f].isoformat(),'first_selected':d['freeze'],
                                   'minutes':round((instant(d['freeze'])-first[f]).total_seconds()/60,2)}
                else:
                    possible.add(f)
    strong = {k for k,v in topics.items() if v=='strong'}
    calls = [d['receipt'] for d in decisions if d['receipt']]
    costs = [c['usage'].get('provider_reported_cost_usd') for c in calls]
    tokens = Counter()
    for c in calls:
        tokens.update({k:v for k,v in c['usage'].items() if 'tokens' in k and type(v) is int})
    report = {'decisions_sha256':checksum((directory/'decisions.json').read_bytes()),
              'strong_hits':seen,'strong_total':len(strong),'misses':sorted(strong-set(seen)),
              'possible_extras':sorted(possible),'unrelated_extra_episodes':unrelated,'mixed_review':mixed,
              'duplicates':duplicates,'proposed_material_updates':updates,
              'calls':len(calls),'skips':len(decisions)-len(calls),'tokens':dict(tokens),
              'reported_usd':str(sum((Decimal(str(c)) for c in costs if c is not None),Decimal(0))),
              'unknown_cost_reserved_usd':str(sum((Decimal(c['reserved_usd']) for c,v in zip(calls,costs) if v is None),Decimal(0))),
              'capture_coverage':offsets,'capacity_simulation':[capacity(decisions,s) for s in (1,2)],
              'end_pending':[e['title'] for e in decisions[-1]['pending']],
              'startup_missing_slots':decisions[0]['missing_slots'],'trailing_quarter_hours':frozen['trailing_quarter_hours'],
              'censored_families':sorted(set().union(*(by_word[w] for e in decisions[-1]['pending']
                                       for w in e['wordings']))-set(seen))}
    write(directory/'score.json',report)
    return report
