"""Compare saved preview coverage without turning missing sources into facts."""

from collections import Counter, defaultdict

FIELDS = (
    "start_date",
    "end_date",
    "title_raw",
    "job_function",
    "description",
    "team",
    "department",
    "geolocation_id",
    "workplace_type",
)


def _present(value):
    return value is not None and value != ""


def coverage(prepared):
    """Count role entries and distinct people, including held rows explicitly.

    A literal match is only a text match. It is not proof that a claim is true
    or an automatically assigned explicit-date classification.
    """
    people = prepared["people"]
    if len({person["key"] for person in people}) != len(people):
        raise ValueError("Coverage requires distinct prepared people")
    field_counts = {name: Counter() for name in FIELDS}
    field_people = {name: set() for name in FIELDS}
    missing_people = {name: set() for name in FIELDS}
    bases = {name: Counter() for name in ("start_date", "end_date")}
    statuses = Counter()
    present_people = set()
    present_entries = 0
    actions = Counter()
    brands = defaultdict(
        lambda: {"entries": 0, "people": set(), "current": 0, "current_people": set()}
    )
    companies = defaultdict(
        lambda: {"entries": 0, "people": set(), "current": 0, "current_people": set()}
    )
    total = 0
    for person in people:
        for role in person["affiliations"]:
            total += 1
            fields = role["fields"]
            action = role["action"]
            actions[action] += 1
            status = fields.get("status") or "unknown"
            statuses[status] += 1
            if status == "current" and not _present(fields.get("end_date")):
                present_entries += 1
                present_people.add(person["key"])
            for name in FIELDS:
                if _present(fields.get(name)):
                    field_counts[name]["populated_entries"] += 1
                    field_people[name].add(person["key"])
                    if name in bases:
                        entries = role.get("field_sources", {}).get(name, [])
                        values = {item.get("basis") or "unknown" for item in entries}
                        bases[name][
                            " / ".join(sorted(values)) if values else "not_recorded"
                        ] += 1
                else:
                    field_counts[name]["missing_entries"] += 1
                    missing_people[name].add(person["key"])
            chain = role.get("chain") or {}
            for mapping, identifiers in (
                (brands, [chain.get("brand_id")]),
                (companies, set(chain.get("company_ids") or [])),
            ):
                for identifier in identifiers:
                    if not identifier:
                        continue
                    row = mapping[identifier]
                    row["entries"] += 1
                    row["people"].add(person["key"])
                    row["current"] += status == "current"
                    if status == "current":
                        row["current_people"].add(person["key"])

    def render(mapping):
        return {
            key: {
                "entries": value["entries"],
                "people": len(value["people"]),
                "current_entries": value["current"],
                "current_people": len(value["current_people"]),
            }
            for key, value in sorted(mapping.items())
        }

    return {
        "people": len(people),
        "people_without_structured_roles": sum(
            not person["affiliations"] for person in people
        ),
        "role_entries": total,
        "actions": dict(actions),
        "statuses": dict(statuses),
        "present_without_end_date": {
            "entries": present_entries,
            "people": len(present_people),
        },
        "fields": {
            name: {
                "populated_entries": field_counts[name]["populated_entries"],
                "missing_entries": field_counts[name]["missing_entries"],
                "populated_people": len(field_people[name]),
                "missing_people": len(missing_people[name]),
                **({"basis_entries": dict(bases[name])} if name in bases else {}),
            }
            for name in FIELDS
        },
        "brands": render(brands),
        "companies": render(companies),
        "scope": prepared.get("role_counts"),
        "payload_digest": prepared.get("payload_digest"),
    }


def compare(before, after):
    """Compare the same people, disclosing changed input or structured scope."""
    if {p["key"] for p in before["people"]} != {p["key"] for p in after["people"]}:
        raise ValueError("Coverage comparison requires the same person cohort")
    return {
        "before": coverage(before),
        "after": coverage(after),
        "same_input_digest": bool(before.get("input_digest"))
        and before.get("input_digest") == after.get("input_digest"),
        "same_target_inventory": bool(before.get("target_inventory_digest"))
        and before.get("target_inventory_digest")
        == after.get("target_inventory_digest"),
        "limitation": "Changed inputs or structured scope make counts unsuitable as a recall comparison.",
    }
