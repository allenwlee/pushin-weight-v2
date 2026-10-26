"""Bounded transfer of admitted staging Posts; no search or inference calls.

Collection and attribution have already used CycleRunner. Transfer those typed
records, remap account identities, and leave existing live records untouched.
The package is temporary transport, not a permanent raw-response archive.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone

from core.collection_jobs import register_job, set_job_state
from core.collection_state import checkpoint_scope, claim_job, finish_run
from core.measurement_taxonomy import require
from core.models import (
    Account,
    AccountProfileSnapshot,
    Brand,
    CollectionJob,
    CollectionObservation,
    DataSource,
    Post,
    PostBrand,
    PostBrandMention,
    PostEnrichmentState,
    XAccountDetail,
)
from core.provider_batches import record_post_membership, save_post_membership
from monitor.backfill_staging import validate_staging
from monitor.run_lock import backfill_yield_requested, harvest_writer_lock

FORMAT = "x-staging-posts/v1"
MODELS = (Account, XAccountDetail, Post, PostBrand, PostBrandMention, AccountProfileSnapshot)
MAX_BYTES = 8 * 1024 * 1024
POST_ENRICHMENT = {"headline", "headline_source", "text_en", "text_zh_cn", "commentary_en",
                   "commentary_zh_cn", "lang_detected", "last_quote_count_seen", "last_quote_fetched_at",
                   "metrics_refreshed_at"}


def encoded(value):
    return json.dumps(value, sort_keys=True, cls=DjangoJSONEncoder, separators=(",", ":")).encode()


def signature(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def fields(model):
    return [f for f in model._meta.concrete_fields if model is not Post or f.name not in POST_ENRICHMENT]


def schema_signature():
    return signature({m.__name__: [(f.attname, f.column, f.get_internal_type(),
        f.related_model._meta.label if f.is_relation else None) for f in fields(m)] for m in MODELS})


def database_identity():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(),session_user")
        name, user = cursor.fetchone()
    return {"name": name, "user": user, "host": connection.settings_dict["HOST"]}


def rows(query):
    return json.loads(encoded(list(query.values(*[f.attname for f in fields(query.model)]))))


def _completed_source(job_id):
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cursor.execute("SET LOCAL statement_timeout='20s'")
    job = CollectionJob.objects.select_related("last_success").get(pk=job_id)
    validate_staging(job.scope)
    require(job.scope.get("response_storage") in {"staging", "database"} and job.state == "completed"
            and job.last_success_id and job.last_success.report.get("collection_drained"),
            "completed direct-staging collection required")
    identity = database_identity()
    from monitor.backfill_database import job_database_matches
    require(job_database_matches(job, identity), "staging identity mismatch")
    return job, {"database": identity, "job_id": str(job.pk), "run_id": str(job.last_success_id),
        "definition_sha256": job.definition_sha256, "since_epoch": job.scope["since_epoch"],
        "until_epoch": job.scope["until_epoch"], "historical_keyword_recall": "incomplete"}


def membership(query):
    """Count and hash ordered distinct Post IDs without retaining a full cohort."""
    count, sha = 0, hashlib.sha256()
    for identifier in query.exclude(post_id=None).order_by("post_id").values_list("post_id", flat=True).distinct().iterator(chunk_size=100):
        count += 1
        sha.update(encoded(identifier) + b"\n")
    return {"count": count, "sha256": sha.hexdigest()}


@transaction.atomic
def inspect_source(job_id, *, after=""):
    job, source = _completed_source(job_id)
    query = CollectionObservation.objects.filter(run__job=job, source_subject_kind="post")
    return {"source": source, "schema": schema_signature(), "members": membership(query),
            "prefix": membership(query.filter(post_id__lte=after))}


@transaction.atomic
def export_posts(job_id, *, after="", limit=100):
    """Keyset-paginated, stable read of one completed staging collection job."""
    require(type(limit) is int and 1 <= limit <= 100, "export limit must be 1–100")
    job, source = _completed_source(job_id)
    ids = list(CollectionObservation.objects.filter(run__job=job, source_subject_kind="post",
        post_id__gt=after).order_by("post_id").values_list("post_id", flat=True).distinct()[:limit])
    if not ids:
        return None
    posts = Post.objects.filter(pk__in=ids).order_by("pk")
    accounts = {p.author_id for p in posts}
    require(None not in accounts, "staging Post author missing")
    # One bounded profile observation per account. Current consumer verification
    # requires a source profile; discovery/review work remains on its own ledger.
    profiles = AccountProfileSnapshot.objects.filter(account_id__in=accounts).order_by(
        "account_id", "-last_observed_at", "-pk").distinct("account_id")
    package = {"format": FORMAT, "schema": schema_signature(), "source": source,
        "after": after, "next_after": ids[-1], "ids": ids, "rows": {
        "Account": rows(Account.objects.filter(pk__in=accounts).order_by("pk")),
        "XAccountDetail": rows(XAccountDetail.objects.filter(account_id__in=accounts).order_by("pk")),
        "Post": rows(posts), "PostBrand": rows(PostBrand.objects.filter(post_id__in=ids).order_by("pk")),
        "PostBrandMention": rows(PostBrandMention.objects.filter(post_id__in=ids).order_by("pk")),
        "AccountProfileSnapshot": rows(profiles),
    }}
    require(len(encoded(package)) <= MAX_BYTES, "export exceeds byte limit; reduce --limit")
    package["sha256"] = signature(package)
    return package


def validate_package(package):
    require(isinstance(package, dict) and set(package) == {
        "format", "schema", "source", "after", "next_after", "ids", "rows", "sha256"}, "invalid export fields")
    require(package["format"] == FORMAT and package["schema"] == schema_signature(), "export schema mismatch")
    require(signature({k: v for k, v in package.items() if k != "sha256"}) == package["sha256"], "export hash mismatch")
    require(len(encoded(package)) <= MAX_BYTES + 100, "export too large")
    ids = package["ids"]
    require(isinstance(ids, list) and 0 < len(ids) <= 100 and all(isinstance(x, str) and x for x in ids)
            and ids == sorted(set(ids)) and package["next_after"] == ids[-1]
            and isinstance(package["after"], str) and all(i > package["after"] for i in ids), "invalid export cohort")
    source = package["source"]
    require(set(source) == {"database", "job_id", "run_id", "definition_sha256", "since_epoch", "until_epoch",
                           "historical_keyword_recall"} and source["historical_keyword_recall"] == "incomplete",
            "invalid source provenance")
    require(set(source["database"]) == {"host", "name", "user"}, "invalid source database")
    require(all(isinstance(v, str) and v for v in source["database"].values()), "invalid source database values")
    for key in ("job_id", "run_id"):
        require(str(uuid.UUID(source[key])) == source[key], "invalid source execution identity")
    require(type(source["since_epoch"]) is int and type(source["until_epoch"]) is int
            and source["since_epoch"] < source["until_epoch"], "invalid source bounds")
    require(set(package["rows"]) == {m.__name__ for m in MODELS}, "invalid export models")
    for model in MODELS:
        records = package["rows"][model.__name__]
        require(isinstance(records, list) and len(records) <= 3000, "oversized export relation")
        require(all(isinstance(r, dict) and set(r) == {f.attname for f in fields(model)} for r in records),
                "export field shape mismatch")
    posts = package["rows"]["Post"]
    require(len(posts) == len(ids) and {p["tweet_id"] for p in posts} == set(ids), "export membership mismatch")
    accounts = package["rows"]["Account"]
    authors = {p["author_id"] for p in posts}
    require(len(accounts) == len(authors) and {a["account_key"] for a in accounts} == authors,
            "export account membership mismatch")
    require(all(a["data_source_id"] == "x" and a["normalized_identifier"] == a["external_identifier"] == a["author_id"]
                for a in accounts), "export X account identity mismatch")
    require(len({a["normalized_identifier"] for a in accounts}) == len(accounts), "duplicate export account")
    for name in ("XAccountDetail", "AccountProfileSnapshot"):
        require(all(r["account_id"] in authors for r in package["rows"][name]), "export profile outside cohort")
    require({r["account_id"] for r in package["rows"]["AccountProfileSnapshot"]} == authors,
            "export profile evidence missing")
    for name in ("PostBrand", "PostBrandMention"):
        require(all(r["post_id"] in ids for r in package["rows"][name]), "export relation outside cohort")
    author_ids = {a["account_key"]: a["normalized_identifier"] for a in accounts}
    for existing in Post.objects.filter(pk__in=ids).select_related("author"):
        incoming = next(p for p in posts if p["tweet_id"] == existing.pk)
        require(existing.author_id and existing.author.data_source_id == "x"
                and existing.author.normalized_identifier == author_ids[incoming["author_id"]],
                "existing Post author identity mismatch")
    for post in posts:
        created = Post._meta.get_field("created_at").to_python(post["created_at"])
        require(post["text"] and created and timezone.is_aware(created)
                and source["since_epoch"] <= created.timestamp() < source["until_epoch"], "invalid source Post")
        require(post["created_at_epoch"] in {None, int(created.timestamp())}, "source Post timestamp mismatch")
        brands = {r["brand_id"] for r in package["rows"]["PostBrand"] if r["post_id"] == post["tweet_id"]}
        mentions = {r["brand_id"] for r in package["rows"]["PostBrandMention"] if r["post_id"] == post["tweet_id"]}
        require(bool(brands) and Brand.objects.filter(pk__in=brands).count() == len(brands), "export brand missing")
        require(brands - set(Brand.objects.filter(pk__in=brands, is_sentinel=True).values_list("pk", flat=True)) <= mentions,
                "export brand mention missing")


def insert_rows(model, records):
    """Copy typed values, preserving source observation timestamps on new rows."""
    require(not backfill_yield_requested(), "promotion yielding to live writer")
    objects = [model(**{f.attname: f.to_python(row[f.attname]) for f in fields(model) if f.attname in row}) for row in records]
    model.objects.bulk_create(objects, batch_size=100)
    timestamps = [f for f in fields(model) if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False)]
    if objects and timestamps:
        for obj, row in zip(objects, records, strict=True):
            for field in timestamps:
                setattr(obj, field.attname, field.to_python(row[field.attname]))
        model.objects.bulk_update(objects, [f.name for f in timestamps], batch_size=100)
    return objects


def _copy(package, run, scope):
    source = package["rows"]
    existing = set(Post.objects.filter(pk__in=package["ids"]).values_list("pk", flat=True))
    new = set(package["ids"]) - existing
    needed_authors = {p["author_id"] for p in source["Post"] if p["tweet_id"] in new}
    account_map, created_accounts = {}, set()
    for row in source["Account"]:
        require(not backfill_yield_requested(), "promotion yielding to live writer")
        if row["account_key"] not in needed_authors:
            continue
        current = Account.objects.filter(data_source_id="x", normalized_identifier=row["normalized_identifier"]).first()
        if current is None:
            values = dict(row)
            values["account_key"] = str(uuid.uuid4())
            # Textual source/country/region keys are portable. Refuse any future
            # unmodeled integer relationship rather than treating its ID as global.
            for field in fields(Account):
                if field.is_relation and values[field.attname] is not None:
                    require(field.related_model.__name__ in {"DataSource", "Country", "Region"}, "account relation needs mapping")
                    require(field.related_model.objects.filter(pk=values[field.attname]).exists(), "account reference missing")
            current = insert_rows(Account, [values])[0]
            created_accounts.add(row["account_key"])
        account_map[row["account_key"]] = str(current.pk)
    insert_rows(XAccountDetail, [{**r, "account_id": account_map[r["account_id"]]} for r in source["XAccountDetail"]
                                if r["account_id"] in created_accounts])
    available = new | set(Post.objects.filter(pk__in=[p["quoted_status_id_id"] for p in source["Post"]
        if p["quoted_status_id_id"]]).values_list("pk", flat=True))
    pending_quotes = {}
    posts = []
    for row in source["Post"]:
        if row["tweet_id"] not in new:
            continue
        values = {**row, "author_id": account_map[row["author_id"]]}
        if values["quoted_status_id_id"] and values["quoted_status_id_id"] not in available:
            pending_quotes[row["tweet_id"]] = {"parent": values["quoted_status_id_id"],
                                               "text_sha256": signature(row["text"])}
            values["quoted_status_id_id"] = None  # Same missing-parent policy as the canonical Post writer.
        posts.append(values)
    insert_rows(Post, posts)
    for model in (PostBrand, PostBrandMention):
        insert_rows(model, [r for r in source[model.__name__] if r["post_id"] in new])
    for row in source["AccountProfileSnapshot"]:
        require(not backfill_yield_requested(), "promotion yielding to live writer")
        if row["account_id"] not in needed_authors:
            continue
        values = {**row, "account_id": account_map[row["account_id"]]}
        values.pop("id")
        if not Post.objects.filter(pk=values["first_source_post_id"]).exists():
            values["first_source_post_id"] = None
        if not AccountProfileSnapshot.objects.filter(account_id=values["account_id"], profile_hash=values["profile_hash"],
                                                     first_observed_at=values["first_observed_at"]).exists():
            insert_rows(AccountProfileSnapshot, [values])
    PostEnrichmentState.objects.bulk_create([PostEnrichmentState(post_id=i, source_collection_job_id=run.job_id) for i in sorted(new)])
    record_post_membership(run, scope, new)
    # Recording an already-live Post must not assign its enrichment queue to the
    # backfiller. The shared helper assigns ownership for new pending members.
    save_post_membership(run, scope, existing)
    require(set(CollectionObservation.objects.filter(run=run).values_list("post_id", flat=True)) == set(package["ids"]),
            "promotion membership reconciliation failed")
    connection.check_constraints()
    require(not backfill_yield_requested(), "promotion yielding to live writer")
    return {"new_post_ids": sorted(new), "existing_posts": len(existing), "pending_quotes": pending_quotes}


def promote_posts(package, *, target, execute=False):
    """Default read-only inspection; apply one atomic cohort under live priority."""
    require(database_identity() == target, "promotion target database mismatch")
    validate_package(package)
    require(tuple(package["source"]["database"][k] for k in ("host", "name"))
            != tuple(target[k] for k in ("host", "name")), "source and target database must differ")
    ids = package["ids"]
    summary = {"posts": len(ids), "existing_posts": Post.objects.filter(pk__in=ids).count(),
               "source_job_id": package["source"]["job_id"], "export_sha256": package["sha256"],
               "twitterapi_requests": 0, "model_requests": 0}
    if not execute:
        return summary
    with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.promote") as lease:
        require(lease.acquired, "promotion waiting for live writer")
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='3s'")
                cursor.execute("SET LOCAL statement_timeout='20s'")
            job_key = "staging-posts/" + package["sha256"]
            previous = CollectionJob.objects.filter(job_key=job_key).first()
            if previous and previous.state == "completed":
                require(set(CollectionObservation.objects.filter(run__job=previous).values_list("post_id", flat=True)) == set(ids),
                        "saved promotion membership mismatch")
                return {**previous.last_success.report["promotion"], "replayed": True}
            definition = {"version": 1, "schedule": {"kind": "manual", "driver": "manual"},
                "budgets": {"requests": 1, "seconds": 120, "bytes": MAX_BYTES, "items": 100},
                "scope": {"adapter": "x-staging-promotion/v1", "database": {k: target[k] for k in ("name", "user")},
                          "source": package["source"], "export_sha256": package["sha256"], "provider_calls_allowed": False}}
            job = register_job(job_key=job_key, source=DataSource.objects.get(pk="x"), purpose="content",
                               operation="x_backfill", mode="historical", definition=definition)
            set_job_state(job.pk, "ready")
            claim = claim_job(job.pk, manual_authorized=True)
            def write(run, scope):
                summary.update(_copy(package, run, scope))
            checkpoint_scope(claim, scope_key="staging-posts", scope_kind="staged_post_copy", ownership=definition["scope"],
                outcome="complete", enumeration_complete=True, raw_count=len(ids), write=write)
            summary.update(job_id=str(job.pk), run_id=str(claim.run_id))
            finish_run(claim, status="success", selected_count=len(ids), success_count=len(ids), request_count=0,
                       report={"promotion": summary, "post_membership": {"version": 1, "distinct_posts": len(ids)}})
    return summary


def reconcile_quotes(package, *, target, execute=False):
    """Repair only this transfer's new Posts, when their quote parents arrive.

    Never replace an existing link or alter a Post whose text changed since
    promotion. The source package and original run keep the unmodified evidence.
    """
    require(database_identity() == target, "promotion target database mismatch")
    validate_package(package)
    job = CollectionJob.objects.select_related("last_success").get(job_key="staging-posts/" + package["sha256"])
    return reconcile_saved_quotes(job.pk, target=target, execute=execute)


def reconcile_saved_quotes(job_id, *, target, execute=False):
    """Use the committed transfer receipt after its temporary package is gone."""
    require(database_identity() == target, "promotion target database mismatch")
    job = CollectionJob.objects.select_related("last_success").get(pk=job_id)
    require(job.scope.get("adapter") == "x-staging-promotion/v1"
            and job.scope.get("database") == {k: target[k] for k in ("name", "user")},
            "saved promotion identity mismatch")
    require(job.state == "completed" and job.last_success_id, "completed promotion required")
    receipt = job.last_success.report["promotion"]
    links = receipt["pending_quotes"]
    require(set(links) <= set(receipt["new_post_ids"]), "quote repair outside promoted Posts")
    summary = {"job_id": str(job.pk), "attached": [], "already_attached": [], "pending": [], "changed": []}

    def inspect_and_apply():
        for identifier, evidence in sorted(links.items()):
            if execute:
                require(not backfill_yield_requested(), "promotion yielding to live writer")
            post = Post.objects.get(pk=identifier)
            parent = evidence["parent"]
            if post.quoted_status_id_id == parent:
                summary["already_attached"].append(identifier)
            elif post.quoted_status_id_id is not None or signature(post.text) != evidence["text_sha256"]:
                summary["changed"].append(identifier)
            elif not Post.objects.filter(pk=parent).exists():
                summary["pending"].append(identifier)
            else:
                if execute:
                    count = Post.objects.filter(pk=identifier, quoted_status_id__isnull=True, text=post.text).update(quoted_status_id_id=parent)
                    require(count == 1, "Post changed during quote reconciliation")
                summary["attached"].append(identifier)
    if execute:
        with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.promote.quotes") as lease:
            require(lease.acquired, "promotion waiting for live writer")
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout='3s'")
                    cursor.execute("SET LOCAL statement_timeout='20s'")
                inspect_and_apply()
                require(not backfill_yield_requested(), "promotion yielding to live writer")
                run = type(job.last_success).objects.select_for_update().get(pk=job.last_success_id)
                run.report = {**run.report, "quote_reconciliation": summary}
                run.save(update_fields=["report", "updated_at"])
    else:
        inspect_and_apply()
    return summary
