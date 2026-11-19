"""Apply the bounded role subset of a prepared saved-person-job packet."""

import json
import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from core.person_names import digest
from core.staff_assets.arrivals import without_collection_registration
from core.staff_assets.job_history_apply import (
    apply_profile_action,
    apply_sourced_role,
    source_account_matches_person,
)
from core.staff_assets.job_history_identity import IdentityHold, apply_identity_records
from core.staff_assets.manifest import unique_json_object

RESOURCE = "dpg-dbona93m8hqs73ef70mg-a"
DATABASE = "pushinweight_save_person_job"
HOSTS = {RESOURCE, RESOURCE + ".oregon-postgres.render.com"}
PRODUCTION_RESOURCE = "dpg-d9koekqjobas73fvjqng-a"
PRODUCTION_DATABASE = "pushinweight_shadow"


def verify_import_schema():
    """Check the ORM columns used by this data-only tool, without migrating."""
    from core import models
    from core.geolocation_evidence import PROJECTIONS

    names = (
        "Account", "Post", "Person", "PersonAccount", "PersonName",
        "PersonNameEvidence", "PersonNameSelection", "PersonText",
        "PersonBrandAffiliation", "PersonBrandAffiliationEvidence",
        "AccountProfileSnapshot", "StaffIntake", "Brand", "Company", "BrandCompany",
        "AffiliationType", "Locale",
    )
    expected = {
        model._meta.db_table: {
            field.column for field in model._meta.local_concrete_fields if field.column
        }
        for model in (getattr(models, name) for name in names)
    }
    for table, projection in PROJECTIONS.items():
        if table in expected:
            expected[table].update(
                field.column for field in projection._meta.local_concrete_fields
                if field.column
            )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name,column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=ANY(%s)",
            [list(expected)],
        )
        actual = set(cursor.fetchall())
    missing = sorted(
        f"{table}.{column}"
        for table, columns in expected.items()
        for column in columns
        if (table, column) not in actual
    )
    if missing:
        raise CommandError("Import schema is incompatible: " + ", ".join(missing))


class PersonHold(Exception):
    pass


def post_action_matches(person, evidence, action):
    """Bind every role source to the same person's prepared post observation."""
    fields = action.get("fields") or {}
    people = action.get("person_keys") or [action.get("person_key")]
    observations = action.get("observations") or [fields.get("observed_at")]
    return (
        person.get("key") in people
        and str(fields.get("author_native_id")) == str(person.get("native_id"))
        and str(action.get("key")) == str(evidence.get("native_post_id"))
        and all(
            fields.get(field) == evidence.get(source)
            for field, source in (
                ("native_post_id", "native_post_id"),
                ("source_reference", "source_url"),
                ("text", "evidence_text"),
                ("published_at", "published_at"),
            )
        )
        and evidence.get("observed_at") in observations
        and evidence.get("observed_at") is not None
    )


def profile_action_matches(person, evidence, action):
    fields = action.get("fields") or {}
    return action.get("person_key") == person.get("key") and all(
        fields.get(field) == evidence.get(source)
        for field, source in (
            ("source_reference", "source_url"),
            ("saved_bio", "evidence_text"),
            ("observed_at", "observed_at"),
            ("observed_handle", "observed_handle"),
            ("observation_kind", "observation_kind"),
        )
    )


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix="." + path.name + ".",
            delete=False,
        ) as stream:
            name = stream.name
            json.dump(report, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def verify_target(payload, resource):
    production = resource == PRODUCTION_RESOURCE
    if production and os.environ.get(
        "PUSHINWEIGHT_SAVE_PERSON_JOB_ALLOW_PRODUCTION"
    ) != "1":
        raise CommandError("Production application requires separate explicit authorization")
    if production:
        database = PRODUCTION_DATABASE
        hosts = {resource, resource + ".oregon-postgres.render.com"}
    else:
        database, hosts = DATABASE, HOSTS
    if (
        resource not in {RESOURCE, PRODUCTION_RESOURCE}
        or os.environ.get("PUSHINWEIGHT_SAVE_PERSON_JOB_DB_RESOURCE") != resource
    ):
        raise CommandError("Explicit task database resource confirmation is required")
    target = payload.get("target") or {}
    if target.get("read_only") != "on":
        raise CommandError("Prepared inventory must be explicitly read-only")
    binding = target.get("binding") or {}
    if (
        binding.get("database_name") != database
        or binding.get("database_host") not in hosts
        or (production and binding.get("resource") != resource)
    ):
        raise CommandError("Prepared inventory is not bound to the task database")
    if connection.settings_dict.get("HOST") not in hosts:
        raise CommandError("Configured database host is not the task database")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), current_setting('transaction_read_only')"
        )
        name, readonly = cursor.fetchone()
    if name != database or readonly != "off":
        raise CommandError("Connected database is not the writable task database")
    if production:
        verify_import_schema()
        return
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        raise CommandError("Task database has pending migrations")


def process_person(
    person,
    post_actions,
    profile_actions,
    person_actions,
    review_provenance,
    selected_brands,
):
    roles = person.get("affiliations", [])
    proposed = [
        role
        for role in roles
        if role.get("action") in {"create", "enrich", "add_evidence"}
    ]
    held = len(roles) - len(proposed)
    identity = person.get("identity") or {}
    if not person.get("native_id") or identity.get("person_action") == "hold":
        return {
            "created": 0,
            "updated": 0,
            "reused": 0,
            "held": len(roles),
            "people_held": 1,
            "reason": "Person identity is not yet resolved",
        }
    try:
        with without_collection_registration(), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '1s'")
                cursor.execute("SET LOCAL statement_timeout = '15s'")
            target, account, identity_counts = apply_identity_records(
                person, person_actions, review_provenance
            )
            profile_results = {}
            for action in person_actions:
                if action.get("table") != "account_profile_snapshots":
                    continue
                profile_results[action["key"]] = apply_profile_action(
                    person=target, account=account, person_packet=person, action=action
                )
            if proposed and not source_account_matches_person(target, account):
                return {
                    **identity_counts,
                    "created": 0,
                    "updated": 0,
                    "reused": 0,
                    "held": len(roles),
                    "reason": "Role source account is ambiguous",
                }
            results = []
            role_holds = []
            role_field_holds = []
            evidence_held = 0
            for role in proposed:
                entries = role.get("evidence") or []
                if not entries:
                    held += 1
                    role_holds.append(
                        {
                            "key": role.get("local_id"),
                            "reason": "Role has no bound source",
                        }
                    )
                    continue
                usable_sources = []
                for evidence in entries:
                    ref = evidence.get("source_post_ref")
                    action = post_actions.get(ref)
                    profile = profile_actions.get(
                        evidence.get("source_profile_snapshot_ref")
                    )
                    if (
                        evidence.get("source_kind") == "own_post"
                        and action
                        and action.get("action") == "compare_or_create"
                        and post_action_matches(person, evidence, action)
                    ):
                        source = {
                            "kind": "post",
                            "account_key": str(account.pk),
                            "post_id": evidence.get("native_post_id"),
                            "url": evidence.get("source_url"),
                            "text": evidence.get("evidence_text"),
                            "published_at": evidence.get("published_at"),
                            "observed_at": evidence.get("observed_at"),
                        }
                    elif (
                        evidence.get("source_kind") == "saved_bio"
                        and profile
                        and profile_action_matches(person, evidence, profile)
                        and profile_results.get(profile["key"], {}).get("action")
                        in {"create", "reuse"}
                        and (
                            profile.get("action") == "compare_or_create"
                            or (profile.get("fields") or {}).get("target_snapshot_id")
                            == evidence.get("source_profile_snapshot_id")
                        )
                    ):
                        source = {
                            "kind": "profile",
                            "snapshot_id": profile_results[profile["key"]][
                                "snapshot_id"
                            ],
                            "url": evidence.get("source_url"),
                            "text": evidence.get("evidence_text"),
                            "observed_at": evidence.get("observed_at"),
                            "observed_handle": evidence.get("observed_handle"),
                            "observation_kind": evidence.get("observation_kind"),
                        }
                    else:
                        evidence_held += 1
                        continue
                    usable_sources.append(source)
                if usable_sources:
                    result = apply_sourced_role(
                        person_id=target.pk,
                        fields=role["fields"],
                        source=usable_sources[0],
                        supporting_sources=usable_sources[1:],
                        expected_action=role["action"],
                        expected_id=role.get("existing_id"),
                        brand_definition=next(
                            (
                                entry
                                for entry in (role.get("chain") or {}).get(
                                    "actions", []
                                )
                                if entry.get("table") == "brands"
                                and entry.get("key") == role["fields"].get("brand_id")
                            ),
                            None,
                        ),
                        selected_brands=selected_brands,
                    )
                    if result["action"] == "hold":
                        evidence_held += len(usable_sources)
                        held += 1
                        role_holds.append({"key": role.get("local_id"), "reason": result["reason"]})
                    elif result.get("held_fields"):
                        entry = {
                            "key": role.get("local_id"),
                            "fields": result["held_fields"],
                            "source_reference": usable_sources[0]["url"],
                            "reason": result.get("held_field_reasons", {}),
                        }
                        if entry not in role_field_holds:
                            role_field_holds.append(entry)
                    if result["action"] != "hold":
                        results.append(result)
                if not usable_sources:
                    held += 1
                    role_holds.append(
                        {
                            "key": role.get("local_id"),
                            "reason": "Role has no reusable source with literal field support",
                        }
                    )
            priority = {"add_evidence": 0, "enrich": 1, "create": 2}
            by_role = {}
            for result in results:
                prior = by_role.get(result["role_id"])
                if prior is None or priority[result["action"]] > priority[prior]:
                    by_role[result["role_id"]] = result["action"]
            return {
                **identity_counts,
                "created": sum(action == "create" for action in by_role.values()),
                "updated": sum(action == "enrich" for action in by_role.values()),
                "reused": sum(action == "add_evidence" for action in by_role.values()),
                "held": held,
                "role_holds": role_holds,
                "role_field_holds": role_field_holds,
                "evidence_held": evidence_held,
                "profiles_created": sum(
                    r["action"] == "create" for r in profile_results.values()
                ),
                "profiles_reused": sum(
                    r["action"] == "reuse" for r in profile_results.values()
                ),
                "profiles_held": sum(
                    r["action"] == "hold" for r in profile_results.values()
                ),
                "profile_holds": [
                    {"key": key, "reason": result.get("reason")}
                    for key, result in profile_results.items()
                    if result["action"] == "hold"
                ],
                "brands_created": sum(
                    result.get("brand_created", False) for result in results
                ),
            }
    except (PersonHold, IdentityHold, ValueError) as exc:
        return {
            "created": 0,
            "updated": 0,
            "reused": 0,
            "held": len(roles),
            "people_held": 1,
            "reason": str(exc),
        }
    except DatabaseError as exc:
        return {
            "created": 0,
            "updated": 0,
            "reused": 0,
            "held": held,
            "failed": len(proposed),
            "people_failed": 1,
            "reason": type(exc).__name__,
        }


class Command(BaseCommand):
    help = "Preview or apply supported saved person actions to the isolated task DB."
    requires_system_checks = ()

    def add_arguments(self, parser):
        parser.add_argument("packet")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--partial-saved-actions",
            "--partial-roles-only",
            dest="partial_saved_actions",
            action="store_true",
        )
        parser.add_argument("--confirm-resource")
        parser.add_argument("--confirm-payload-digest")
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            packet_path, output_path = Path(options["packet"]), Path(options["output"])
            if packet_path.resolve() == output_path.resolve():
                raise ValueError("Report must not overwrite the packet")
            data = json.loads(
                packet_path.read_text(), object_pairs_hook=unique_json_object
            )
            if (
                not isinstance(data, dict)
                or data.get("schema") != "record-job-history-preview/v1"
            ):
                raise ValueError("Expected a prepared record-job-history preview")
            supplied = data.get("payload_digest")
            unsigned = {k: v for k, v in data.items() if k != "payload_digest"}
            if supplied != digest(unsigned):
                raise ValueError("Prepared packet digest does not match its contents")
            people = data.get("people")
            if not isinstance(people, list):
                raise TypeError("Prepared people must be a list")
            if any(
                not isinstance(person, dict) or not person.get("key")
                for person in people
            ):
                raise ValueError("Every prepared person needs a stable key")
            keys = [person["key"] for person in people]
            native_ids = [
                person["native_id"] for person in people if person.get("native_id")
            ]
            if len(set(keys)) != len(keys) or len(set(native_ids)) != len(native_ids):
                raise ValueError("Duplicate prepared person identity")
            report = {
                "schema": "save-person-job-partial-roles/v1",
                "payload_digest": supplied,
                "apply": bool(options["apply"]),
                "complete": False,
                "scope": "Supported source-only identity, name, language, prose, and unambiguous direct-account role actions",
                "unimplemented": [
                    "other profile materialization and compressed-interval reconciliation",
                    "company and brand-company creation",
                ],
                "people": [],
            }
            if options["apply"]:
                if (
                    not options["partial_saved_actions"]
                    or options.get("confirm_payload_digest") != supplied
                ):
                    raise CommandError(
                        "Partial role scope and exact payload digest must be confirmed"
                    )
                if (
                    not isinstance(data.get("selected_brand_ids"), list)
                    or not data["selected_brand_ids"]
                    or any(
                        not isinstance(value, str) or not value
                        for value in data["selected_brand_ids"]
                    )
                ):
                    raise CommandError("Prepared selected brand scope is required")
                verify_target(data, options.get("confirm_resource"))
                posts = {}
                profiles = {}
                for action in data.get("record_actions", []):
                    if action.get("table") == "account_profile_snapshots":
                        key = action["key"]
                        if key in profiles and profiles[key] != action:
                            raise ValueError("Conflicting prepared profile identity")
                        profiles[key] = action
                    if action.get("table") != "posts":
                        continue
                    key = "post:" + str(action["key"])
                    if key in posts and posts[key] != action:
                        raise ValueError("Conflicting prepared post identity")
                    posts[key] = action
                # Prove that the operator can retain a receipt before the first
                # person transaction commits. Runtime I/O failures may still
                # interrupt checkpoints; replay remains idempotent.
                write_report(output_path, report)
                for person in people:
                    report["people"].append(
                        {
                            "key": person.get("key"),
                            **process_person(
                                person,
                                posts,
                                profiles,
                                [
                                    action
                                    for action in data.get("record_actions", [])
                                    if action.get("person_key") == person.get("key")
                                ],
                                data.get("language_review_provenance"),
                                data.get("selected_brand_ids"),
                            ),
                        }
                    )
                    report["totals"] = {
                        key: sum(row.get(key, 0) for row in report["people"])
                        for key in (
                            "created",
                            "updated",
                            "reused",
                            "held",
                            "failed",
                            "evidence_held",
                            "profiles_created",
                            "profiles_reused",
                            "profiles_held",
                            "brands_created",
                            "people_held",
                            "people_failed",
                            "accounts_created",
                            "accounts_reused",
                            "people_created",
                            "people_reused",
                            "names_created",
                            "names_reused",
                            "names_held",
                            "name_evidence_held",
                            "language_updated",
                            "language_retained",
                            "language_held",
                            "language_excluded",
                            "texts_created",
                            "texts_reused",
                            "texts_held",
                        )
                    }
                    write_report(output_path, report)
            else:
                report["people"] = [
                    {"key": p.get("key"), "role_count": len(p.get("affiliations", []))}
                    for p in people
                ]
            write_report(output_path, report)
            self.stdout.write(
                json.dumps(
                    {
                        "report": str(output_path),
                        "people": len(people),
                        "applied": bool(options["apply"]),
                        "complete": False,
                    }
                )
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
