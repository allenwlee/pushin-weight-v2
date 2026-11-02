"""Conservative, source-backed GitHub project identity signals.

These signals support Product identity only. A profile's current X handle is
not proof that its owner controlled the announcing account at the post date.
"""

import re

from core.product_release_intake import _FUTURE, _NEGATED


def source_names_repository(*, text, author_handle, owner_handle, repository):
    """Return the exact repository basename only for an explicit self-release.

    The caller must separately verify that the exact repository URL occurs in
    the saved source and that the owner profile matches the captured native ID.
    """
    if (not isinstance(text, str) or not isinstance(author_handle, str)
            or not isinstance(owner_handle, str) or not isinstance(repository, str)
            or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", author_handle)
            or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", owner_handle)
            or author_handle.casefold() != owner_handle.casefold()
            or re.match(r"\s*RT\s+@", text, re.IGNORECASE)
            or repository.count("/") != 1 or _FUTURE.search(text) or _NEGATED.search(text)):
        return None
    name = repository.split("/", 1)[1]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,99}", name):
        return None
    parts = re.split(r"[-_]", name)
    if any(not part for part in parts):
        return None
    pattern = r"[-_\s]+".join(re.escape(part) for part in parts)
    statement = re.compile(
        r"\b(?:(?:we(?:['’]re)?|i(?:['’]m)?)\s+(?:(?:have|just|are|am)\s+){0,2}"
        r"(?:released?|releasing|launch(?:ed|ing)?|introduc(?:e|ed|ing)|announc(?:e|ed|ing))|"
        r"(?:excited|pleased|proud|thrilled)\s+to\s+(?:announce|introduce|release|launch)|"
        r"announcing|introducing|launching|releasing)\s+"
        r"(?:(?:our|the|new)\s+){0,2}" + pattern
        + r"(?![A-Za-z0-9_.-])(?!\s+(?-i:[A-Z])[A-Za-z0-9_-]*)",
        re.IGNORECASE,
    )
    match = statement.search(text)
    if not match or "?" in text[match.end():].split("\n", 1)[0].split(".", 1)[0]:
        return None
    prefix = text[max(0, match.start() - 32):match.start()]
    if re.search(r"(?:says?|wrote|quot(?:e|ed))\s*[:\"“]\s*$", prefix, re.IGNORECASE):
        return None
    return name


def retain_named_repository_product(owner_observation, dossier_id):
    """Retain a source-named project identity without confirming its publisher."""
    from uuid import NAMESPACE_URL, uuid5

    from django.db import connection, transaction
    from django.db.models import TextField, Value
    from django.db.models.functions import Lower, Replace

    from core import models
    from core.event_dossiers import add_claim, attach_source
    from core.measurement_taxonomy import digest, resolve_subject_id
    from core.product_release_acquisition import (
        _source_bound_github_repo, github_exact_observation_documents,
        link_reviewed_github_product,
    )
    from core.product_release_github_owner import owner_documents
    from core.product_release_pipeline import ReleaseIdentityBusy, canonical_dossier

    owner, _, _ = owner_documents(owner_observation)
    target = owner_observation.run.job.targets.get(target_role="publisher_profile")
    repo_observation = target.evidence_observation
    repo, _, _ = github_exact_observation_documents(repo_observation)
    name = None
    post_source = None
    for link in repo_observation.run.job.dossier_claim_links.select_related(
        "claim__event_dossier_source__post", "claim__event_dossier_source__event_dossier",
    ):
        claim = link.claim
        source = claim.event_dossier_source
        source_repo = _source_bound_github_repo(claim) if source.post_id else None
        if (not source_repo or source.post.is_retweet or source.post.quoted_status_id
                or canonical_dossier(source.event_dossier_id).pk != dossier_id
                or source_repo.casefold() != repo["full_name"].casefold()):
            continue
        candidate = source_names_repository(
            text=source.post.text, author_handle=source.post.author_handle,
            owner_handle=owner.get("twitter_username"), repository=repo["full_name"],
        )
        if candidate:
            name, post_source = candidate, source
            break
    if not name:
        return None

    with transaction.atomic():
        key = int(digest(["catalog-native-v1", "github", "repository", "repository_id", str(repo["id"])])[:15], 16)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [key])
            if not cursor.fetchone()[0]:
                raise ReleaseIdentityBusy("repository identity review is busy")
        captured = models.CollectionObservation.objects.select_for_update().get(pk=repo_observation.pk)
        mapping = link_reviewed_github_product(captured, repo)
        if captured.product_id:
            product = captured.product
            if mapping is None and product.product_key != uuid5(NAMESPACE_URL, f"https://api.github.com/repositories/{repo['id']}"):
                return None
        else:
            product_key = uuid5(NAMESPACE_URL, f"https://api.github.com/repositories/{repo['id']}")
            normalized = re.sub(r"[-_\s]+", "", name).lower()
            normalized_name = "display_name"
            for separator in ("-", "_", " "):
                normalized_name = Replace(normalized_name, Value(separator), Value(""), output_field=TextField())
            normalized_name = Lower(normalized_name)
            if models.Product.objects.annotate(identity_name=normalized_name).filter(
                identity_name=normalized,
            ).exclude(product_key=product_key).exists():
                return None
            product, created = models.Product.objects.get_or_create(
                product_key=product_key, defaults={"display_name": name, "hf_type": ""},
            )
            models.MeasurementSubject.objects.get_or_create(
                pk=resolve_subject_id("product", str(product.product_key)),
                defaults={"subject_kind": "product", "product": product},
            )
            captured.product = product
            captured.created_product = created
            captured.save(update_fields=["product", "created_product", "updated_at"])
        canonical_source = attach_source(dossier_id, post_id=post_source.post_id)
        add_claim(canonical_source.pk, claim_kind="release_context",
                  scope_key=f"github_named_product:{repo['id']}",
                  assertion_text=f"The source names {name} as a released project; publisher control remains unresolved",
                  source_excerpt=post_source.post.text, source_locator=f"https://github.com/{repo['full_name']}",
                  reported_product_id=product.pk, extraction_version="github-named-product-v1")
        return product
