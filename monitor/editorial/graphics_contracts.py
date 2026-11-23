"""Load and assemble the task-specific Graphics prompt contracts."""

import copy
import json
import math
import re
from pathlib import Path

from jsonschema import validate


def load_pack(path):
    pack = json.loads(Path(path).read_text())
    calls = pack['model_call_plan']['calls']
    ids = [call['id'] for call in calls]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate Graphics stage')
    return pack


def build_task(instruction, data, schema):
    return (
        instruction
        + '\n\nSUPPLIED INPUTS:\n'
        + json.dumps(data, ensure_ascii=False, indent=2)
        + '\n\nOUTPUT JSON SCHEMA FOR THIS REQUEST:\n'
        + json.dumps(schema, ensure_ascii=False, indent=2)
        + '\nReturn valid JSON only, without Markdown wrapping or additional prose.'
    )


def copy_writer_route(value):
    """Only the configured native writer and existing Graphics transport are bound.

    Other editorial roles may use other providers; that does not give Graphics
    a C1 transport contract or authorize falling back to another writer.
    """
    from .config import Route

    route = Route.model_validate(value)
    if route.endpoint not in {
        'https://api.openai.com/v1/chat/completions',
        'https://openrouter.ai/api/v1/chat/completions',
    }:
        raise ValueError('unsupported Graphics C1 writer route')
    return route


WRITER_LED = 'chatter-writer-led/v1'


def writer_led(handoff):
    return handoff.get('copy_contract') == WRITER_LED


def bind_copy_contract(pack, handoff):
    """Bind the one C1/publication contract to this saved edition, without edits
    to the literal shared pack or another Copy Editor request.
    """
    from .voices import Voice

    locale = handoff.get('locale', 'en')
    languages = {'en': 'English', 'ja': 'Japanese', 'zh-cn': 'Simplified Chinese'}
    if locale not in languages:
        raise ValueError('unsupported Copy Editor locale')
    voice = None
    if 'voice' in handoff:
        voice = Voice.model_validate(handoff['voice'])
        if (voice.locale != locale or voice.track != 'chatter' or not voice.available
                or not voice.instructions.strip() or voice.digest != handoff.get('voice_hash')):
            raise ValueError('invalid saved Copy Editor voice')
    result = copy.deepcopy(pack)
    if writer_led(handoff):
        path = Path(__file__).resolve().parents[2] / 'config/editorial_prompts/chatter-writer-led-v1.json'
        overrides = json.loads(path.read_text())
        for item in result['model_call_plan']['calls']:
            stage = item['id']
            if stage not in overrides:
                continue
            item.update(overrides[stage])
            props = item['response_schema']['properties']
            entries = props['candidates' if stage == 'C1' else 'treatments']
            entries.update(minItems=1, maxItems=1)
            schema = entries['items']
            schema['properties']['id' if stage == 'C1' else 'candidate_id'] = {'const': 'A'}
            if stage == 'C1':
                props['schema_version'] = {'const': WRITER_LED}
                for field in ('still_pitch', 'motion_prompt'):
                    schema['properties'][field] = {'type': 'string', 'minLength': 1}
                    if field not in schema['required']:
                        schema['required'].append(field)
        result['copy_contract'] = WRITER_LED
    call = next(item for item in result['model_call_plan']['calls'] if item['id'] == 'C1')
    call['response_schema']['properties']['locale'] = {'const': locale}
    result['publication_schema']['properties']['locale']['const'] = locale
    call['system'] = call['system'].replace(
        'Write the complete publication copy in English (en).',
        f'Write the complete publication copy in {languages[locale]} ({locale}).',
    )
    if voice:
        # Native saved instructions replace the English example's publication
        # voice, while the accepted C1 evidence/task/creative boundary stays exact.
        system = call['system']
        role_start, role_end = system.index('# Newsroom role\n'), system.index('# Jurisdiction\n')
        system = system[:role_start] + '# Newsroom role\nYou are the Copy Editor for the saved publication voice below.\n\n' + system[role_end:]
        start, end = system.index('# Locked publication voice\n'), system.index('# Requested output language\n')
        call['system'] = system[:start] + '# Locked publication voice\n' + voice.instructions + '\n\n' + system[end:]
    return result


def build_messages(pack, stage, data, *, instruction=None):
    if stage == 'C1':
        pack = bind_copy_contract(pack, data)
    call = next((item for item in pack['model_call_plan']['calls'] if item['id'] == stage), None)
    if call is None or 'response_schema' not in call:
        raise ValueError('Unknown Graphics language-model stage')
    return {
        'system': call['system'],
        'task': build_task(instruction if instruction is not None else call['user'], data, call['response_schema']),
    }


def validate_stage_output(pack, stage, response):
    """Validate provider output and the cross-candidate identity invariant."""
    call = next((item for item in pack['model_call_plan']['calls'] if item['id'] == stage), None)
    if call is None or 'response_schema' not in call:
        raise ValueError('Unknown Graphics language-model stage')
    validate(response, call['response_schema'])
    expected = ['A'] if pack.get('copy_contract') == WRITER_LED else ['A', 'B']
    if stage == 'C1' and [item['id'] for item in response['candidates']] != expected:
        raise ValueError('Expected one candidate ' + ' and one '.join(expected))
    if stage == 'G0' and sorted(item['candidate_id'] for item in response['approaches']) != ['A', 'B']:
        raise ValueError('Expected one Graphics approach for A and one for B')
    if stage == 'G1' and sorted(item['candidate_id'] for item in response['treatments']) != expected:
        raise ValueError('Expected one Graphics treatment for ' + ' and one for '.join(expected))
    return response


TERMINAL_MEDIA_FAILURES = frozenset({'failed', 'expired', 'canceled', 'cancelled', 'moderated'})


def build_publication(
    pack,
    copy,
    candidate_assets,
    source_assets,
    *,
    selected='A',
    fallback_stage=None,
    failure_state=None,
    previous_selection=None,
):
    """Assemble exact C1 copy; B needs both a definite failure and a saved still.

    This function makes no persistence or provider calls. Callers retain the actual
    failure and predecessor/new revision evidence when persisting a B edition.
    """
    validate_stage_output(pack, 'C1', copy)
    valid_failure = (
        fallback_stage in {'I-A', 'V1'} and failure_state in TERMINAL_MEDIA_FAILURES
    )
    if previous_selection is not None and not (
        previous_selection == 'A' and selected == 'B' and valid_failure
    ):
        raise RuntimeError(
            'Edition already saved; only a recorded definite media failure permits reserve fallback'
        )
    if selected not in {'A', 'B'}:
        raise ValueError('Unknown candidate')
    if selected == 'B' and not valid_failure:
        raise RuntimeError('B requires a definite A media failure')
    by_candidate = {asset['candidate_id']: asset for asset in candidate_assets}
    if len(by_candidate) != len(candidate_assets):
        raise ValueError('Duplicate candidate asset')
    if selected == 'B' and selected not in by_candidate:
        raise RuntimeError('No reserve still; retain the existing A edition')
    candidate = next(item for item in copy['candidates'] if item['id'] == selected)
    asset = by_candidate.get(selected)
    sources = {item['asset_ref']: item for item in source_assets}
    credits = []
    if asset:
        inputs = [sources[ref] for ref in asset['input_asset_refs']]
        gaps = [gap for item in inputs for gap in item.get('credit_gaps', [])]
        credits = [{
            'asset_ref': asset['asset_ref'],
            'credit_text': '; '.join(dict.fromkeys(item.get('credit', 'Creator unknown') for item in inputs)),
            'credit_url': next((item.get('page_url') or item.get('source_url') for item in inputs), None),
            'status': 'incomplete' if gaps else 'complete',
            'gaps': gaps,
        }]
    publication = {
        'locale': copy['locale'],
        'headline': candidate['headline'],
        'byline': candidate['byline'],
        'article': copy['article'],
        'used_fact_ids': list(dict.fromkeys(copy['used_fact_ids'] + candidate['used_fact_ids'])),
        'used_asset_refs': [asset['asset_ref']] if asset else [],
        'asset_credits': credits,
        'visual_brief': (
            'C1 preferred headline A; image execution does not change selection.'
            if selected == 'A'
            else f'Reserve B used after definite technical failure at {fallback_stage}.'
        ),
        'evidence_gaps': copy['evidence_gaps'],
    }
    validate(publication, pack['publication_schema'])
    return publication


def validate_copy_fact_ids(copy, fact_items):
    """Ensure the exact C1 article and both options cite supplied fact IDs only."""
    facts = {item['fact_id'] for item in fact_items}
    if not set(copy['used_fact_ids']) <= facts or any(
        not set(candidate['used_fact_ids']) <= facts for candidate in copy['candidates']
    ):
        raise ValueError('Unknown fact reference')


def normalize_treatments(pack, result):
    """Repair only transport geometry; preserve the raw model output and exact copy."""
    result = copy.deepcopy(result)
    supported = pack["media_capabilities"]["image_aspect_ratios"]
    adjustments = []
    for treatment in result.get("treatments", []):
        requested = treatment.get("aspect_ratio")
        if requested in supported:
            continue
        match = re.fullmatch(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", str(requested))
        if match and all(0 < float(value) < 1e100 for value in match.groups()):
            ratio = float(match[1]) / float(match[2])

            def distance(candidate, target=ratio):
                w, h = map(float, candidate.split(":"))
                return abs(math.log((w / h) / target))

            resolved = min(
                (value for value in supported if value != "auto"), key=distance
            )
        else:
            resolved = "auto"
        treatment["aspect_ratio"] = resolved
        for field in ["still_prompt", "motion_prompt"]:
            if isinstance(requested, str) and requested:
                treatment[field] = re.sub(
                    r"(?i)(\b(?:locked|fixed)\s+)"
                    + re.escape(requested)
                    + r"(\s+frame\b)",
                    lambda match, value=resolved: match[1] + value + match[2],
                    treatment.get(field, ""),
                )
        adjustments.append(
            {
                "candidate_id": treatment.get("candidate_id"),
                "requested": requested,
                "submitted": resolved,
                "reason": "unsupported provider geometry; no regeneration",
            }
        )
    return result, adjustments
