"""Prepare sourced employment rows against a saved, read-only target inventory.

This module has no database writer or provider client. Its output is a proposal,
including explicit unresolved records, for the existing staff import path.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from urllib.parse import urlsplit

from core.person_affiliations import reconcile_role
from core.person_names import digest

TEXT_FIELDS = (
    "title_raw",
    "title_normalized",
    "job_function",
    "department",
    "team",
    "description",
    "seniority",
    "employment_type",
    "workplace_type",
)
ROLE_FIELDS = set(TEXT_FIELDS) | {
    "organization",
    "status",
    "affiliation_type",
    "start_date",
    "start_date_precision",
    "end_date",
    "end_date_precision",
    "location_text",
    "source_keys",
    "note",
    "review_note",
}


def normalized(value):
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", value or "").casefold())


def date_display(value, precision):
    if value is None:
        return "Unknown"
    return (
        value.replace("-", "") + {"day": "", "month": "00", "year": "0000"}[precision]
    )


def _time(value):
    if not value:
        return None
    if not isinstance(value, str):
        raise TypeError("Source observation must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Source observation requires a timezone")
    return parsed.isoformat()


def _validate_person(person, *, allow_missing_clocks=False):
    if not isinstance(person, dict):
        raise TypeError("Each person must be an object")
    handle = person.get("handle")
    if not isinstance(handle, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
        raise ValueError("Expected an X handle without @")
    native = person.get("native_id")
    if native is not None and (
        not isinstance(native, str) or not re.fullmatch(r"[0-9]+", native)
    ):
        raise ValueError("Native X identity must be a decimal string")
    names = person.get("names", [])
    if not isinstance(names, list) or any(
        not isinstance(n, str) or not n.strip() for n in names
    ):
        raise ValueError("Names must be an array of nonempty text")
    if person.get("outcome", "unresolved") not in {
        "supported",
        "unresolved",
        "excluded",
    }:
        raise ValueError("Invalid person outcome")
    name_source = person.get("name_source")
    if names:
        if not isinstance(name_source, dict):
            raise ValueError("A saved name requires source information")
        name_time = _time(name_source.get("observed_at"))
        if not name_time and not allow_missing_clocks:
            raise ValueError("A saved name requires its source observation time")
    if not isinstance(person.get("roles", []), list) or not isinstance(
        person.get("sources"), list
    ):
        raise TypeError("Roles and sources must be arrays")
    for source in person["sources"]:
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("key"), str)
            or not source["key"]
        ):
            raise ValueError("A source requires a text key")
        if source.get("kind") not in {"saved_bio", "own_post", "third_party_post"}:
            raise ValueError("Unknown saved source kind")
        if not isinstance(source.get("text"), str) or not source["text"].strip():
            raise ValueError("Saved source evidence must not be blank")
        observations = source.get("observations") or [
            {"observed": source.get("observed_at")}
        ]
        if not isinstance(observations, list) or any(
            not isinstance(o, dict) for o in observations
        ):
            raise ValueError("Saved evidence requires observation objects")
        for observation in observations:
            if not _time(observation.get("observed")) and not allow_missing_clocks:
                raise ValueError("Saved evidence requires an observation timestamp")
        _time(source.get("published_at"))


def source_post_id(source, observation=None):
    """Resolve the saved post identity from either supported source shape."""
    return (
        source.get("native_post_id")
        or source.get("post_id")
        or source.get("tweet_id")
        or (observation or {}).get("post_id")
    )


def _source_evidence(person, source, *, include_details=False):
    """Keep each distinct saved observation; never substitute a post's date."""
    observations = source.get("observations") or [
        {"observed": source.get("observed_at")}
    ]
    result = []
    for observation in observations:
        handle = observation.get("handle") or person["handle"]
        post_id = source_post_id(source, observation)
        url = source.get("url") or f"https://x.com/{handle}"
        if post_id and not source.get("url"):
            url += f"/status/{post_id}"
        evidence = {
            "source_key": source["key"],
            "source_kind": source["kind"],
            "source_url": url,
            "evidence_text": source["text"],
            "observed_at": _time(observation.get("observed")),
            "published_at": _time(source.get("published_at")),
            "native_post_id": post_id,
            # A production source identity is not a staging FK.
            "source_post_id": None,
            "source_profile_snapshot_id": None,
            "extraction_method": "record-job-history-saved-review-v1",
            "review_status": "pending",
        }
        if include_details:
            evidence["observation_kind"] = observation.get("kind")
            evidence["observed_handle"] = observation.get("handle")
            evidence["source_account_key"] = observation.get("account_key")
        evidence["local_id"] = "evidence:" + digest(evidence)[:20]
        result.append(evidence)
    return result


def _match_target_profile(action, snapshots):
    """Bind only an exact, independently verifiable target observation."""
    from core.profile_snapshots import _profile_hash

    fields = action["fields"]
    account_key = fields.get("account_key")
    observed = fields.get("observed_at")
    handle = fields.get("observed_handle")
    kind = fields.get("observation_kind")
    if (
        not account_key
        or not observed
        or not handle
        or kind
        not in {
            "account.profile_bio_text",
            "snapshot.profile_bio_text",
            "post.saved_bio",
        }
    ):
        return None
    parsed = urlsplit(fields.get("source_reference") or "")
    parts = parsed.path.strip("/").split("/")
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"x.com", "twitter.com", "www.twitter.com"}
        or parsed.username is not None
        or not parts
        or parts[0].casefold() != handle.casefold()
    ):
        return None
    if len(parts) == 1:
        post_id = None
    elif (
        len(parts) == 3
        and parts[1] == "status"
        and parts[2].isascii()
        and parts[2].isdigit()
        and int(parts[2]) > 0
        and str(int(parts[2])) == parts[2]
    ):
        post_id = parts[2]
    else:
        return None
    if (
        kind == "account.profile_bio_text"
        and post_id
        or kind == "post.saved_bio"
        and not post_id
    ):
        return None
    observed_at = datetime.fromisoformat(_time(observed))
    candidates = []
    overlapping = []
    for row in snapshots:
        if str(row.get("account_key")) != str(account_key):
            continue
        try:
            first = datetime.fromisoformat(_time(row.get("first_observed_at")))
            last = datetime.fromisoformat(_time(row.get("last_observed_at")))
        except (ValueError, TypeError):
            return None
        if first <= observed_at <= last:
            overlapping.append(row)
        profile_data = row.get("profile_data")
        present = row.get("present_fields")
        if (
            not isinstance(profile_data, dict)
            or not isinstance(present, list)
            or not isinstance(row.get("profile_hash"), str)
        ):
            continue
        if _profile_hash(profile_data, present) != row["profile_hash"]:
            continue
        expected_kinds = {"post"} if post_id else {"account", "saved_bio"}
        if (
            row.get("id") is not None
            and first == observed_at
            and row.get("first_source_kind") in expected_kinds
            and str(row.get("first_source_post_id") or "") == str(post_id or "")
            and profile_data.get("profile_bio_text") == fields.get("saved_bio")
            and row.get("handle")
            and str(row["handle"]).casefold() == handle.casefold()
        ):
            candidates.append(row)
    if len(candidates) != 1 or any(
        row.get("profile_hash") != candidates[0]["profile_hash"] for row in overlapping
    ):
        return None
    return candidates[0].get("id")


def _can_create_target_profile(action, snapshots):
    """Propose dated account bios outside every known compressed interval."""
    fields = action["fields"]
    account, handle, observed = (
        fields.get("account_key"),
        fields.get("observed_handle"),
        fields.get("observed_at"),
    )
    if (
        not account
        or not handle
        or not observed
        or fields.get("observation_kind") != "account.profile_bio_text"
        or not fields.get("saved_bio")
    ):
        return False
    parsed = urlsplit(fields.get("source_reference") or "")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "x.com"
        or parsed.username is not None
        or parsed.path.strip("/").casefold() != handle.casefold()
    ):
        return False
    try:
        when = datetime.fromisoformat(_time(observed))
        if when.utcoffset() is None:
            return False
        for row in snapshots:
            first = datetime.fromisoformat(_time(row.get("first_observed_at")))
            last = datetime.fromisoformat(_time(row.get("last_observed_at")))
            if first.utcoffset() is None or last.utcoffset() is None or first > last:
                return False
            if first <= when <= last:
                return False
        return True
    except (TypeError, ValueError):
        return False


class Catalogue:
    def __init__(self, inventory, aliases):
        self.brands = {x["nickname"]: x for x in inventory["brands"]}
        self.companies = {x["nickname"]: x for x in inventory["companies"]}
        self.brand_names = defaultdict(set)
        self.company_names = defaultdict(set)
        for key, row in self.brands.items():
            for text in (
                key,
                row.get("display_name"),
                row.get("display_name_en"),
                row.get("display_name_zh_cn"),
            ):
                if text:
                    self.brand_names[normalized(text)].add(key)
        for key in self.companies:
            self.company_names[normalized(key)].add(key)
        for row in inventory.get("company_labels", []):
            self.company_names[normalized(row["label"])].add(row["company_id"])
        self.links = defaultdict(set)
        for row in inventory["brand_companies"]:
            self.links[row["brand_id"]].add(row["company_id"])
        self.aliases = aliases or {}
        self.actions = {}

    def action(self, table, key, action, fields):
        entry = {"table": table, "key": key, "action": action, "fields": fields}
        self.actions[(table, str(key))] = entry
        return entry

    def resolve(self, organization):
        if re.search(
            r"\b(unnamed|undisclosed|unspecified|unknown|unidentified|unresolved|stealth|FAANG)\b|not (named|specified)|未具名|未命名",
            organization,
            re.IGNORECASE,
        ):
            return {
                "brand_id": None,
                "company_ids": [],
                "actions": [],
                "issues": [
                    "Organization is not named in the saved evidence; no placeholder company will be created"
                ],
            }
        alias = self.aliases.get(normalized(organization), {})
        brand_ids = set(self.brand_names.get(normalized(organization), ()))
        company_ids = set(self.company_names.get(normalized(organization), ()))
        if alias.get("brand_id"):
            brand_ids = {alias["brand_id"]}
        if alias.get("company_id"):
            company_ids = {alias["company_id"]}
        reasons, actions = [], []
        if len(brand_ids) > 1:
            return {
                "brand_id": None,
                "company_ids": sorted(company_ids),
                "actions": [],
                "issues": [
                    "Multiple matching Brand records: " + ", ".join(sorted(brand_ids))
                ],
            }
        slug = re.sub(
            r"[^\w]+", "-", unicodedata.normalize("NFKC", organization).lower()
        ).strip("-")
        slug = slug[:47] + "-" + digest(organization)[:12] if len(slug) > 64 else slug
        brand_id = next(iter(brand_ids), slug)
        if not brand_id:
            raise ValueError("Organization cannot be empty")
        brand_action = "reuse" if brand_id in self.brands else "create"
        actions.append(
            self.action(
                "brands",
                brand_id,
                brand_action,
                {
                    "nickname": brand_id,
                    "display_name": self.brands.get(brand_id, {}).get("display_name")
                    or organization,
                },
            )
        )
        linked = self.links.get(brand_id, set())
        if linked:
            if company_ids and not company_ids.issubset(linked):
                reasons.append(
                    "Observed company conflicts with existing BrandCompany links"
                )
            company_ids |= linked
        if not company_ids:
            company_ids = {slug}
        if len(company_ids) > 1:
            reasons.append("Multiple Company records; employer mapping requires review")
        for company_id in sorted(company_ids):
            actions.append(
                self.action(
                    "companies",
                    company_id,
                    "reuse" if company_id in self.companies else "create",
                    {"nickname": company_id},
                )
            )
            if company_id not in self.companies:
                actions.append(
                    self.action(
                        "company_labels",
                        company_id + ":und",
                        "create",
                        {
                            "company_id": company_id,
                            "locale_id": "und",
                            "label": organization,
                        },
                    )
                )
            link_exists = company_id in linked
            # Ambiguous matches are exposed, never converted to new ownership claims.
            link_action = "reuse" if link_exists else "hold" if reasons else "create"
            link = self.action(
                "brands_companies",
                brand_id + "/" + company_id,
                link_action,
                {"brand_id": brand_id, "company_id": company_id},
            )
            if not link_exists:
                link["note"] = (
                    "ownership_pct defaults to 1.0 in this table; this source does not establish an equity percentage"
                )
            actions.append(link)
        return {
            "brand_id": brand_id,
            "company_ids": sorted(company_ids),
            "actions": actions,
            "issues": reasons,
        }


def _inventory_indexes(inventory):
    indexes = {
        name: defaultdict(list)
        for name in (
            "accounts_by_native",
            "accounts_by_handle",
            "links_by_account",
            "affiliations_by_person",
            "evidence_by_affiliation",
        )
    }
    for row in inventory["accounts"]:
        indexes["accounts_by_native"][row.get("author_id")].append(row)
        indexes["accounts_by_handle"][normalized(row.get("handle"))].append(row)
    for table, key, index in (
        ("person_accounts", "account_key", "links_by_account"),
        ("affiliations", "person_id", "affiliations_by_person"),
        ("evidence", "affiliation_id", "evidence_by_affiliation"),
    ):
        for row in inventory[table]:
            indexes[index][row[key]].append(row)
    indexes["redirects"] = {
        row["id"]: row.get("merged_into_id") for row in inventory["people"]
    }
    return indexes


def _identity(person, indexes):
    from core.person_identity import account_observation_person_ids

    native = person.get("native_id")
    matches = indexes["accounts_by_native"].get(native, []) if native else []
    handle_matches = indexes["accounts_by_handle"].get(normalized(person["handle"]), [])
    issues = []
    if not native:
        issues.append(
            "Stable X identity missing; handle match alone cannot attach a Person"
        )
    if len(matches) > 1:
        issues.append("Multiple stored Accounts for native X identity")
    account = matches[0] if len(matches) == 1 else None
    key = account["account_key"] if account else None
    handle_conflict = bool(native) and any(
        row.get("author_id") != native for row in handle_matches
    )
    if handle_conflict:
        issues.append(
            "Handle belongs to a different stored X identity; review possible transfer"
        )
    links = indexes["links_by_account"].get(key, []) if key else []
    redirects = indexes["redirects"]

    def canonical(pk):
        seen = set()
        while redirects.get(pk):
            if pk in seen:
                raise ValueError("Cyclic Person identity redirect")
            seen.add(pk)
            pk = redirects[pk]
        return pk

    confirmed = {
        canonical(x["person_id"])
        for x in links
        if x["resolution_status"] == "confirmed"
    }
    pending = {
        canonical(x["person_id"]) for x in links if x["resolution_status"] != "rejected"
    }
    derived = (
        {
            canonical(str(pk))
            for pk in account_observation_person_ids(native)
            if str(pk) in redirects
        }
        if native
        else set()
    )
    resolved = confirmed or derived
    person_id = next(iter(resolved)) if len(resolved) == 1 else None
    if len(resolved) > 1 or (not person_id and pending):
        issues.append("Existing PersonAccount links need identity confirmation")
    if person_id and any(
        canonical(x["person_id"]) == person_id and x["resolution_status"] == "rejected"
        for x in links
    ):
        issues.append("Rejected PersonAccount conflicts with resolved identity")
    return {
        "account_key": key,
        "account_action": "hold"
        if handle_conflict
        else "reuse"
        if key
        else "create"
        if native
        else "resolve",
        "person_id": person_id,
        "person_action": "hold" if issues else "reuse" if person_id else "create",
        "candidate_person_ids": sorted(pending),
        "handle_matches": handle_matches,
        "person_account_action": "reuse"
        if not issues
        and any(
            canonical(x["person_id"]) == person_id
            and x["resolution_status"] != "rejected"
            for x in links
        )
        else "hold"
        if issues
        else "create",
        "issues": issues,
    }


def _role_fields(role):
    from core.targeted_extraction import _temporal_range, _temporal_value

    if not isinstance(role, dict):
        raise TypeError("Each role must be an object")
    if (
        not isinstance(role.get("organization"), str)
        or not role["organization"].strip()
    ):
        raise ValueError("A role requires a named organization")
    if not isinstance(role.get("source_keys"), list) or any(
        not isinstance(k, str) for k in role["source_keys"]
    ):
        raise ValueError("Role source_keys must be a text array")
    if set(role) - ROLE_FIELDS:
        raise ValueError(
            "Unknown role fields: " + ", ".join(sorted(set(role) - ROLE_FIELDS))
        )
    if role.get("status", "unknown") not in {"current", "former", "unknown"}:
        raise ValueError("Invalid affiliation status")
    if role.get("affiliation_type", "employment") not in {
        "employment",
        "founder",
        "contractor",
    }:
        raise ValueError(
            "Only employment/founder/contractor claims belong in this staff preview"
        )
    fields = {k: role.get(k) for k in TEXT_FIELDS}
    if "review_note" in role:
        fields["review_note"] = role["review_note"]
    for key, value in fields.items():
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{key} must be text or null")
    dates = {}
    for name in ("start", "end"):
        dates[name] = _temporal_value(
            role.get(name + "_date"),
            role.get(name + "_date_precision", "unknown"),
            field=name,
            allow_datetime=False,
        )
        fields[name + "_date"], fields[name + "_date_precision"] = dates[name][:2]
    _temporal_range(start=dates["start"], end=dates["end"], field="employment")
    fields.update(
        status=role.get("status", "unknown"),
        affiliation_type=role.get("affiliation_type", "employment"),
        observed_organization_name=role["organization"],
        review_status="pending",
        confidence=None,
        geolocation_id=None,
    )
    return fields


def _coalesce_role_observations(raw_roles):
    """Combine mutually compatible observations; never bridge conflicting spells."""
    roles = deepcopy(raw_roles)
    fields = [_role_fields(role) for role in roles]
    comparable = (*TEXT_FIELDS, "start_date", "end_date")

    def compatible(i, j):
        a, b = fields[i], fields[j]
        return (
            normalized(roles[i]["organization"]) == normalized(roles[j]["organization"])
            and a["status"] == b["status"]
            and a["affiliation_type"] == b["affiliation_type"]
            and all(not a[k] or not b[k] or a[k] == b[k] for k in comparable)
            and (
                not roles[i].get("location_text")
                or not roles[j].get("location_text")
                or roles[i]["location_text"] == roles[j]["location_text"]
            )
        )

    neighbours = {
        i: {j for j in range(len(roles)) if compatible(i, j)} for i in range(len(roles))
    }
    remaining, result, issues, source_groups = set(neighbours), [], [], []
    while remaining:
        group, pending = set(), {min(remaining)}
        while pending:
            i = pending.pop()
            group.add(i)
            pending |= neighbours[i] - group
        remaining -= group
        if not all(group <= neighbours[i] for i in group):
            result.extend(roles[i] for i in sorted(group))
            source_groups.extend([[roles[i]] for i in sorted(group)])
            issues.append(
                "Saved role observations could match different employment spells; retained separately for review"
            )
            continue
        combined = {}
        keys, notes = set(), []
        for i in sorted(group):
            role = roles[i]
            for key, value in role.items():
                if key not in {
                    "source_keys",
                    "note",
                    "start_date_precision",
                    "end_date_precision",
                } and value not in (None, ""):
                    combined.setdefault(key, value)
            for edge in ("start", "end"):
                if role.get(edge + "_date"):
                    combined[edge + "_date_precision"] = role[edge + "_date_precision"]
            keys.update(role["source_keys"])
            if role.get("note") and role["note"] not in notes:
                notes.append(role["note"])
        combined["source_keys"] = sorted(keys)
        combined["note"] = "\n".join(notes)
        result.append(combined)
        source_groups.append([roles[i] for i in sorted(group)])
    return result, issues, source_groups


def _language_assignment_members(assignment, people):
    """Validate an explicit owner decision, never infer membership from a name."""
    if assignment is None:
        return set()
    required = {
        "schema",
        "value",
        "origin",
        "decision_id",
        "authorized_by",
        "authorized_at",
        "instruction",
        "evidence_reference",
        "evidence_sha256",
        "expected_count",
        "native_ids",
        "cohort_digest",
    }
    if not isinstance(assignment, dict) or set(assignment) != required:
        raise ValueError(
            "Primary-language assignment requires the exact decision contract"
        )
    if (
        assignment["schema"] != "record-job-history-primary-language/v1"
        or assignment["origin"] != "owner_override"
        or assignment["value"] != "zh-Hans"
    ):
        raise ValueError("Expected an explicit owner_override assigning zh-Hans")
    for field in (
        "decision_id",
        "authorized_by",
        "instruction",
        "evidence_reference",
    ):
        if not isinstance(assignment[field], str) or not assignment[field].strip():
            raise ValueError("Primary-language assignment requires " + field)
    if not _time(assignment["authorized_at"]):
        raise ValueError("Primary-language assignment requires an authorization time")
    if not isinstance(assignment["evidence_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", assignment["evidence_sha256"]
    ):
        raise ValueError("Primary-language assignment requires an evidence SHA-256")
    members = assignment["native_ids"]
    count = assignment["expected_count"]
    if (
        not isinstance(members, list)
        or type(count) is not int
        or count < 1
        or len(members) != count
        or any(
            not isinstance(i, str) or not re.fullmatch(r"[0-9]+", i) for i in members
        )
    ):
        raise ValueError("Primary-language roster must contain the expected native IDs")
    if len(set(members)) != count:
        raise ValueError("Duplicate native ID in primary-language roster")
    if assignment["cohort_digest"] != digest(sorted(members)):
        raise ValueError("Primary-language cohort digest does not match its roster")
    available = {p.get("native_id") for p in people}
    if set(members) - available:
        raise ValueError(
            "Primary-language roster contains identities absent from this input"
        )
    return set(members)


def prepare_job_history(
    people,
    inventory,
    *,
    aliases=None,
    primary_language_assignment=None,
    fresh_language=False,
    selected_brands=None,
    language_exclusions=None,
    audited_names=None,
    review_provenance=None,
    name_review_digest=None,
):
    """Return a deterministic proposal; never resolve identities by display name."""
    language_members = _language_assignment_members(primary_language_assignment, people)
    if fresh_language:
        from core.staff_assets.job_history_names import assess_fresh, load_lexicon

        lexicon = load_lexicon()
    name_audit = {}
    if audited_names is not None:
        if not isinstance(audited_names, list):
            raise ValueError("Name audit must be an array")
        for row in audited_names:
            if not isinstance(row, dict):
                raise TypeError("Invalid name audit row")
            if row.get("chinese_name"):
                native_id = row.get("native_id")
                if (
                    not isinstance(native_id, str)
                    or native_id in name_audit
                    or row.get("category") != "apparent_full_chinese_name"
                ):
                    raise ValueError("Invalid or duplicate reviewed name identity")
                name_audit[native_id] = row
        available_ids = {person.get("native_id") for person in people}
        if set(name_audit) - available_ids:
            raise ValueError("Reviewed name identity absent from source packet")
    existing_people = {p["id"]: p for p in inventory["people"]}
    catalogue = Catalogue(inventory, aliases)
    indexes = _inventory_indexes(inventory)
    prepared, seen, record_actions = [], set(), []
    audited_evidence_by_key = {}
    role_counts = Counter(
        {"input": 0, "coalesced": 0, "structured": 0, "outside_scope": 0, "held": 0}
    )
    for person in people:
        _validate_person(person, allow_missing_clocks=selected_brands is not None)
        allowed = {
            "native_id",
            "handle",
            "names",
            "outcome",
            "note",
            "roles",
            "sources",
            "discovery_brands",
            "name_source",
        }
        if set(person) - allowed:
            raise ValueError(
                "Unknown person fields: " + ", ".join(sorted(set(person) - allowed))
            )
        identity_key = (
            person.get("native_id") or "handle:" + person["handle"].casefold()
        )
        if identity_key in seen:
            raise ValueError("Duplicate stable identity in input: " + identity_key)
        seen.add(identity_key)
        sources = {x["key"]: x for x in person["sources"]}
        if len(sources) != len(person["sources"]):
            raise ValueError("Duplicate source key")
        identity = _identity(person, indexes)
        issues = list(identity["issues"])
        if selected_brands is not None:
            if person.get("names") and not (person.get("name_source") or {}).get(
                "observed_at"
            ):
                issues.append("Saved name has no observation time")
            for source in person["sources"]:
                observations = source.get("observations") or [
                    {"observed": source.get("observed_at")}
                ]
                if any(not observation.get("observed") for observation in observations):
                    issues.append(
                        "Saved source has no observation time: " + source["key"]
                    )
        roles = {}
        held_roles = []
        summary_clauses = defaultdict(list)
        summary_holds = set()
        observed_roles, role_issues, source_groups = _coalesce_role_observations(
            person.get("roles", [])
        )
        issues.extend(role_issues)
        role_counts["input"] += len(person.get("roles", []))
        role_counts["coalesced"] += len(observed_roles)
        for raw, source_group in zip(observed_roles, source_groups, strict=True):
            fields = _role_fields(raw)
            keys = raw.get("source_keys", [])
            if not keys or not set(keys).issubset(sources):
                raise ValueError("Role must cite this person's saved evidence")
            if selected_brands is not None:
                org_key = normalized(raw["organization"])
                alias = catalogue.aliases.get(org_key, {})
                matches = (
                    {alias["brand_id"]}
                    if alias.get("brand_id")
                    else catalogue.brand_names.get(org_key, set())
                )
                in_scope = set(matches) & set(selected_brands)
                if in_scope and (
                    len(matches) > 1 or next(iter(in_scope)) not in catalogue.brands
                ):
                    issues.append(
                        "Selected organization needs identity reconciliation: "
                        + raw["organization"]
                    )
                    held_roles.append(
                        {
                            "organization": raw["organization"],
                            "fields": fields,
                            "evidence": [
                                entry
                                for key in keys
                                for entry in _source_evidence(
                                    person,
                                    sources[key],
                                    include_details=selected_brands is not None,
                                )
                            ],
                        }
                    )
                    continue
                if not in_scope:
                    role_counts["outside_scope"] += 1
                    for source_role in source_group:
                        source_fields = _role_fields(source_role)
                        source_keys = source_role["source_keys"]
                        parts = [
                            source_fields.get("title_raw"),
                            source_fields.get("job_function"),
                            source_fields.get("team"),
                            source_fields.get("description"),
                        ]
                        details = ", ".join(
                            dict.fromkeys(value for value in parts if value)
                        )
                        dates = "–".join(
                            value
                            for value in (
                                source_fields.get("start_date"),
                                source_fields.get("end_date"),
                            )
                            if value
                        )
                        status = (
                            source_fields["status"]
                            if source_fields["status"] != "unknown"
                            else ""
                        )
                        if status == "current" and "certainty: low" in (
                            source_fields.get("review_note") or ""
                        ):
                            status = "assumed current, low certainty"
                        clause = source_role["organization"] + (
                            ": " + details if details else ""
                        )
                        if dates or status:
                            clause += (
                                " ("
                                + ", ".join(value for value in (dates, status) if value)
                                + ")"
                            )
                        for key in source_keys:
                            source_text = sources[key]["text"].casefold()
                            needs_review = any(
                                value and str(value).casefold() not in source_text
                                for value in [
                                    source_role["organization"],
                                    *parts,
                                    source_fields.get("start_date"),
                                    source_fields.get("end_date"),
                                    status
                                    if status
                                    not in {"", "assumed current, low certainty"}
                                    else None,
                                ]
                            )
                            for evidence in _source_evidence(
                                person, sources[key], include_details=True
                            ):
                                source_identity = (
                                    key,
                                    evidence["source_url"],
                                    evidence["observed_at"],
                                )
                                summary_clauses[source_identity].append(clause)
                                if needs_review:
                                    summary_holds.add(source_identity)
                    continue
            chain = catalogue.resolve(raw["organization"])
            fields["brand_id"] = chain["brand_id"]
            issues.extend(chain["issues"])
            role_key = digest(
                [
                    identity_key,
                    {
                        k: v
                        for k, v in fields.items()
                        if k not in {"observed_organization_name", "review_note"}
                    },
                    raw["organization"] if not chain["brand_id"] else None,
                ]
            )
            evidence = [
                entry
                for key in keys
                for entry in _source_evidence(
                    person, sources[key], include_details=selected_brands is not None
                )
            ]
            if selected_brands is not None:
                for entry in evidence:
                    if entry["source_kind"] == "saved_bio":
                        entry["source_profile_snapshot_ref"] = (
                            "profile:" + digest([identity_key, entry["local_id"]])[:20]
                        )
                    if (
                        entry["source_kind"] in {"own_post", "third_party_post"}
                        and entry["native_post_id"]
                    ):
                        entry["source_post_ref"] = "post:" + str(
                            entry["native_post_id"]
                        )
            existing = [
                x
                for x in indexes["affiliations_by_person"].get(
                    identity["person_id"], []
                )
                if identity["person_id"]
                and not x.get("superseded_by_id")
                and x.get("brand_id") == chain["brand_id"]
            ]
            decision = reconcile_role(fields, existing)
            match = decision["match"]
            action = decision["action"]
            if existing and not match:
                issues.append(
                    "Existing affiliation needs comparison; no automatic overwrite"
                )
            entry = roles.setdefault(
                role_key,
                {
                    "local_id": "affiliation:" + role_key[:20],
                    "existing_id": match["id"] if match else None,
                    "action": action,
                    "fields": fields,
                    "chain": chain,
                    "evidence": [],
                    "source_keys": [],
                    "notes": [],
                    "location_text": raw.get("location_text"),
                    "start_display": date_display(
                        fields["start_date"], fields["start_date_precision"]
                    ),
                    "end_display": date_display(
                        fields["end_date"], fields["end_date_precision"]
                    ),
                    "existing_candidates": existing,
                },
            )
            if selected_brands is not None:
                field_sources = entry.setdefault("field_sources", {})
                for source_role in source_group:
                    for field in (
                        *TEXT_FIELDS,
                        "start_date",
                        "end_date",
                        "status",
                        "location_text",
                    ):
                        value = source_role.get(field)
                        if value in (None, "", "unknown"):
                            continue
                        attributions = []
                        for key in source_role["source_keys"]:
                            match = re.search(
                                re.escape(str(value)),
                                sources[key]["text"],
                                re.IGNORECASE,
                            )
                            if match:
                                attributions.append(
                                    {
                                        "value": value,
                                        "source_keys": [key],
                                        "basis": "literal_match",
                                        "supporting_span": match.group(),
                                    }
                                )
                        if not attributions:
                            inferred = (
                                field == "status"
                                and value == "current"
                                and "certainty: low"
                                in (source_role.get("review_note") or "")
                            )
                            attributions.append(
                                {
                                    "value": value,
                                    "source_keys": sorted(source_role["source_keys"]),
                                    "basis": "owner_low_certainty_inference"
                                    if inferred
                                    else "source_keys_unresolved",
                                    "supporting_span": None,
                                }
                            )
                        for attribution in attributions:
                            if attribution not in field_sources.setdefault(field, []):
                                field_sources[field].append(attribution)
            entry["evidence"].extend(evidence)
            entry["source_keys"].extend(keys)
            if raw.get("note"):
                entry["notes"].append(raw["note"])
        for role in roles.values():
            role["evidence"] = list(
                {x["local_id"]: x for x in role["evidence"]}.values()
            )
            role["source_keys"] = sorted(set(role["source_keys"]))
            role["notes"] = list(dict.fromkeys(role["notes"]))
        ordered = sorted(
            roles.values(),
            key=lambda r: (
                {"current": 0, "former": 1, "unknown": 2}[r["fields"]["status"]],
                r["fields"]["observed_organization_name"].casefold(),
            ),
        )
        outcome = "unresolved" if issues else person.get("outcome", "unresolved")
        if outcome == "supported" and not ordered and not summary_clauses:
            outcome = "unresolved"
            issues.append("No supported employment entry")
        item = {
            "key": identity_key,
            "native_id": person.get("native_id"),
            "handle": person["handle"],
            "names": person.get("names", []),
            "name_source": person.get("name_source"),
            "outcome": outcome,
            "note": person.get("note", ""),
            "issues": list(dict.fromkeys(issues)),
            "identity": identity,
            "affiliations": ordered,
            "sources": deepcopy(person["sources"]),
            "unused_evidence": [
                e
                for source in person["sources"]
                if not any(source["key"] in role["source_keys"] for role in ordered)
                for e in _source_evidence(
                    person, source, include_details=selected_brands is not None
                )
            ],
            "discovery_brands": person.get("discovery_brands", []),
        }
        if selected_brands is not None:
            kinds = Counter(source["kind"] for source in person["sources"])
            item["source_coverage"] = {
                "saved_bios": kinds["saved_bio"],
                "own_posts": kinds["own_post"],
                "third_party_posts": kinds["third_party_post"],
                "observation_count": sum(
                    len(source.get("observations") or [source.get("observed_at")])
                    for source in person["sources"]
                ),
                "history_search": "not_run",
                "source_completeness": "truncated"
                if any(source.get("truncated") is True for source in person["sources"])
                else "unknown",
                "other_biographical_details": "not_fully_extracted",
            }
            item["held_roles"] = held_roles
            item["biography_summaries"] = [
                {
                    "kind": "biography",
                    "origin": "summary",
                    "language": "und",
                    "text": "; ".join(dict.fromkeys(clauses)),
                    "source_reference": url,
                    "source_keys": [source_key],
                    "observed_at": observed,
                    "review_status": "pending",
                    "action": "hold"
                    if not observed
                    or (source_key, url, observed) in summary_holds
                    or identity["person_action"] not in {"create", "reuse"}
                    else "compare_or_create",
                }
                for (source_key, url, observed), clauses in sorted(
                    summary_clauses.items(),
                    key=lambda x: (x[0][0], x[0][1], x[0][2] or ""),
                )
            ]
            versions = {}
            for summary in item["biography_summaries"]:
                version_key = (summary["source_reference"], summary["text"])
                version = versions.get(version_key)
                if version is None:
                    summary["observation_times"] = [summary["observed_at"]]
                    versions[version_key] = summary
                else:
                    if summary["observed_at"] not in version["observation_times"]:
                        version["observation_times"].append(summary["observed_at"])
                    for source_key in summary["source_keys"]:
                        if source_key not in version["source_keys"]:
                            version["source_keys"].append(source_key)
                    if summary["action"] == "hold":
                        version["action"] = "hold"
            item["biography_summaries"] = list(versions.values())
            for version in item["biography_summaries"]:
                version["observation_times"].sort(
                    key=lambda value: (
                        value is not None,
                        datetime.fromisoformat(value).timestamp() if value else 0,
                    )
                )
                version["observed_at"] = version["observation_times"][0]
        if fresh_language:
            assessment = assess_fresh(person, lexicon)
            item["language_assessment"] = assessment
            previous = existing_people.get(identity["person_id"], {})
            native_id = person.get("native_id")
            reason = (language_exclusions or {}).get(native_id)
            if reason or person.get("outcome") == "excluded":
                action = "excluded"
            elif assessment["outcome"] != "assign":
                action = "no_proposal"
            elif (
                language_exclusions is None
                or identity["person_action"]
                not in {
                    "create",
                    "reuse",
                }
                or (
                    identity["person_action"] == "reuse"
                    and "primary_language" not in previous
                )
            ):
                action = "hold"
            elif previous.get("primary_language"):
                action = "retain"
            else:
                action = "propose"
                item["person_fields"] = {"primary_language": "zh-Hans"}
            item["language_proposal"] = {
                "action": action,
                "value": "zh-Hans",
                "exclusion_reason": reason,
            }
        item["existing_affiliations"] = [
            {**row, "evidence": indexes["evidence_by_affiliation"].get(row["id"], [])}
            for row in indexes["affiliations_by_person"].get(identity["person_id"], [])
            if identity["person_id"]
        ]
        language = None
        if person.get("native_id") in language_members:
            previous = existing_people.get(identity["person_id"], {})
            previous_known = (
                identity["person_action"] == "create" or "primary_language" in previous
            )
            value = primary_language_assignment["value"]
            action = identity["person_action"]
            if action == "reuse":
                action = (
                    "retain" if previous.get("primary_language") == value else "update"
                )
            language = {
                "value": value,
                "origin": "owner_override",
                "decision_id": primary_language_assignment["decision_id"],
                "previous_value": previous.get("primary_language"),
                "previous_value_known": previous_known,
                "action": action,
            }
            item["person_fields"] = {"primary_language": value}
            item["primary_language_assignment"] = language
        prepared.append(item)
        ref = identity["person_id"] or "person:" + identity_key
        for table, action, key in (
            (
                "accounts",
                identity["account_action"],
                identity["account_key"] or identity_key,
            ),
            ("people", identity["person_action"], ref),
            (
                "people_accounts",
                identity["person_account_action"],
                ref + "/" + identity_key,
            ),
        ):
            record_action = {
                "table": table,
                "key": key,
                "action": action,
                "person_key": identity_key,
            }
            if (
                table == "people"
                and fresh_language
                and item["language_proposal"]["action"] == "propose"
            ):
                record_action.update(
                    fields=item["person_fields"].copy(),
                    language_proposal=item["language_proposal"].copy(),
                )
                if action == "reuse":
                    record_action["action"] = "update"
            if table == "people" and language:
                record_action.update(
                    action=language["action"],
                    fields=item["person_fields"].copy(),
                    primary_language_assignment=language.copy(),
                )
            record_actions.append(record_action)
        if identity["person_action"] == "create" and person.get("names"):
            name_ref = ref + "/name:und"
            for table, values in (
                (
                    "people_names",
                    {
                        "person_id": ref,
                        "full_name": person["names"][0],
                        "locale_id": "und",
                    },
                ),
                (
                    "people_name_evidence",
                    {
                        "name_id": name_ref,
                        "source_text": person["names"][0],
                        "source_reference": f"https://x.com/{person['handle']}",
                        "observed_at": (person.get("name_source") or {}).get(
                            "observed_at"
                        ),
                        "source_kind": (person.get("name_source") or {}).get(
                            "source_kind", "saved_account_name"
                        ),
                    },
                ),
                (
                    "person_name_selections",
                    {"person_id": ref, "display_locale_id": "und", "name_id": name_ref},
                ),
            ):
                record_actions.append(
                    {
                        "table": table,
                        "key": name_ref,
                        "action": "create"
                        if (person.get("name_source") or {}).get("observed_at")
                        else "hold",
                        "person_key": identity_key,
                        "fields": values,
                        "note": "Local references only. Use existing sourced-name writer; no invented name parts or language.",
                    }
                )
        audited_name = name_audit.get(person.get("native_id"))
        if audited_name:
            full_name = audited_name["chinese_name"]
            saved_texts = person.get("names", []) + [
                source["text"] for source in person["sources"]
            ]
            if (
                not isinstance(full_name, str)
                or not full_name
                or not any(full_name in value for value in saved_texts)
            ):
                raise ValueError("Reviewed name absent from saved source packet")
            existing_name_action = next(
                (
                    action
                    for action in record_actions
                    if action["table"] == "people_names"
                    and action.get("person_key") == identity_key
                    and action["fields"].get("full_name") == full_name
                    and action["fields"].get("locale_id") == "und"
                ),
                None,
            )
            name_ref = (
                existing_name_action["key"]
                if existing_name_action
                else ref + "/reviewed-name:" + digest(full_name)[:20]
            )
            name_action = (
                "compare_or_create"
                if identity["person_action"] in {"create", "reuse"}
                else "hold"
            )
            if not existing_name_action:
                record_actions.append(
                    {
                        "table": "people_names",
                        "key": name_ref,
                        "action": name_action,
                        "person_key": identity_key,
                        "fields": {
                            "person_id": ref,
                            "full_name": full_name,
                            "locale_id": "und",
                            "name_type": "professional",
                            "origin": "source",
                        },
                    }
                )
            name_record = existing_name_action or record_actions[-1]
            for evidence in audited_name.get("evidence", []):
                quote = evidence.get("name") or evidence.get("text") or ""
                if full_name not in quote:
                    continue
                if not any(quote in value for value in saved_texts):
                    raise ValueError(
                        "Reviewed name evidence absent from saved source packet"
                    )
                observations = evidence.get("observations") or [
                    {
                        "observed": evidence.get("observed_at"),
                        "handle": evidence.get("handle"),
                        "post_id": evidence.get("post_id"),
                    }
                ]
                for observation in observations:
                    observed = observation.get("observed")
                    if observed:
                        _time(observed)
                    handle = observation.get("handle") or evidence.get("handle")
                    post_id = observation.get("post_id") or evidence.get("post_id")
                    source_ref = evidence.get("url") or (
                        f"https://x.com/{handle}" if handle else ""
                    )
                    if post_id and source_ref and "/status/" not in source_ref:
                        source_ref += f"/status/{post_id}"
                    name_source = person.get("name_source") or {}
                    reference_verified = bool(
                        quote == name_source.get("source_text")
                        and source_ref == name_source.get("source_reference")
                        and observed
                        and name_source.get("observed_at")
                        and _time(observed) == _time(name_source["observed_at"])
                    ) or any(
                        quote in source["text"]
                        and handle
                        and source_ref.casefold()
                        == (
                            f"https://x.com/{handle}"
                            + (f"/status/{post_id}" if post_id else "")
                        ).casefold()
                        and any(
                            normalized(handle) == normalized(saved.get("handle"))
                            and str(post_id or "") == str(saved.get("post_id") or "")
                            and observed
                            and saved.get("observed")
                            and _time(observed) == _time(saved["observed"])
                            for saved in source.get("observations", [])
                        )
                        for source in person["sources"]
                    )
                    name_evidence = {
                        "name_id": name_ref,
                        "source_text": quote,
                        "source_reference": source_ref,
                        "observed_at": observed,
                        "source_kind": evidence.get("kind", "saved_name"),
                        "collection_method": "saved-name-review",
                        "supports_fields": ["full_name"],
                    }
                    name_evidence_action = {
                        "table": "people_name_evidence",
                        "key": name_ref + "/" + digest(name_evidence)[:20],
                        "action": name_action
                        if observed and source_ref and reference_verified
                        else "hold",
                        "person_key": identity_key,
                        "fields": name_evidence,
                    }
                    prior = audited_evidence_by_key.get(name_evidence_action["key"])
                    if prior is None:
                        audited_evidence_by_key[name_evidence_action["key"]] = (
                            name_evidence_action
                        )
                        record_actions.append(name_evidence_action)
                    else:
                        if any(
                            prior[field] != name_evidence_action[field]
                            for field in name_evidence_action
                        ):
                            raise ValueError(
                                "Conflicting reviewed name evidence identity"
                            )
                        prior["occurrences"] = prior.get("occurrences", 1) + 1
            if not existing_name_action and not any(
                action["table"] == "people_name_evidence"
                and action["fields"]["name_id"] == name_ref
                and action["action"] != "hold"
                for action in record_actions
            ):
                name_record["action"] = "hold"
            item["reviewed_names"] = [
                {
                    "full_name": full_name,
                    "action": name_record["action"],
                    "evidence": [
                        deepcopy(action["fields"])
                        for action in record_actions
                        if action["table"] == "people_name_evidence"
                        and action["fields"].get("name_id") == name_ref
                    ],
                }
            ]
        if selected_brands is not None:
            for source in person["sources"]:
                if source["kind"] == "saved_bio":
                    for evidence in _source_evidence(
                        person, source, include_details=selected_brands is not None
                    ):
                        record_actions.append(
                            {
                                "table": "account_profile_snapshots",
                                "key": "profile:"
                                + digest([identity_key, evidence["local_id"]])[:20],
                                "action": "hold",
                                "person_key": identity_key,
                                "fields": {
                                    "account_key": identity["account_key"],
                                    "source_reference": evidence["source_url"],
                                    "observed_at": evidence["observed_at"],
                                    "saved_bio": evidence["evidence_text"],
                                    "observation_kind": evidence.get(
                                        "observation_kind"
                                    ),
                                    "observed_handle": evidence.get("observed_handle"),
                                    "source_account_key": evidence.get(
                                        "source_account_key"
                                    ),
                                },
                                "note": "Target profile history has not been bound and checked for overlapping observations.",
                            }
                        )
                    continue
                if source["kind"] not in {"own_post", "third_party_post"}:
                    continue
                for evidence in _source_evidence(
                    person, source, include_details=selected_brands is not None
                ):
                    post_id = evidence["native_post_id"]
                    author_id = source.get("author_native_id") or source.get(
                        "author_id"
                    )
                    author_handle = source.get("author_handle")
                    author_matches = (
                        str(author_id) == person.get("native_id")
                        if author_id
                        else isinstance(author_handle, str)
                        and author_handle.casefold() == person["handle"].casefold()
                    )
                    valid_post_id = (
                        isinstance(post_id, str)
                        and post_id.isascii()
                        and post_id.isdigit()
                        and int(post_id) > 0
                        and str(int(post_id)) == post_id
                    )
                    source_url = evidence["source_url"].rstrip("/")
                    try:
                        parsed_url = urlsplit(source_url)
                        url_matches = (
                            valid_post_id
                            and parsed_url.scheme == "https"
                            and parsed_url.hostname
                            in {"x.com", "twitter.com", "www.twitter.com"}
                            and parsed_url.path.endswith("/status/" + post_id)
                        )
                    except ValueError:
                        url_matches = False
                    complete = bool(
                        valid_post_id
                        and url_matches
                        and evidence["published_at"]
                        and evidence["observed_at"]
                        and person.get("native_id")
                        and source["kind"] == "own_post"
                        and author_matches
                    )
                    record_actions.append(
                        {
                            "table": "posts",
                            "key": str(post_id)
                            if post_id
                            else "lookup:" + evidence["local_id"],
                            "action": "compare_or_create" if complete else "hold",
                            "person_key": identity_key,
                            "fields": {
                                "source_reference": evidence["source_url"],
                                "text": evidence["evidence_text"],
                                "native_post_id": post_id,
                                "observed_at": evidence["observed_at"],
                                "published_at": evidence["published_at"],
                                "author_native_id": person.get("native_id")
                                if source["kind"] == "own_post"
                                else None,
                            },
                        }
                    )
        for summary in item.get("biography_summaries", []):
            record_actions.append(
                {
                    "table": "people_texts",
                    "key": digest([ref, summary]),
                    "action": summary["action"],
                    "person_key": identity_key,
                    "fields": summary,
                }
            )
        for role in ordered:
            record_actions.append(
                {
                    "table": "people_brand_affiliations",
                    "key": role["local_id"],
                    "action": role["action"],
                    "person_key": identity_key,
                    "fields": role["fields"],
                }
            )
            for source in role["evidence"]:
                record_actions.append(
                    {
                        "table": "people_brand_affiliation_evidence",
                        "key": role["local_id"] + "/" + source["local_id"],
                        "action": "compare_or_create",
                        "person_key": identity_key,
                        "fields": source,
                    }
                )
    record_actions.extend(catalogue.actions.values())
    if selected_brands is not None:
        grouped_posts = {}
        other_actions = []
        for action in record_actions:
            if action["table"] != "posts":
                other_actions.append(action)
                continue
            fields = dict(action["fields"])
            observed = fields.pop("observed_at")
            previous = grouped_posts.get(action["key"])
            if previous is None:
                action["fields"] = fields
                action["observations"] = [observed]
                action["person_keys"] = [action.pop("person_key")]
                grouped_posts[action["key"]] = action
            else:
                if observed not in previous["observations"]:
                    previous["observations"].append(observed)
                if action["person_key"] not in previous["person_keys"]:
                    previous["person_keys"].append(action["person_key"])
                if fields != previous["fields"]:
                    previous["action"] = "hold"
                    previous.setdefault("conflicting_sources", []).append(fields)
                if action["action"] == "hold":
                    previous["action"] = "hold"
        grouped_profiles = {}
        deduplicated_actions = []
        for action in other_actions:
            if action["table"] != "account_profile_snapshots":
                deduplicated_actions.append(action)
                continue
            previous = grouped_profiles.get(action["key"])
            if previous is None:
                action["occurrences"] = 1
                grouped_profiles[action["key"]] = action
            else:
                previous["occurrences"] += 1
                if previous["fields"] != action["fields"]:
                    previous.setdefault("conflicting_sources", []).append(
                        action["fields"]
                    )
        record_actions = (
            deduplicated_actions
            + list(grouped_profiles.values())
            + list(grouped_posts.values())
        )
        target_snapshots = inventory.get("profile_snapshots")
        if (
            inventory.get("profile_snapshots_complete") is True
            and isinstance(target_snapshots, list)
            and all(isinstance(row, dict) for row in target_snapshots)
        ):
            snapshots_by_account = defaultdict(list)
            for row in target_snapshots:
                snapshots_by_account[str(row.get("account_key"))].append(row)
            for action in grouped_profiles.values():
                if action.get("conflicting_sources"):
                    continue
                target_id = _match_target_profile(
                    action,
                    snapshots_by_account.get(
                        str(action["fields"].get("account_key")), []
                    ),
                )
                if target_id is not None:
                    action["action"] = "reuse"
                    action["fields"]["target_snapshot_id"] = target_id
                    action["note"] = (
                        "Exact target account, source, clock and profile hash verified; recheck before applying."
                    )
                elif _can_create_target_profile(
                    action,
                    snapshots_by_account.get(
                        str(action["fields"].get("account_key")), []
                    ),
                ):
                    action["action"] = "compare_or_create"
                    action["note"] = (
                        "Observation is outside known target intervals; recheck history and provenance under lock before capture."
                    )
        held_posts = {
            "post:" + key
            for key, action in grouped_posts.items()
            if action["action"] == "hold" and not key.startswith("lookup:")
        }
        held_urls = {
            variant["source_reference"]
            for action in grouped_posts.values()
            if action["action"] == "hold"
            for variant in [action["fields"], *action.get("conflicting_sources", [])]
        }
        held_profile_refs = {
            action["key"]
            for action in record_actions
            if action["table"] == "account_profile_snapshots"
            and action["action"] == "hold"
        }
        held_affiliations = set()
        for item in prepared:
            for summary in item.get("biography_summaries", []):
                if summary["source_reference"] in held_urls:
                    summary["action"] = "hold"
                    item["outcome"] = "unresolved"
                    message = "Post source requires identity or content reconciliation"
                    if message not in item["issues"]:
                        item["issues"].append(message)

            for role in item["affiliations"]:
                for evidence in role["evidence"]:
                    profile = grouped_profiles.get(
                        evidence.get("source_profile_snapshot_ref")
                    )
                    if profile and profile["action"] == "reuse":
                        evidence["source_profile_snapshot_id"] = profile["fields"][
                            "target_snapshot_id"
                        ]
                if any(
                    attribution["basis"] == "source_keys_unresolved"
                    for entries in role.get("field_sources", {}).values()
                    for attribution in entries
                ):
                    role["action"] = "hold"
                    held_affiliations.add(role["local_id"])
                    item["outcome"] = "unresolved"
                    message = "Role field sources need attribution"
                    if message not in item["issues"]:
                        item["issues"].append(message)
                profile_only_hold = bool(role["evidence"]) and all(
                    evidence.get("source_profile_snapshot_ref") in held_profile_refs
                    for evidence in role["evidence"]
                )
                if profile_only_hold:
                    role["action"] = "hold"
                    held_affiliations.add(role["local_id"])
                    item["outcome"] = "unresolved"
                    message = "Profile source requires target history comparison"
                    if message not in item["issues"]:
                        item["issues"].append(message)
                if any(
                    evidence["source_kind"] in {"own_post", "third_party_post"}
                    and (
                        not evidence.get("source_post_ref")
                        or evidence["source_post_ref"] in held_posts
                    )
                    for evidence in role["evidence"]
                ):
                    role["action"] = "hold"
                    held_affiliations.add(role["local_id"])
                    item["outcome"] = "unresolved"
                    message = "Post source requires identity or content reconciliation"
                    if message not in item["issues"]:
                        item["issues"].append(message)
        for action in record_actions:
            if (
                action["table"] == "people_brand_affiliation_evidence"
                and action["fields"].get("source_profile_snapshot_ref")
                in held_profile_refs
            ):
                action["action"] = "hold"
            if (
                action["table"] == "people_texts"
                and action["fields"]["source_reference"] in held_urls
            ):
                action["action"] = "hold"
            if (
                (
                    action["table"] == "people_brand_affiliations"
                    and action["key"] in held_affiliations
                )
                or action["table"] == "people_brand_affiliation_evidence"
                and any(
                    action["key"].startswith(key + "/") for key in held_affiliations
                )
            ):
                action["action"] = "hold"
    result = {
        "schema": "record-job-history-preview/v1",
        "database_writes": 0,
        "target": {
            k: inventory.get(k)
            for k in ("database", "captured_at", "read_only", "binding")
        },
        "target_inventory_digest": digest(inventory),
        "input_digest": digest(people),
        "people": prepared,
        "record_actions": record_actions,
        "counts": dict(Counter(p["outcome"] for p in prepared)),
        "affiliation_count": sum(len(p["affiliations"]) for p in prepared),
        "apply_available": False,
    }
    if selected_brands is not None:
        role_counts["structured"] = sum(len(item["affiliations"]) for item in prepared)
        role_counts["held"] = sum(
            len(item.get("held_roles", []))
            + sum(role["action"] == "hold" for role in item["affiliations"])
            for item in prepared
        )
        result["role_counts"] = dict(role_counts)
        result["profile_history_inventory"] = (
            "exact_matches_only"
            if inventory.get("profile_snapshots_complete") is True
            and isinstance(inventory.get("profile_snapshots"), list)
            else "unassessed"
            if "profile_snapshots" in inventory
            else "not_captured"
        )
    if name_review_digest is not None:
        result["name_review_digest"] = name_review_digest
    if review_provenance is not None:
        result["language_review_provenance"] = deepcopy(review_provenance)
    if audited_names is not None:
        result["reviewed_name_audit_digest"] = digest(audited_names)
    if selected_brands is not None:
        result["selected_brand_ids"] = sorted(set(selected_brands))
    if primary_language_assignment is not None:
        result["primary_language_assignment"] = deepcopy(primary_language_assignment)
        result["primary_language_assignment_count"] = len(language_members)
    result["payload_digest"] = digest(result)
    return result
