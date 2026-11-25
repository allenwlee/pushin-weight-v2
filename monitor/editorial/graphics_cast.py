"""Resolve and pin the actual cast bytes for a writer-led Chatter edition."""

import hashlib
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache, partial

from botocore.exceptions import BotoCoreError, ClientError
from django.core.files.storage import storages
from django.db.models import Value
from django.db.models.functions import Collate, Lower, StrIndex, Trim
from django.utils import timezone

from core.models import PersonAccount, PersonMedia, PersonName
from core.staff_assets.graphics_references import (
    read_graphics_references,
    read_staff_object_before,
)
from core.staff_assets.person_roles import named_employers, sourced_role

from .chatter_cast_history import (
    confirmed_appearances,
    current_primary_fact,
    matching_appearances,
    verified_subject_mentions,
)
from .graphics_generation import MAX_INPUT_BYTES, MIME_TYPES


def _subject_candidates(saved, selection):
    """Match the subject against saved source passages and existing person identities."""
    facts = saved['handoff']['fact_items']
    headlines = [saved['handoff']['subject'], *selection.get('original_headlines', [])]
    subject = ' '.join(headlines)
    linked = defaultdict(set)
    posts = {f.get('source_post_id') for f in facts if f.get('source_post_id')}
    for source in selection.get('source_identities', []):
        if source.get('post_id') in posts:
            for link in source.get('person_links', []):
                if link.get('resolution_status') == 'confirmed' and link.get('role') == 'mentioned':
                    linked[link['person_id']].add(source['post_id'])

    matches = defaultdict(dict)
    handles = {handle.casefold() for handle in re.findall(r'(?<![\w@])@([A-Za-z0-9_]{1,15})(?!\w)', subject)}
    if handles:
        accounts = PersonAccount.objects.filter(account__data_source_id='x', account__normalized_handle__in=handles,
            person__merged_into__isnull=True, resolution_status='confirmed')
        for pid, handle, name in accounts.values_list('person_id', 'account__normalized_handle', 'person__primary_name__full_name'):
            person = str(pid)
            if linked.get(person):
                matches['@' + handle][person] = name or '@' + handle
    # Let PostgreSQL reduce aliases to literal substrings of this episode.
    # Check word boundaries and ambiguity below, retaining names without photos
    # so the saved gap distinguishes a named subject from an unknown identity.
    names = (PersonName.objects.filter(person__merged_into__isnull=True)
             .exclude(review_status='rejected')
             .alias(name_position=StrIndex(Collate(Lower(Value(subject)), "C"), Lower(Trim('full_name'))))
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
        if any(f.get('source_post_id') in linked[person] or re.search(
                pattern, f['supporting_passage'], re.IGNORECASE) for f in facts):
            matches[name.casefold()][person] = name
    # The ranker can supply a cold-start subject within its existing call.
    # Validate each name against both the headline and the selected primary sources.
    hints = {}
    names = selection.get("people") or []
    if "people" not in selection:
        # Older rankings did not name their subjects. Recover a headline name
        # only when a primary passage explicitly attributes an employer and role.
        likely_names = dict.fromkeys(name for headline in headlines for name in
            re.findall(r"(?<!\w)[A-Z][a-zA-Z’'-]+(?:[ \t]+[A-Z][a-zA-Z’'-]+){1,2}(?!\w)", headline))
        names = [name for name in likely_names if any(
            sourced_role(name, org, fact['supporting_passage'])
            for fact in facts if name in fact['supporting_passage']
            for org in named_employers(name, fact['supporting_passage']))]
    for name in names[:3]:
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            continue
        pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
        if re.search(pattern, subject, re.IGNORECASE) and any(
            re.search(pattern, f["supporting_passage"], re.IGNORECASE) for f in facts
        ):
            matches.setdefault(name.casefold(), {})
            hints[name.casefold()] = name
    seen = set()
    for label, identities in sorted(matches.items(), key=lambda item: -len(item[0])):
        # A generic mention in a post can refer to a same-named bystander.
        # A literal subject handle or a subject selected by ID can bind a person;
        # name-only subjects go through the attributed passage and account resolver.
        selected_ids = set(saved.get("person_ids", []))
        confirmed = {pid for pid in identities if pid in selected_ids or
                     label.startswith("@") and linked.get(pid)}
        pid = next(iter(confirmed)) if len(confirmed) == 1 else None
        name = identities.get(pid) or next(iter(identities.values()), None) or hints[label]
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
        supporting = [f for f in facts if re.search(pattern, f["supporting_passage"], re.IGNORECASE)]
        if not supporting and pid:
            supporting = [f for f in facts if f.get("source_post_id") in linked[pid]]
        if not supporting:
            continue
        yield name, pid, supporting, set(identities)


def story_subjects(saved, selection):
    for name, pid, supporting, _ in _subject_candidates(saved, selection):
        yield name, pid, supporting


def _competing_source_identity(name, pid, facts, supporting, saved, observed_by):
    """Look for a second identity explicitly attributed in the same edition."""
    from core.staff_assets.person_intake import create_or_update_person

    for fact in facts:
        if not current_primary_fact(fact, observed_by):
            continue
        evidence = fact_evidence(name, fact, None, saved)
        named_account = evidence.get("personal_account")
        if not named_account and (fact in supporting or not named_employers(name, evidence["passage"])):
            continue
        check = create_or_update_person(name, evidence, apply=False, collect=False, require_source_match=True)
        if check["person_id"] and check["person_id"] != pid:
            return True
        if named_account and "person_account_conflict" in check["gaps"]:
            return True
    return False


def _cast_subjects(saved, selection, observed_by):
    subjects = list(_subject_candidates(saved, selection))
    candidates = {person for _, pid, _, namesakes in subjects if not pid for person in namesakes}
    appearances = confirmed_appearances(candidates, saved.get("facts_as_of"))
    all_facts = saved["handoff"]["fact_items"]
    mentions, conflicts = verified_subject_mentions(candidates, all_facts, observed_by)
    named_by_selector = {n.casefold() for n in selection.get("people") or [] if isinstance(n, str)}
    for name, pid, facts, namesakes in subjects:
        if pid:
            yield name, pid, facts, None
            continue
        history = matching_appearances(name, namesakes, facts, appearances, observed_by)
        # The entity belongs to this story only when the pitch names this person
        # and a primary passage independently names them, including older rankings.
        principal = re.search(rf"(?<!\w){re.escape(name)}(?!\w)", saved["handoff"]["subject"], re.IGNORECASE)
        if named_by_selector and name.casefold() not in named_by_selector:
            principal = False
        named_facts = [f for f in facts if current_primary_fact(f, observed_by)] if principal else []
        cited = namesakes & mentions.keys() if named_facts else set()
        bound = history.keys() | cited
        contested = named_facts and namesakes & conflicts
        if not bound and not contested:
            yield name, pid, facts, None
            continue
        if len(bound) == 1 and not contested:
            pid = next(iter(bound))
            supporting, media_ids = history.get(pid, ([], None))
            if not _competing_source_identity(name, pid, facts, supporting, saved, observed_by):
                if pid in cited:
                    fact_ids = mentions[pid] | {f["fact_id"] for f in named_facts + supporting}
                    supporting = [f for f in all_facts if f["fact_id"] in fact_ids]
                yield name, pid, supporting, media_ids
                continue
        yield name, None, [], None


PORTRAIT_WAIT_SECONDS = 20


class ForegroundPortraits:
    """Verified bytes live only for this worker delivery. Retries inherit its original deadline."""

    def __init__(self, started):
        self.expires_at = started + timedelta(seconds=PORTRAIT_WAIT_SECONDS)
        self.deadline = time.monotonic() + (self.expires_at - timezone.now()).total_seconds()
        self.verified = {}

    def remaining(self):
        return max(0, self.deadline - time.monotonic())

    def read(self, name):
        if name in self.verified:
            return self.verified[name]
        return read_staff_object_before(name, self.deadline)


def portrait_asset(person, name, fact_ids, *, media_ids=None, foreground=None):
    person = str(person)
    references = read_graphics_references(person, permitted_reuse={'unknown', 'restricted', 'permitted'},
                                          max_images=1, media_ids=media_ids, portrait_mimes=MIME_TYPES,
                                          read_bytes=foreground.read if foreground else None)
    for ref in references.references:
        row = PersonMedia.objects.select_related('media').filter(
            pk=ref.person_media_id, person_id=person, media_id=ref.sha256).first()
        if not row:
            continue
        if foreground is not None:
            foreground.verified[row.media.storage_name] = ref.data
        return {'asset_ref': f'person:{row.pk}', 'role': 'identity_reference', 'person_id': person,
                'person_name': name, 'fact_ids': fact_ids, 'credit': ref.credit, 'source_url': ref.source_url,
                'reuse_status': ref.reuse_status, 'storage_alias': 'staff_media',
                'storage_name': row.media.storage_name, 'sha256': ref.sha256, 'mime': ref.media_type}
    return None


def cast_manifest(saved, selection):
    """Resolve existing cast without research. Retained for former callers."""
    from core.staff_assets.person_intake import create_or_update_person

    assets, gaps = [], []
    for name, pid, facts, media_ids in _cast_subjects(saved, selection, timezone.now()):
        if not facts:
            gaps.append(f"{name}: ambiguous_subject_name")
            continue
        evidence = fact_evidence(name, facts[0], pid, saved)
        identity = create_or_update_person(name, evidence, needs={'portrait'}, apply=False, collect=False,
                                           require_source_match=True)
        person = identity.get('person_id')
        ref = portrait_asset(person, name, [f['fact_id'] for f in facts], media_ids=media_ids) if person else None
        if ref and ref['sha256'] not in {a['sha256'] for a in assets}:
            assets.append(ref)
        else:
            gaps.extend(identity.get('gaps') or [f'{name}: no usable identity portrait'])
        if len(assets) == 3:
            break
    return {'assets': assets, 'gaps': gaps or ([] if assets else ['no source-backed cast identity'])}


def fact_evidence(name, fact, person_id, saved):
    passage = fact['supporting_passage']
    urls = list(dict.fromkeys([*fact.get('source_refs', []), *re.findall(r'https?://[^\s<>"\]]+', passage)]))
    evidence = {'passage': passage, 'source_id': str(fact.get('source_id') or fact['fact_id']),
                'source_url': next(iter(urls), ''), 'source_urls': urls,
                'observed_at': fact.get('observed_at') or saved['facts_as_of']}
    if person_id:
        evidence['person_id'] = person_id
    personal = re.search(rf'(?<!\w){re.escape(name)}\s*\(\s*@([A-Za-z0-9_]{{1,15}})\s*\)', passage, re.IGNORECASE)
    if personal:
        evidence['personal_account'] = {'handle': personal[1]}
    return evidence



def load_cast(manifest, *, foreground=None):
    assets = []
    for ref in manifest['assets']:
        media_id = ref['asset_ref'].removeprefix('person:')
        if not PersonMedia.objects.filter(pk=media_id, person_id=ref['person_id'],
                media_id=ref['sha256'], media__storage_name=ref['storage_name']).exists():
            raise ValueError('cast identity changed')
        try:
            if foreground is not None:
                data = foreground.read(ref['storage_name'])
            else:
                with storages['staff_media'].open(ref['storage_name'], 'rb') as stream:
                    data = stream.read(MAX_INPUT_BYTES + 1)
        except (OSError, BotoCoreError, ClientError) as exc:
            raise ValueError('cast asset unavailable') from exc
        if not data or len(data) > MAX_INPUT_BYTES or hashlib.sha256(data).hexdigest() != ref['sha256']:
            raise ValueError('cast asset hash mismatch')
        if foreground is not None:
            foreground.verified[ref['storage_name']] = data
        assets.append({**ref, 'data': data})
    return assets


def recipe_refs(assets):
    return [{key: asset[key] for key in ('storage_alias', 'storage_name', 'sha256', 'mime')} for asset in assets]


def prepare_person_cast(saved, selection, started, *, foreground=None):
    """Reconcile every sourced observation before choosing or requesting a portrait."""
    from core.staff_assets.person_intake import (
        create_or_update_person,
        personal_accounts_named,
    )
    from core.staff_assets.person_research import collect_missing

    foreground = foreground or ForegroundPortraits(started)
    subjects, gaps = [], []
    # The same name may appear in dozens of posts. Check the account directory
    # once per subject, while validating role and affiliation on every passage.
    accounts_for_story = lru_cache(maxsize=3)(personal_accounts_named)
    for name, known_id, facts, media_ids in _cast_subjects(saved, selection, started):
        if not facts:
            gaps.append(f"{name}: ambiguous_subject_name")
            continue
        matches = {}
        links = defaultdict(list)
        unresolved = set()
        for fact in facts:
            evidence = fact_evidence(name, fact, known_id, saved)
            identity = create_or_update_person(name, evidence, needs={'portrait'}, collect=False,
                                               account_lookup=accounts_for_story, require_source_match=True)
            if identity.get('person_id'):
                key = str(identity['person_id'])
                links[key].extend(evidence['source_urls'])
                # Choose the most informative sourced observation for query construction.
                strength = (bool(identity.get('china')), bool(identity.get('affiliation')),
                            bool(evidence.get('personal_account')), bool(evidence.get('source_url')))
                if key not in matches or strength > matches[key][0]:
                    matches[key] = (strength, identity, evidence)
            else:
                unresolved.update(identity.get('gaps', []))
        if len(matches) != 1:
            gaps.extend(f'{name}: {gap}' for gap in sorted(unresolved or {'ambiguous_subject_name'}))
            continue
        pid, (_, identity, evidence) = next(iter(matches.items()))
        if any(entry['person_id'] == pid for entry in subjects):
            continue
        evidence = {**evidence, 'source_urls': list(dict.fromkeys([*evidence['source_urls'], *links[pid]]))}
        resolved = collect_missing(identity, name, evidence, {'portrait'},
                                   portrait_reader=partial(portrait_asset, foreground=foreground, media_ids=media_ids))
        ids = [f['fact_id'] for f in facts]
        asset = resolved['asset']
        if asset:
            asset = {**asset, 'fact_ids': ids}
        subjects.append({'person_id': pid, 'name': name, 'fact_ids': ids, 'asset': asset,
                         'work_id': resolved['work_id']})
        if len(subjects) == 3:
            break
    return {'started_at': started.isoformat(), 'subjects': subjects, 'gaps': gaps}


def read_person_cast(state, now, *, foreground=None):
    """A worker continuation can join early results without tying up a worker slot."""
    from core.models import StaffCollectionWork
    from core.staff_assets.person_research import OPEN, POLICY

    foreground = foreground or ForegroundPortraits(datetime.fromisoformat(state['started_at']))
    deadline = foreground.expires_at
    works = StaffCollectionWork.objects.filter(policy_version=POLICY, pk__in=[
        entry['work_id'] for entry in state['subjects'] if entry['work_id']]).in_bulk()
    assets, gaps, waiting = [], list(state['gaps']), False
    for entry in state['subjects']:
        asset = entry['asset']
        work = works.get(entry['work_id'])
        if not asset and work:
            if work.state in OPEN:
                waiting |= now < deadline
            elif work.updated_at <= deadline and work.result.get('asset_ids'):
                asset = portrait_asset(entry['person_id'], entry['name'], entry['fact_ids'],
                                       media_ids=work.result['asset_ids'], foreground=foreground)
            if not asset and work.state not in OPEN:
                gaps.extend(f"{entry['name']}: {gap}" for gap in work.result.get('gaps', []))
        if asset and asset['sha256'] not in {ref['sha256'] for ref in assets}:
            try:
                load_cast({'assets': [asset]}, foreground=foreground)
            except (ValueError, OSError):
                asset = None
            else:
                assets.append(asset)
        if not asset:
            if foreground.remaining() <= 0:
                gaps.append(f"{entry['name']}: portrait retrieval deadline elapsed")
            gaps.append(f"{entry['name']}: no usable identity portrait")
    if waiting and foreground.remaining() > 0:
        return None
    return {'assets': assets, 'gaps': list(dict.fromkeys(gaps)) or ([] if assets else ['no source-backed cast identity'])}
