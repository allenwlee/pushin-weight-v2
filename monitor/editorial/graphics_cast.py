"""Resolve and pin the actual cast bytes for a writer-led Chatter edition."""

import hashlib
import re
from collections import defaultdict

from botocore.exceptions import BotoCoreError, ClientError
from django.core.files.storage import storages
from django.db.models import Value
from django.db.models.functions import Lower, StrIndex, Trim

from core.models import PersonAccount, PersonMedia, PersonName
from core.staff_assets.graphics_references import read_graphics_references

from .graphics_generation import MAX_INPUT_BYTES, MIME_TYPES


def cast_manifest(saved, selection):
    """Match the subject against saved source passages and existing person identities."""
    facts = saved['handoff']['fact_items']
    headlines = [saved['handoff']['subject'], *selection.get('original_headlines', [])]
    subject = ' '.join(headlines)
    linked = defaultdict(set)
    posts = {f.get('source_post_id') for f in facts if f.get('source_post_id')}
    for source in selection.get('source_identities', []):
        if source.get('post_id') in posts:
            for link in source.get('person_links', []):
                if link.get('resolution_status') == 'confirmed':
                    linked[link['person_id']].add(source['post_id'])

    matches = defaultdict(dict)
    handles = {handle.casefold() for handle in re.findall(r'(?<![\w@])@([A-Za-z0-9_]{1,15})(?!\w)', subject)}
    if handles:
        accounts = PersonAccount.objects.filter(account__data_source_id='x', account__normalized_handle__in=handles,
            person__merged_into__isnull=True, resolution_status='confirmed')
        for pid, handle, name in accounts.values_list('person_id', 'account__normalized_handle', 'person__primary_name__full_name'):
            person = str(pid)
            evidence = [fact['fact_id'] for fact in facts if fact.get('source_post_id') in linked[person]]
            if evidence:
                matches['@' + handle][person] = (name or '@' + handle, evidence)
    # Let PostgreSQL reduce aliases to literal substrings of this episode.
    # Check word boundaries and ambiguity below, retaining names without photos
    # so the saved gap distinguishes a named subject from an unknown identity.
    names = (PersonName.objects.filter(person__merged_into__isnull=True)
             .exclude(review_status='rejected')
             .alias(name_position=StrIndex(Lower(Value(subject)), Lower(Trim('full_name'))))
             .filter(name_position__gt=0))
    for person_id, name in names.values_list('person_id', 'full_name'):
        name = name.strip()
        if not name or len(name) < 2:
            continue
        pattern = rf'(?<!\w){re.escape(name)}(?!\w)'
        if not re.search(pattern, subject, re.IGNORECASE):
            continue
        person = str(person_id)
        # Short Latin display aliases need the explicit account-to-person link.
        if name.isascii() and len(name.split()) == 1 and not linked[person]:
            continue
        evidence = [f['fact_id'] for f in facts if f.get('source_post_id') in linked[person]
                    or re.search(pattern, f['supporting_passage'], re.IGNORECASE)]
        if evidence:
            matches[name.casefold()][person] = (name, evidence)
    assets, gaps, picked = [], [], set()
    for identities in sorted(matches.values(), key=lambda group: -len(next(iter(group.values()))[0])):
        if len(identities) != 1:
            source_linked = {person: match for person, match in identities.items() if linked[person]}
            if len(source_linked) != 1:
                gaps.append('ambiguous_subject_name')
                continue
            identities = source_linked
        person, (name, evidence) = next(iter(identities.items()))
        if person in picked or len(assets) >= 3:
            continue
        picked.add(person)
        references = read_graphics_references(person, permitted_reuse={'unknown', 'restricted', 'permitted'})
        for ref in references.references:
            cast_identity = ref.evidence.get('identity_resolution') or {}
            verified_cast = (cast_identity.get('state') == 'verified' and cast_identity.get('person_id') == person
                             and ref.evidence.get('source_role') in {'identity-still', 'prepared-identity-crop',
                                                                     'identity', 'existing-reference', 'source-frame'})
            if ref.media_type not in MIME_TYPES or not (ref.individual_portrait or ref.owner_confirmed or verified_cast):
                continue
            row = PersonMedia.objects.select_related('media').get(pk=ref.person_media_id, person_id=person, media_id=ref.sha256)
            if any(asset['sha256'] == ref.sha256 for asset in assets):
                break
            assets.append({'asset_ref': f'person:{row.pk}', 'role': 'identity_reference',
                'person_id': person, 'person_name': name, 'fact_ids': evidence, 'credit': ref.credit,
                'source_url': ref.source_url, 'reuse_status': ref.reuse_status,
                'storage_alias': 'staff_media', 'storage_name': row.media.storage_name,
                'sha256': ref.sha256, 'mime': ref.media_type})
            break
        else:
            gaps.append(f'{name}: no usable identity portrait')
    if not picked and not gaps:
        gaps.append('no source-backed cast identity')
    return {'assets': assets, 'gaps': gaps}


def load_cast(manifest):
    assets = []
    for ref in manifest['assets']:
        media_id = ref['asset_ref'].removeprefix('person:')
        if not PersonMedia.objects.filter(pk=media_id, person_id=ref['person_id'],
                media_id=ref['sha256'], media__storage_name=ref['storage_name']).exists():
            raise ValueError('cast identity changed')
        try:
            with storages['staff_media'].open(ref['storage_name'], 'rb') as stream:
                data = stream.read(MAX_INPUT_BYTES + 1)
        except (OSError, BotoCoreError, ClientError) as exc:
            raise ValueError('cast asset unavailable') from exc
        if not data or len(data) > MAX_INPUT_BYTES or hashlib.sha256(data).hexdigest() != ref['sha256']:
            raise ValueError('cast asset hash mismatch')
        assets.append({**ref, 'data': data})
    return assets


def recipe_refs(assets):
    return [{key: asset[key] for key in ('storage_alias', 'storage_name', 'sha256', 'mime')} for asset in assets]
