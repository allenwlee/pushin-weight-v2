"""All ten inbound references on populated old schema; dedicated local database."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
import django

django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

assert connection.settings_dict["NAME"] == "pw_benchmark_migration_20261006"
assert (
    connection.settings_dict["HOST"] == "127.0.0.1"
    and str(connection.settings_dict["PORT"]) == "55436"
)
e = MigrationExecutor(connection)
e.migrate([("core", "0065_measurement_taxonomy")])
apps = e.loader.project_state([("core", "0065_measurement_taxonomy")]).apps
get = lambda name: apps.get_model("core", name).objects
now = timezone.now()
a = get("Account").create(author_id="rehearsal-native", handle="rehearsal")
b = get("Brand").create(nickname="rehearsal")
co = get("Company").create(nickname="rehearsal")
r = get("Role").create(key="official")
p = get("Post").create(
    tweet_id="rehearsal-post",
    author=a,
    text="isolated migration fixture",
    created_at=now,
)
get("BrandAccount").create(brand=b, account=a, role=r)
get("CompanyAccount").create(company=co, account=a, role=r)
get("TwitterListMembership").create(list_id=42, account=a, source="fixture")
get("AccountPostAppearance").create(account=a, post=p)
get("ProductVerificationProposal").create(
    account=a,
    source_post=p,
    proposed_brand=b,
    proposal_key="fixture",
    observed_name="fixture",
    policy_version="fixture",
)
person = get("Person").create(display_name="fixture")
get("PersonAccount").create(
    person=person, account=a, first_observed_at=now, last_observed_at=now
)
snap = lambda h: get("AccountProfileSnapshot").create(
    account=a,
    profile_hash=h * 64,
    first_observed_at=now,
    last_observed_at=now,
    first_source_kind="fixture",
)
s1, s2 = snap("a"), snap("b")
get("ProfileMovementCandidate").create(
    account=a,
    prior_snapshot=s1,
    new_snapshot=s2,
    source_post=p,
    prior_description="a",
    new_description="b",
    observed_at=now,
    movement_identity="fixture",
)
c = get("BrandDiscoveryCandidate").create(
    observed_name="fixture",
    candidate_identity="fixture",
    first_observed_at=now,
    last_observed_at=now,
)
promotion = get("PostUntrackedBrandPromotion").create(
    post=p,
    contract_version="fixture",
    taxonomy_version="fixture",
    prompt_version="fixture",
    model="fixture",
    provider_role="fixture",
)
get("UntrackedBrandPromotionEvidence").create(
    promotion=promotion,
    brand_discovery_candidate=c,
    source_post=p,
    exact_matched_account=a,
    observed_name="fixture",
    subject_identity="fixture",
    first_seen_at=now,
    last_seen_at=now,
)
links = [
    {"model": model.__name__, "field": field.name}
    for model in apps.get_models()
    for field in model._meta.local_fields
    if field.is_relation and field.related_model == apps.get_model("core", "Account")
]
assert len(links) == 10, "Reaudit new inbound account references before migration"
before = {x["model"]: get(x["model"]).count() for x in links}
e = MigrationExecutor(connection)
e.migrate([("core", "0066_account_source_identity")])
new = e.loader.project_state([("core", "0066_account_source_identity")]).apps
key = new.get_model("core", "Account").objects.get(author_id=a.pk).pk
for x in links:
    model = new.get_model("core", x["model"])
    assert model.objects.count() == before[x["model"]]
    assert (
        model.objects.filter(**{x["field"] + "_id": key}).count() == before[x["model"]]
    )
# Recorded migrations replay as no-ops and cannot mint identities again.
e = MigrationExecutor(connection)
e.migrate([("core", "0066_account_source_identity")])
assert new.get_model("core", "Account").objects.get(author_id=a.pk).pk == key
with connection.cursor() as c:
    c.execute("SELECT version()")
    version = c.fetchone()[0]
    c.execute(
        "SELECT count(*) FROM pg_constraint WHERE contype='f' AND confrelid='accounts'::regclass"
    )
    fks = c.fetchone()[0]
print(
    json.dumps(
        {
            "version": version,
            "counts": before,
            "account_key": str(key),
            "fk_constraints": fks,
            "orphans": 0,
            "replay_preserved_uuid": True,
        }
    )
)
