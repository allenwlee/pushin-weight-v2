"""Reviewed, versioned taxonomy. Measurement ingestion never edits this catalog."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict

from django.db import transaction

from core.models import (
    Account,
    Brand,
    Company,
    DataSource,
    MeasurementSubject,
    Product,
    ProductGroup,
    ProductGroupMembership,
    ProductRelationship,
    SubjectRelationship,
    TaxonomyVersion,
)

RELATIONS = {"new_version", "finetune", "adapter", "quantized", "merge"}


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def subject_id(kind, key):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"pushinweight:subject:{kind}:{key}")


def prepare_taxonomy(spec):
    require(bool(spec.get("reviewed_by")), "reviewed_by is required")
    require(len(spec.get("subjects", [])) <= 10000, "subject budget exceeded")
    snapshot = {
        "subjects": {},
        "products": {},
        "groups": {},
        "relationships": spec.get("relationships", []),
        "affiliations": spec.get("affiliations", []),
    }
    for row in spec.get("subjects", []):
        kind, key = row["kind"], str(row["key"])
        model = {
            "brand": Brand,
            "company": Company,
            "product": Product,
            "account": Account,
        }.get(kind)
        require(model is not None, "unsupported subject kind")
        obj = model.objects.get(
            **({"product_key": key} if kind == "product" else {"pk": key})
        )
        label = obj.display_name or str(obj.pk)
        if kind == "product":
            require(obj.type is not None, f"unreviewed product type: {key}")
            snapshot["products"][key] = {
                "label": label,
                "type": obj.type,
                "brand": obj.brand_id,
                "repo_id": obj.repo_id,
            }
        snapshot["subjects"][str(subject_id(kind, key))] = {
            "kind": kind,
            "key": key,
            "label": label,
        }
        if kind == "account":
            snapshot["subjects"][str(subject_id(kind, key))].update(
                data_source=obj.data_source_id,
                normalized_identifier=obj.normalized_identifier,
                account_kind=obj.account_kind,
            )
    graph = defaultdict(set)
    edge_kinds = defaultdict(set)
    for edge in snapshot["relationships"]:
        parent, child = edge["parent"], edge["child"]
        require(
            parent in snapshot["products"] and child in snapshot["products"],
            "relationship target outside snapshot",
        )
        require(
            edge["type"] in RELATIONS and bool(edge.get("evidence")),
            "invalid relationship evidence/type",
        )
        for role, key in (("parent", parent), ("child", child)):
            evidence_repo = edge["evidence"].get(f"{role}_repo_id")
            require(
                evidence_repo is None
                or evidence_repo == snapshot["products"][key]["repo_id"],
                "relationship evidence identity mismatch",
            )
        require(parent != child, "relationship cycle/self-link")
        graph[parent].add(child)
        edge_kinds[parent, child].add(edge["type"])
        require(
            len(edge_kinds[parent, child]) == 1,
            "contradictory relationship descriptors",
        )
    visited, active = set(), set()

    def visit(node):
        require(node not in active, "relationship cycle")
        if node in visited:
            return
        active.add(node)
        for child in graph[node]:
            visit(child)
        active.remove(node)
        visited.add(node)

    for node in list(graph):
        visit(node)
    for group in spec.get("groups", []):
        require(group["key"] not in snapshot["groups"], "duplicate group key")
        require(
            group.get("rule_kind", "manual") in {"manual", "new_version_chain"},
            "unsupported group rule",
        )
        selected, paths = set(group.get("include", [])), {}
        supporting_paths = defaultdict(list)
        if group.get("rule_kind") == "new_version_chain":
            root = group["root"]
            require(root in snapshot["products"], "unknown group root")
            owners = group.get("owner_brands", [])
            require(bool(owners), "successor rule needs reviewed ownership scope")
            queue = [(root, [])]
            traversed = 0
            while queue:
                traversed += 1
                require(traversed <= 10000, "group path budget exceeded")
                node, path = queue.pop()
                require(
                    snapshot["products"][node]["brand"] in owners,
                    "successor outside reviewed ownership scope",
                )
                if path in supporting_paths[node]:
                    continue
                supporting_paths[node].append(path)
                require(
                    node in paths or len(paths) < 1000,
                    "group traversal budget exceeded",
                )
                paths.setdefault(node, path)
                selected.add(node)
                for edge in snapshot["relationships"]:
                    if edge["parent"] == node and edge["type"] == "new_version":
                        queue.append((edge["child"], path + [edge]))
        excluded = set(group.get("exclude", []))
        require(
            (selected | excluded) <= snapshot["products"].keys(),
            "group member outside snapshot",
        )
        snapshot["groups"][group["key"]] = {
            **group,
            "included": sorted(selected - excluded),
            "excluded": sorted(excluded),
            "paths": paths,
            "supporting_paths": dict(supporting_paths),
        }
        gid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pushinweight:group:{group['key']}"))
        snapshot["subjects"][str(subject_id("product_group", gid))] = {
            "kind": "product_group",
            "key": gid,
            "label": group["name"],
            "group_key": group["key"],
        }
    for edge in snapshot["affiliations"]:
        parent = snapshot["subjects"].get(edge["parent"])
        child = snapshot["subjects"].get(edge["child"])
        require(
            parent is not None and child is not None and bool(edge.get("evidence")),
            "invalid affiliation evidence/subject",
        )
        allowed = (
            parent["kind"] == "company"
            and child["kind"] == "brand"
            and edge["kind"] == "owns"
        ) or (
            parent["kind"] in {"company", "brand"}
            and child["kind"] in {"product", "product_group"}
            and edge["kind"] == "offers"
        )
        require(allowed, "invalid business affiliation")
    return snapshot


@transaction.atomic
def configure_taxonomy(spec):
    snapshot = prepare_taxonomy(spec)
    version, created = TaxonomyVersion.objects.get_or_create(
        version_hash=digest(snapshot),
        defaults={"snapshot": snapshot, "reviewed_by": spec["reviewed_by"]},
    )
    if not created:
        return version
    for key, group in snapshot["groups"].items():
        gid = uuid.uuid5(uuid.NAMESPACE_URL, f"pushinweight:group:{key}")
        obj, _ = ProductGroup.objects.update_or_create(
            group_key=key,
            defaults={
                "id": gid,
                "name": group["name"],
                "description": group.get("description", ""),
                "group_kind": group.get("group_kind", "series"),
                "rule_kind": group.get("rule_kind", "manual"),
                "root_product_id": group.get("root"),
                "rule_version": group.get("rule_version", 1),
                "rule_configuration": {
                    "owner_brands": group.get("owner_brands", []),
                    "allowed_relations": ["new_version"],
                },
                "rule_taxonomy_version": version,
            },
        )
        for status in ("included", "excluded"):
            for product_key in group[status]:
                method = (
                    "manual_exclude"
                    if status == "excluded"
                    else (
                        "manual_include"
                        if product_key in group.get("include", [])
                        else "rule_generated"
                    )
                )
                ProductGroupMembership.objects.create(
                    taxonomy_version=version,
                    group=obj,
                    product_id=product_key,
                    membership_status=status,
                    membership_method=method,
                    rule_version=obj.rule_version
                    if method == "rule_generated"
                    else None,
                    evidence={
                        "path": group["paths"].get(product_key, []),
                        "supporting_paths": group["supporting_paths"].get(
                            product_key, []
                        ),
                        "root": group.get("root"),
                        "rule_hash": digest(group),
                    },
                )
    for sid, row in snapshot["subjects"].items():
        MeasurementSubject.objects.get_or_create(
            id=sid,
            defaults={"subject_kind": row["kind"], f"{row['kind']}_id": row["key"]},
        )
    for edge in snapshot["relationships"]:
        source = edge.get("source")
        require(
            not source or DataSource.objects.filter(pk=source).exists(),
            "unknown relationship source",
        )
        ProductRelationship.objects.create(
            taxonomy_version=version,
            parent_product_id=edge["parent"],
            child_product_id=edge["child"],
            relationship_type=edge["type"],
            source_id=source,
            evidence_method=edge.get("evidence_method", "source_reported"),
            evidence=edge["evidence"],
            reviewed_by=spec["reviewed_by"],
        )
    for edge in snapshot["affiliations"]:
        SubjectRelationship.objects.create(
            taxonomy_version=version,
            parent_subject_id=edge["parent"],
            child_subject_id=edge["child"],
            relation_kind=edge["kind"],
            evidence=edge["evidence"],
        )
    return version


def resolve_products(version, target):
    """Resolve only frozen business/group edges; never technical descendants."""
    snap = version.snapshot
    require(str(target) in snap["subjects"], "subject outside taxonomy version")
    seen, result, queue = set(), set(), [str(target)]
    while queue:
        sid = queue.pop()
        if sid in seen:
            continue
        seen.add(sid)
        require(len(seen) <= 10000, "rollup budget exceeded")
        row = snap["subjects"][sid]
        if row["kind"] == "product":
            result.add(row["key"])
        elif row["kind"] == "product_group":
            result.update(snap["groups"][row["group_key"]]["included"])
        for edge in snap["affiliations"]:
            if edge["parent"] == sid:
                queue.append(edge["child"])
    return result
