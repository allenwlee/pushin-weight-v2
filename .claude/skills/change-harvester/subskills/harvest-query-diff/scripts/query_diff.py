"""Expand saved Boolean queries and compare every branch. No network or DB I/O."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import itertools
import json
import math
import re
from pathlib import Path


TOKEN = re.compile(r'\s*(?:((?:-)?"(?:\\.|[^"\\])*")|([()]|-(?=\())|([^\s()"]+))')
MAX_BRANCHES = 100_000


def parse(query):
    """Strict OR/AND/NOT parser. Operators such as url: remain opaque atoms."""
    tokens, offset = [], 0
    while offset < len(query):
        if not query[offset:].strip():
            break
        m = TOKEN.match(query, offset)
        if not m:
            raise ValueError(f"invalid or unclosed token at character {offset}")
        tokens.append(next(x for x in m.groups() if x is not None))
        offset = m.end()
    pos = 0

    def primary():
        nonlocal pos
        if pos == len(tokens):
            raise ValueError("missing operand")
        token = tokens[pos]
        pos += 1
        if token in ('NOT', '-'):
            return ('not', primary())
        if token == '(':
            result = either()
            if pos == len(tokens) or tokens[pos] != ')':
                raise ValueError("unclosed group")
            pos += 1
            return result
        if token in ('OR', 'AND', ')'):
            raise ValueError(f"unexpected {token}")
        return ('atom', token)

    def both():
        nonlocal pos
        children = [primary()]
        while pos < len(tokens) and tokens[pos] not in ('OR', ')'):
            if tokens[pos] == 'AND':
                pos += 1
            children.append(primary())
        return ('and', children)

    def either():
        nonlocal pos
        children = [both()]
        while pos < len(tokens) and tokens[pos] == 'OR':
            pos += 1
            children.append(both())
        return ('or', children)

    result = either()
    if pos != len(tokens):
        raise ValueError("unconsumed query tokens")
    return result


def expand(node, *, negate=False):
    """Distribute AND over OR. Retain duplicate occurrences and their order."""
    kind, value = node
    if kind == 'atom':
        atom = (value[1:] if value.startswith('-') else '-' + value) if negate else value
        return [(atom,)]
    if kind == 'not':
        return expand(value, negate=not negate)
    if negate:
        kind = 'or' if kind == 'and' else 'and'
    children = [expand(child, negate=negate) for child in value]
    size = sum(map(len, children)) if kind == 'or' else math.prod(map(len, children))
    if size > MAX_BRANCHES:
        raise ValueError(f"{size} branches exceed explicit expansion limit {MAX_BRANCHES}; no truncation")
    if kind == 'or':
        return [branch for child in children for branch in child]
    return [tuple(itertools.chain.from_iterable(parts)) for parts in itertools.product(*children)]


def semantic_atom(atom):
    """Hyphen-as-space is a declared input assumption; periods stay literal."""
    negative = atom.startswith('-')
    raw = atom[1:] if negative else atom
    if ':' in raw and not raw.startswith('"'):
        return ('-' if negative else '') + raw.casefold()
    value = re.sub(r'(?<=\w)-(?=\w)', ' ', raw).casefold()
    return ('-' if negative else '') + value


def canonical(branch):
    atoms = set()
    for atom in branch:
        # The zero engagement floor is tautological; keep it in the displayed
        # original branch but ignore it for implication/equivalence checks.
        if atom.casefold() == 'min_faves:0':
            continue
        atom = semantic_atom(atom)
        if not atom.startswith(('"', '-')) and ':' not in atom:
            atoms.update(atom.split())
        else:
            atoms.add(atom)
    return frozenset(atoms)


def consequences(atoms):
    result = set(atoms)
    for atom in atoms:
        if atom.startswith('"') and atom.endswith('"'):
            words = atom[1:-1].split()
            result.update(words)
            # A longer exact phrase also guarantees each contiguous subphrase;
            # the reverse would incorrectly erase adjacency requirements.
            result.update(
                '"' + ' '.join(words[start:end]) + '"'
                for start in range(len(words))
                for end in range(start + 2, len(words) + 1)
            )
    return result


def implies(a, b):
    return b <= consequences(a)


def display(branch):
    terms = []
    for raw in branch:
        # Preserve source casing and quotation. Show unquoted hyphens as their
        # AND words; exact bytes remain in the query appendix and JSON.
        if not raw.startswith(('"', '-')) and ':' not in raw:
            terms.extend(re.sub(r'(?<=\w)-(?=\w)', ' ', raw).split())
        else:
            terms.append(raw)
    return ' AND '.join(terms)


def pretty(query):
    """Whitespace-only appendix formatting; phrases stay byte-identical."""
    parse(query)
    lines, line, depth = [], '', 0
    for match in TOKEN.finditer(query):
        token = next(x for x in match.groups() if x is not None)
        if token == '(':
            lines.append('    ' * depth + (line + ' ' if line else '') + '(')
            line = ''
            depth += 1
        elif token == ')':
            if line:
                lines.append('    ' * depth + line)
            depth -= 1
            line = ')'
        elif token == 'OR':
            if line:
                lines.append('    ' * depth + line)
            line = 'OR'
        else:
            line += (' ' if line else '') + token
    if line:
        lines.append('    ' * depth + line)
    result = '\n'.join(lines)
    if parse(result) != parse(query):
        raise ValueError('appendix formatting changed query meaning')
    return result


def inventory(manifest, prefix):
    rows = []
    for query in manifest['queries']:
        for branch_index, branch in enumerate(expand(parse(query['query'])), 1):
            rows.append({
                'id': f'{prefix}{len(rows)+1:04d}', 'call_id': query['call_id'],
                'branch_index': branch_index, 'atoms': list(branch),
                'text': display(branch), 'canonical': sorted(canonical(branch)),
                'lane': query.get('lane', 'tracked'),
                'blocks': query.get('blocks', []),
            })
    return rows


def compare(current, proposed):
    old, new = inventory(current, 'C'), inventory(proposed, 'P')
    used, comparisons = set(), []
    for row in old:
        a = frozenset(row['canonical'])
        candidates = [p for p in new if p['lane'] == row['lane']]
        same = [p for p in candidates if frozenset(p['canonical']) == a]
        wider = [p for p in candidates if implies(a, frozenset(p['canonical']))]
        narrower = [p for p in candidates if implies(frozenset(p['canonical']), a)]
        if same:
            status, matches = 'Equivalent', same
        elif wider:
            # All covering alternatives are printed. No single representative
            # is passed off as the complete correspondence.
            status, matches = 'Broader', wider
        elif narrower:
            status, matches = 'Narrower', narrower
        else:
            status, matches = 'Not guaranteed', []
        used.update(p['id'] for p in matches)
        comparisons.append({'current': row, 'proposed': matches, 'status': status})
    for row in new:
        if row['id'] not in used:
            comparisons.append({'current': None, 'proposed': [row], 'status': 'Added alternative'})
    # Prove every source occurrence and every proposed occurrence was displayed.
    assert [r['current']['id'] for r in comparisons if r['current']] == [r['id'] for r in old]
    assert {p['id'] for r in comparisons for p in r['proposed']} == {p['id'] for p in new}
    counts = {status: sum(r['status'] == status for r in comparisons) for status in (
        'Equivalent', 'Broader', 'Narrower', 'Not guaranteed', 'Added alternative')}
    return {'current_branches': old, 'proposed_branches': new, 'comparisons': comparisons, 'counts': counts}


def write_report(current, proposed, output, notes):
    result = compare(current, proposed)
    result.update(current_source=current.get('source'), proposed_source=proposed.get('source'), notes=notes)
    output.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    with output.with_suffix('.csv').open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['status','current_id','current_call','current_exact_branch','proposed_id','proposed_call','proposed_exact_branch'])
        for row in result['comparisons']:
            c = row['current'] or {}
            for p in row['proposed'] or [{}]:
                writer.writerow([row['status'],c.get('id'),c.get('call_id'),c.get('text'),p.get('id'),p.get('call_id'),p.get('text')])
    e = html.escape
    def cell(branches):
        if not branches:
            return '<span class="absent">No guaranteed equivalent route</span>'
        return ''.join(f'<div class="branch"><b>{e(b["id"])} · {e(b["call_id"])}</b><code>{e(b["text"])}</code></div>' for b in branches)
    rows = []
    for number, row in enumerate(result['comparisons'], 1):
        c = row['current']
        search = ' '.join([row['status'], (c['call_id'] + ' ' + c['text']) if c else '', *(p['call_id'] + ' ' + ' '.join(p['blocks']) + ' ' + p['text'] for p in row['proposed'])]).casefold()
        rows.append(f'<tr data-status="{e(row["status"])}" data-search="{e(search, quote=True)}"><td>{number}<small>{e(row["status"])}</small></td><td>{cell([c]) if c else "— No corresponding current branch"}</td><td>{cell(row["proposed"])}</td></tr>')
    def appendix(manifest):
        cards = []
        for q in manifest['queries']:
            text = q['query']; size = len(text.encode('utf-8'))
            blocks = ', '.join(q.get('blocks', []))
            formatted = q.get('formatted_query') or pretty(text)
            if parse(formatted) != parse(text):
                raise ValueError('formatted request differs from the exact query')
            cards.append(f'<details><summary>{e(q["call_id"])} · {size} UTF-8 bytes · {512-size} bytes spare · {e(blocks)}</summary><pre>{e(formatted)}</pre><details><summary>Exact one-line request</summary><pre>{e(text)}</pre></details></details>')
        return ''.join(cards)
    nold, nnew = len(result['current_branches']), len(result['proposed_branches'])
    source = e(str(current.get('source', ''))) + '<br>' + e(str(proposed.get('source', '')))
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Every harvest alternative</title><style>
body{font:15px/1.5 system-ui;margin:24px;color:#152334;background:#f7f9fc}h1{font-size:30px;margin-bottom:8px}p{max-width:1100px}code,pre{font:12px/1.55 ui-monospace,SFMono-Regular,monospace;white-space:pre-wrap;overflow-wrap:anywhere}code{display:block}.toolbar{position:sticky;top:0;background:#f7f9fc;padding:12px 0;z-index:2;display:flex;gap:12px;align-items:center}input{width:340px}input,select{padding:8px;font:inherit}table{width:100%;border-collapse:collapse;table-layout:fixed;background:white}th{text-align:left;background:#182b44;color:white}th,td{border:1px solid #d9e1eb;padding:9px;vertical-align:top}th:first-child{width:100px}small{display:block;font-size:11px}b{font-size:11px;color:#465e7a}.branch+.branch{border-top:1px dashed #ccd6e4;margin-top:8px;padding-top:8px}tr[data-status="Broader"]{background:#fff5dc}tr[data-status="Narrower"],tr[data-status="Not guaranteed"]{background:#ffe8e7}tr[data-status="Added alternative"]{background:#eaf5ff}.absent{color:#a62828}details{margin:10px 0}pre{background:white;padding:12px}li{margin:7px 0}@media print{.toolbar{position:static}tr{break-inside:avoid}body{margin:0}}
</style>'''
    document += f'<h1>Every harvest alternative</h1><p><strong>{nold} current branches → {nnew} proposed branches.</strong> Every OR is expanded and every AND combination is listed. All rows are visible initially. IDs count source occurrences, including duplicates; they are not post counts or proof of relevance.</p><p>{e(str(result["counts"]))}</p>'
    document += '<ul>' + ''.join('<li>'+e(note)+'</li>' for note in notes) + '</ul>'
    document += f'<p><a href="{e(output.with_suffix(".csv").name)}" download>Download every row as CSV</a> · <a href="{e(output.with_suffix(".json").name)}" download>Download the complete comparison as JSON</a></p>'
    document += '<p><small>'+source+'</small></p><div class="toolbar"><input id="search" placeholder="Filter terms, e.g. MiMo or NVIDIA"><select id="status"><option value="">All differences</option>'+''.join(f'<option>{e(s)}</option>' for s in result['counts'])+'</select><span id="count"></span><button id="reset">Show all</button></div><table><thead><tr><th>Row / effect</th><th>Current: one exact AND combination</th><th>Proposed: every corresponding AND combination</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
    document += '<h2>Exact full requests</h2><h3>Current</h3>'+appendix(current)+'<h3>Proposed</h3>'+appendix(proposed)
    document += '''<script>
const rows=[...document.querySelectorAll('tbody tr')],q=document.querySelector('#search'),s=document.querySelector('#status');function filter(){let n=0;for(const row of rows){const show=(!s.value||row.dataset.status===s.value)&&row.dataset.search.includes(q.value.toLowerCase());row.hidden=!show;if(show)n++}document.querySelector('#count').textContent=n+' / '+rows.length+' rows'}q.addEventListener('input',filter);s.addEventListener('change',filter);document.querySelector('#reset').addEventListener('click',()=>{q.value='';s.value='';filter()});filter();</script></html>'''
    output.write_text(document)
    return {'current_branches': nold, 'proposed_branches': nnew, 'comparison_rows': len(result['comparisons']), 'counts': result['counts'], 'html_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('current', type=Path)
    parser.add_argument('proposed', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--note', action='append', default=[])
    args = parser.parse_args()
    print(json.dumps(write_report(json.loads(args.current.read_text()), json.loads(args.proposed.read_text()), args.output, args.note), indent=2))
