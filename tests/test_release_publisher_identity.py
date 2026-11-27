"""Brand writes require publisher identity evidence for the particular offering."""

import pytest

from core import models, publisher_accounts

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def account(identifier, handle, name):
    return models.Account.objects.create(author_id=identifier, handle=handle, display_name=name)


def release(author, text, name, relation, handle=None):
    post = models.Post.objects.create(tweet_id='2126159872026960215', author=author, text=text)
    issuer = {'source_excerpt': text, 'relation': relation, 'observed_name': name}
    if handle:
        issuer['observed_handle'] = handle
    finding = {'issuer_evidence': issuer, 'observed_name': 'Test-Model', 'brand_id': None}
    return post, finding


def profile(author):
    return {'provider': 'x', 'external_identifier': author.author_id, 'handle': author.handle,
            'display_name': author.display_name, 'sources': [
                {'id': 'account:bio', 'text': 'Empowering every robot with a super-brain.'}
            ]}


def test_supported_first_party_registers_one_official_brand():
    author = account('9990001', 'ace_robotics', 'ACE ROBOTICS')
    post, finding = release(author, 'Introducing ACE-ViDiHand2', 'ACE ROBOTICS', 'source_author')
    finding['publisher_profile'] = profile(author)
    resolve = publisher_accounts.resolve_release_publisher
    brand_id = resolve(post=post, finding=finding)
    assert resolve(post=post, finding=finding) == brand_id
    assert models.BrandAccount.objects.get(account=author, role_id='official').brand_id == brand_id
    assert not models.Company.objects.exists()


def test_extracting_a_handle_does_not_register_reporter_or_unverified_publisher():
    reporter = account('9990002', 'SouthBrief', 'SouthBrief')
    amini = account('9990003', 'AminiTech', 'Amini')
    post, finding = release(reporter, 'Amini (@AminiTech) released Soma-1X Lite', 'Amini',
                            'attributed_party', 'AminiTech')
    resolve = publisher_accounts.resolve_release_publisher
    assert resolve(post=post, finding=finding) is None
    assert not models.BrandAccount.objects.exists()
    brand_id = resolve(post=post, finding=finding, verified_account=amini)
    assert resolve(post=post, finding=finding) == brand_id
    assert models.BrandAccount.objects.get(role_id='official').account_id == amini.pk
    assert not models.Company.objects.exists()


def test_localized_name_reuses_brand_and_conflicting_owners_remain_pending():
    author = account('9990004', 'hunyuan_official', '腾讯混元')
    known = models.Brand.objects.create(nickname='hunyuan', display_name='Hunyuan', display_name_zh_cn='腾讯混元')
    post, finding = release(author, 'We released a new model', '腾讯混元', 'source_author')
    finding['publisher_profile'] = profile(author)
    resolve = publisher_accounts.resolve_release_publisher
    assert resolve(post=post, finding=finding) == known.pk
    role, _ = models.Role.objects.get_or_create(pk='official')
    models.BrandAccount.objects.get_or_create(account=author, brand=known, defaults={'role': role})
    other = models.Brand.objects.create(nickname='other', display_name='Other')
    models.BrandAccount.objects.create(account=author, brand=other, role_id='official')
    assert resolve(post=post, finding=finding) is None
    assert models.Brand.objects.count() == 2


def test_profile_without_ownership_or_suspect_brand_id_stays_pending():
    author = account('9990005', 'reader', 'Reader')
    post, finding = release(author, 'I signed up for Muse', 'Muse', 'source_author')
    suspect = models.Brand.objects.create(nickname='muse', display_name='Muse')
    finding.update(brand_id=suspect.pk, publisher_profile=profile(author))
    assert publisher_accounts.resolve_release_publisher(post=post, finding=finding) is None
    assert not models.BrandAccount.objects.exists()


def test_publisher_registration_and_release_share_account_lock():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from types import SimpleNamespace

    from django.db import connections

    from core.official_company_accounts import register_account

    author = account('9990007', 'ace_robotics', 'ACE ROBOTICS')
    post, finding = release(author, 'Introducing ACE-ViDiHand2', 'ACE ROBOTICS', 'source_author')
    finding['publisher_profile'] = profile(author)
    state = models.OfficialCompanyAccountState.objects.create(
        account=author, status='accepted', evidence_hash='a'*64,
        decision={'organization_name': 'ACE ROBOTICS'},
    )
    start = Barrier(2)

    def run(fn):
        try:
            start.wait(timeout=8)
            return fn()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        registration = executor.submit(run, lambda: register_account(
            state.pk, cfg=SimpleNamespace(registration_enabled=True), preserve_list_intents=True,
            propagate_conflicts=True,
        ))
        product = executor.submit(run, lambda: publisher_accounts.resolve_release_publisher(post=post, finding=finding))
        assert registration.result(timeout=15) == state.pk
        owner = product.result(timeout=15)
    assert models.Brand.objects.filter(display_name='ACE ROBOTICS').count() == 1
    assert models.BrandAccount.objects.get(account=author, role_id='official').brand_id == owner


def test_namesake_profile_does_not_qualify_a_new_brand():
    author = account('9990006', 'personal_reader', 'ACE ROBOTICS')
    post, finding = release(author, 'Introducing ACE-ViDiHand2', 'ACE ROBOTICS', 'source_author')
    finding['publisher_profile'] = profile(author)
    assert publisher_accounts.resolve_release_publisher(post=post, finding=finding) is None
    assert not models.Brand.objects.exists()
    assert not models.BrandAccount.objects.exists()


def test_reporter_mention_cannot_credit_a_reassigned_handle_and_uses_exact_indexes():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from core.release_publisher_recovery import _saved_originals

    reporter = account("1868991360755539968", "SouthBrief", "SouthBrief")
    current = account("111122223333", "AminiTech", "Different account")
    post, finding = release(reporter, "Amini (@AminiTech) released Soma-1X Lite this week.",
                            "Amini", "attributed_party", "aminitech")
    post.entities = {"user_mentions":[{"name":"Amini","id_str":"1615357145842581505",
                                     "indices":[7,17],"screen_name":"AminiTech"}]}
    from django.utils import timezone
    post.created_at = timezone.now()
    with CaptureQueriesContext(connection) as captured:
        assert publisher_accounts.resolve_release_publisher(post=post, finding=finding, verified_account=current) is None
        assert list(_saved_originals("aminitech", "Soma-1X Lite", post)) == []
    assert not models.BrandAccount.objects.exists()
    queries = [r["sql"] for r in captured.captured_queries]
    assert any('"normalized_handle"' in q and 'WHERE' in q for q in queries)
    assert not any('UPPER("accounts"."handle"' in q or 'UPPER("posts"."author_handle"' in q for q in queries)
