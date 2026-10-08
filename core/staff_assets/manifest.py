"""Versioned, reviewable interchange for a skill or an operator's research."""

import json
from collections import Counter
from pathlib import Path

from core.person_identity import IdentityConflict
from core.staff_assets.intake import (
    ELIGIBLE,
    ingest_record,
    observed_time,
    resolve_person,
    validate_record,
)
from core.staff_assets.media import record_media


def load_manifest(path):
    value = json.loads(Path(path).read_text())
    if value.get("schema") != "staff-intake/v1" or not isinstance(
        value.get("people"), list
    ):
        raise ValueError("Expected staff-intake/v1 with a people array")
    keys = [row.get("source_key") for row in value["people"]]
    if len(keys) != len(set(keys)):
        raise ValueError("Manifest contains duplicate source keys")
    for row in value["people"]:
        validate_record(row)
    return value


def import_manifest(manifest, *, apply=False, asset_root=None):
    counts = Counter()
    records = []
    for record in manifest["people"]:
        validate_record(record)
        eligible = record.get("eligibility") in ELIGIBLE
        try:
            person, _ = resolve_person(record) if eligible else (None, None)
            action = "reuse" if person else "create" if eligible else "exclude"
        except IdentityConflict:
            person, action = None, "needs_review"
        counts[action] += 1
        if apply:
            intake, created = ingest_record(record)
            if intake.person_id:
                for entry in record.get("media", []):
                    record_media(
                        intake.person,
                        entry,
                        asset_root=asset_root,
                        observed_at=observed_time(record.get("observed_at")),
                    )
                person = intake.person
            counts["new_observations" if created else "retained_observations"] += 1
        records.append(
            {
                "source_key": record["source_key"],
                "action": action,
                "person_id": str(person.pk) if person else None,
            }
        )
    return {
        "applied": apply,
        "counts": dict(counts),
        "records": records,
        "source_outcomes": manifest.get("source_outcomes", []),
    }


def saved_title_entries(fields):
    """Carry the saved audit's uncertainty; a reported title is not a verified quote."""
    result = []
    for key, language in (("job_title_zh", "zh-Hans"), ("job_title_en", "en")):
        field = fields.get(key, {})
        if not field.get("value") or not field.get("source"):
            continue
        status = field.get("status", "Unknown")
        translated = "translat" in status.casefold()
        entry = {
            "key": key,
            "language": language,
            "text": field["value"],
            "source_reference": field["source"],
            "origin": "translation"
            if translated
            else "source"
            if field.get("original")
            else "unknown",
            "review_status": "confirmed"
            if status.startswith(("Verified", "Owner-supplied"))
            else "pending",
            "review_note": status + (": " + field["note"] if field.get("note") else ""),
        }
        if (
            translated
            and result
            and result[0]["source_reference"] == entry["source_reference"]
        ):
            entry["derived_from_key"] = result[0]["key"]
        result.append(entry)
    return result


def from_deepseek_dossier(data):
    """Explicit adapter for the saved prototype; generic intake knows no people."""
    records = []
    for person in data["people"]:
        team = person.get("deepseek")
        if not team:
            continue
        staff = team.get("staff_eligibility", {})
        fields = person.get("presentation", {}).get("fields", {})
        record = {
            "source_key": "saved-dossier:" + str(person["id"]),
            "display_name": person["name"],
            "eligibility": "unestablished",
            "observed_at": team["observed_at"],
            "source_dossier": person,
            "names": [],
            "affiliations": [],
            "media": [],
            "texts": [],
        }
        if not staff.get("included"):
            records.append(record)
            continue
        record["eligibility"] = (
            "former_staff"
            if staff.get("status") == "former_staff"
            else "dated_staff"
            if staff.get("view") == "history"
            else "staff"
        )
        if team.get("db_person_id"):
            record["person_id"] = team["db_person_id"]
        if person.get("account_key"):
            record["account_key"] = person["account_key"]
        if person.get("account_id"):
            record["account_id"] = person["account_id"]
        primary = None
        for key, language in (("romanized_name", "en"), ("chinese_name", "zh-Hans")):
            field = fields.get(key, {})
            if not field.get("value") or not field.get("source"):
                continue
            status = field.get("status", "")
            verified = status.startswith(("Verified", "Owner-supplied"))
            name = {
                "full_name": field["value"],
                "language": language,
                "source_kind": "saved_dossier",
                "source_reference": field["source"],
                "source_text": field.get("original") or field["value"],
                "collection_method": "saved-source-audit",
                "review_reason": field.get("note", ""),
            }
            if status.startswith("Owner-supplied"):
                name.update(
                    origin="owner",
                    source_kind="owner_supplied",
                    collection_method="user_provided_profile",
                )
            if verified:
                name["review"] = {
                    "status": "confirmed",
                    "reviewer": "saved source audit",
                    "reason": status
                    + (": " + field["note"] if field.get("note") else ""),
                }
                name["selection"] = "english" if language == "en" else "primary"
                if language == "zh-Hans":
                    primary = name
            record["names"].append(name)
        if primary is None:
            # The English selection can also serve as the sourced primary spelling.
            en = next(
                (
                    entry
                    for entry in record["names"]
                    if entry.get("selection") == "english"
                ),
                None,
            )
            if en:
                record["names"].append({**en, "selection": "primary"})
        # Preserve real existing work history, including a later employer's dates.
        for affiliation in person.get("affiliations", []):
            if affiliation.get("affiliation_type") not in {"employment", "founder"}:
                continue
            for evidence in affiliation.get("evidence", []):
                if not evidence.get("text"):
                    continue
                role = {
                    key: affiliation[key]
                    for key in (
                        "brand_id",
                        "observed_organization_name",
                        "affiliation_type",
                        "status",
                        "title_raw",
                        "title_normalized",
                        "start_date",
                        "start_date_precision",
                        "end_date",
                        "end_date_precision",
                        "location",
                        "department",
                        "team",
                        "description",
                        "review_status",
                        "source_system",
                    )
                    if key in affiliation
                }
                role.update(
                    source_url=evidence.get("source_url")
                    or (
                        f"https://x.com/i/status/{evidence['post_id']}"
                        if evidence.get("post_id")
                        else team["source"]
                    ),
                    evidence_text=evidence["text"],
                    source_data=evidence,
                )
                record["affiliations"].append(role)
        if not any(
            role.get("brand_id") == "deepseek" for role in record["affiliations"]
        ):
            role = {
                "brand_id": "deepseek",
                "observed_organization_name": "DeepSeek",
                "affiliation_type": "founder"
                if team.get("category") == "founder"
                else "employment",
                "title_raw": team.get("title_original"),
                "status": "former"
                if record["eligibility"] == "former_staff"
                else "unknown"
                if record["eligibility"] == "dated_staff"
                else "current",
                "source_url": staff.get("source") or team["source"],
                "evidence_text": staff.get("excerpt_original")
                or person.get("bio")
                or staff["reason"],
                "source_data": {
                    "staff_eligibility": staff,
                    "title_fields": fields,
                    "title_language": team.get("source_language", "und"),
                },
            }
            if person.get("joined") and person.get("joined_source"):
                date = person["joined"]
                role.update(
                    start_date=date,
                    start_date_precision={4: "year", 7: "month", 10: "day"}[len(date)],
                )
            record["affiliations"].append(role)
        candidates = [
            role for role in record["affiliations"] if role["brand_id"] == "deepseek"
        ]
        if len(candidates) == 1:
            candidates[0]["titles"] = saved_title_entries(fields)
        if person.get("location") and person.get("location_source"):
            record["texts"].append(
                {
                    "kind": "location",
                    "language": "und",
                    "text": person["location"],
                    "source_reference": person["location_source"],
                }
            )
        # Prototype biographies can be researcher-written English summaries of
        # Chinese pages. Preserve them in source_dossier, not as original quotes.
        if staff.get("excerpt_original"):
            record["texts"].append(
                {
                    "kind": "role",
                    "text": staff["excerpt_original"],
                    "language": team.get("source_language", "und"),
                    "source_reference": staff.get("source") or team["source"],
                }
            )
        for key, language in (("job_title_zh", "zh-Hans"), ("job_title_en", "en")):
            field = fields.get(key, {})
            if field.get("original") and field.get("source"):
                record["texts"].append(
                    {
                        "kind": "role",
                        "text": field["original"],
                        "language": language,
                        "source_reference": field["source"],
                    }
                )
        checks = person.get("presentation", {}).get("image_checks", {})
        for asset in person.get("photos", []) + person.get("account_images", []):
            check = checks.get(asset.get("src"), {})
            source = asset.get("source") or check.get("evidence_url")
            if not source:
                continue
            entry = {
                "source_url": source,
                "original_url": asset.get("original_url")
                or asset.get("url")
                or asset.get("fetched_url")
                or "",
                "source_kind": check.get("source_kind", "saved_dossier"),
                "discovery_provider": asset.get(
                    "discovery_provider", "Saved collection"
                ),
                "kind": asset.get("kind", "image"),
                "evidence": {
                    "caption": asset.get("label", ""),
                    "original_evidence": asset.get("evidence", ""),
                    "saved_verification": check,
                },
            }
            if asset.get("src"):
                entry["path"] = asset["src"]
            if check.get("reason"):
                entry["review"] = {
                    "reviewer": "saved source audit",
                    "reason": check["reason"],
                    "source_verified": check.get("source_verified", False),
                    "individual_portrait": check.get("individual_portrait", False),
                    "suitability": "approved" if check.get("qualifies") else "pending",
                    "reuse_status": "unknown",
                }
            record["media"].append(entry)
        records.append(record)
    return {
        "schema": "staff-intake/v1",
        "people": records,
        "source_outcomes": [
            {
                "source": "saved DeepSeek dossier",
                "status": "adapted",
                "coverage": "Public staff claims; no complete employee directory",
            }
        ],
    }
