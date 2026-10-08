"""Evidence-backed direct mentions and distinct-post rollups; no inferred mentions."""

from django.db import transaction

from core.measurement_taxonomy import digest, require
from core.models import (
    MeasurementSubject,
    Post,
    PostBrand,
    PostSubjectAttribution,
    ProductGroupMembership,
    SubjectRelationship,
)


@transaction.atomic
def record_attribution(
    version,
    post,
    subject_id,
    *,
    observed_name,
    policy_version,
    evidence,
    kind="direct_mention",
):
    key = str(subject_id)
    require(key in version.snapshot["subjects"], "attribution subject outside taxonomy")
    require(
        policy_version and observed_name and evidence, "attribution provenance required"
    )
    if kind == "legacy_brand":
        subject = version.snapshot["subjects"][key]
        require(
            subject["kind"] == "brand"
            and PostBrand.objects.filter(post=post, brand_id=subject["key"]).exists(),
            "legacy attribution requires existing brand evidence",
        )
    else:
        require(
            kind == "direct_mention" and evidence.get("reviewed_by"),
            "reviewed direct evidence required",
        )
        start, end = evidence.get("span_start"), evidence.get("span_end")
        require(
            type(start) is int
            and type(end) is int
            and 0 <= start < end <= len(post.text or ""),
            "valid literal span required",
        )
        require(
            post.text[start:end].casefold() == observed_name.casefold(),
            "observed name does not match evidence span",
        )
    assertion_key = digest({"kind": kind, "name": observed_name, "evidence": evidence})
    return PostSubjectAttribution.objects.get_or_create(
        post=post,
        subject_id=subject_id,
        taxonomy_version=version,
        policy_version=policy_version,
        assertion_key=assertion_key,
        defaults={
            "attribution_kind": kind,
            "observed_name": observed_name,
            "evidence": evidence,
        },
    )[0]


def subject_posts(version, subject_id, *, policy_version):
    key = str(subject_id)
    require(key in version.snapshot["subjects"], "query subject outside taxonomy")
    selected = {key}
    queue = [key]
    edges = {}
    for parent, child in SubjectRelationship.objects.filter(
        taxonomy_version=version
    ).values_list("parent_subject_id", "child_subject_id"):
        edges.setdefault(str(parent), set()).add(str(child))
    while queue:
        current = queue.pop()
        children = set(edges.get(current, set()))
        subject = version.snapshot["subjects"][current]
        if subject["kind"] == "product_group":
            products = ProductGroupMembership.objects.filter(
                taxonomy_version=version,
                group_id=subject["key"],
                membership_status="included",
            ).values_list("product_id", flat=True)
            children.update(
                str(pk)
                for pk in MeasurementSubject.objects.filter(
                    product_id__in=products
                ).values_list("pk", flat=True)
            )
        for child in children - selected:
            require(
                child in version.snapshot["subjects"], "rollup edge outside taxonomy"
            )
            selected.add(child)
            queue.append(child)
        require(len(selected) <= 10000, "rollup subject budget exceeded")
    posts = PostSubjectAttribution.objects.filter(
        taxonomy_version=version, subject_id__in=selected, policy_version=policy_version
    ).values_list("post_id", flat=True)
    return Post.objects.filter(pk__in=posts)
