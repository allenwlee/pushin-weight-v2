"""Immutable, readable measurement and attribution correction history."""

import uuid
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_timing import TIME_FIELDS
from core.measurement_taxonomy import digest, require
from core.models import Actor, CollectionCorrection, CollectionObservation

TIME_STATE_FIELDS = (*TIME_FIELDS, "temporal_status", "source_timezone")
TIME_BASIS_FIELDS = (
    "as_of_basis",
    "window_start_basis",
    "window_end_basis",
    "as_of_unknown_reason",
    "window_start_unknown_reason",
    "window_end_unknown_reason",
    "reported_time_policy",
    "provenance_precision",
)


def _registered_actor(actor_identity):
    if actor_identity is not None:
        require(
            isinstance(actor_identity, Actor) and not actor_identity._state.adding,
            "existing registered actor required",
        )
    return actor_identity


def correction_head(observation, *, metric_value=None, kind):
    history = CollectionCorrection.objects.filter(
        observation=observation,
        metric_value=metric_value,
        correction_kind=kind,
    )
    predecessors = history.exclude(predecessor_id=None).values("predecessor_id")
    heads = list(history.exclude(pk__in=predecessors)[:2])
    require(len(heads) <= 1, "ambiguous correction history")
    return heads[0] if heads else None


@transaction.atomic
def record_timing_correction(
    value,
    *,
    before,
    after,
    policy,
    reason,
    actor=None,
    actor_identity=None,
    recorded_at=None,
):
    actor_identity = _registered_actor(actor_identity)
    if actor is None:
        if actor_identity is None:
            # This fixed system performer is explicit registration, never
            # inferred from a caller's legacy text or an operator name.
            actor_identity, _ = Actor.objects.get_or_create(
                actor_kind=Actor.Kind.SYSTEM,
                actor_key="benchmark_metric_timing_repair",
                defaults={
                    "id": uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        "pushinweight:actor:system:benchmark_metric_timing_repair",
                    )
                },
            )
        actor = f"{actor_identity.actor_kind}:{actor_identity.actor_key}"
    require(isinstance(actor, str) and actor.strip(), "correction actor required")
    observation = CollectionObservation.objects.select_for_update().get(
        pk=value.observation_id
    )
    predecessor = correction_head(observation, metric_value=value, kind="timing")
    fields = {
        f"{side}_{name}": state.get(name)
        for side, state in (("before", before), ("after", after))
        for name in (*TIME_STATE_FIELDS, *TIME_BASIS_FIELDS)
    }
    serialized = {
        key: item.isoformat() if isinstance(item, (date, datetime)) else item
        for key, item in fields.items()
    }
    key = digest(
        {
            "value": value.pk,
            "predecessor": str(predecessor.pk) if predecessor else None,
            "policy": policy,
            "reason": reason,
            "fields": serialized,
        }
    )
    return CollectionCorrection.objects.create(
        id=uuid.uuid5(uuid.NAMESPACE_URL, "pushinweight:timing-correction:" + key),
        observation=observation,
        metric_value=value,
        predecessor=predecessor,
        correction_kind="timing",
        policy_version=policy,
        actor_identifier=actor,
        actor=actor_identity,
        reason_code=reason,
        recorded_at=recorded_at or timezone.now(),
        recorded_at_precision="instant",
        **fields,
    )


@transaction.atomic
def correct_attribution(
    observation,
    *,
    product,
    mapping,
    actor,
    reason,
    policy="reviewed-attribution-v1",
    actor_identity=None,
):
    """Change the current view while retaining original contract-pinned admission."""
    from core.collection_identity import qualified_catalog_ownership

    observation = CollectionObservation.objects.select_for_update().get(
        pk=observation.pk
    )
    require(actor and reason, "correction actor and reason required")
    actor_identity = _registered_actor(actor_identity)
    if mapping is not None:
        require(
            product is not None
            and mapping.subject.subject_kind == "product"
            and mapping.subject.product_id == product.product_key,
            "correction mapping/product mismatch",
        )
        require(
            mapping.source_id == observation.run.job.source_id
            and mapping.publisher_account_id
            and qualified_catalog_ownership(mapping.publisher_account, mapping.subject),
            "correction requires qualified source mapping",
        )
    predecessor = correction_head(observation, kind="attribution")
    return CollectionCorrection.objects.create(
        observation=observation,
        predecessor=predecessor,
        correction_kind="attribution",
        policy_version=policy,
        actor_identifier=actor,
        actor=actor_identity,
        reason_code=reason,
        recorded_at=timezone.now(),
        recorded_at_precision="instant",
        before_product_id=predecessor.after_product_id
        if predecessor
        else observation.product_id,
        before_mapping_id=predecessor.after_mapping_id
        if predecessor
        else observation.mapping_id,
        after_product=product,
        after_mapping=mapping,
    )


def attribution_at(observation, *, known_at=None):
    """Return current or historical attribution without mutating source identity."""
    history = getattr(observation, "attribution_history", None)
    if history is None:
        history = list(observation.corrections.filter(correction_kind="attribution"))
    if known_at is not None:
        from core.benchmark_metric_timing import aware_instant

        known_at = aware_instant(known_at)
        if any(row.recorded_at is None for row in history):
            return {
                "product_id": None,
                "mapping_id": None,
                "correction_id": None,
                "assignment_complete": False,
                "uncertainty_reason": "correction_time_unknown",
            }
        history = [row for row in history if row.recorded_at <= known_at]
    predecessors = {row.predecessor_id for row in history}
    heads = [row for row in history if row.pk not in predecessors]
    require(len(heads) <= 1, "ambiguous correction history")
    correction = heads[0] if heads else None
    return {
        "product_id": correction.after_product_id
        if correction
        else observation.product_id,
        "mapping_id": correction.after_mapping_id
        if correction
        else observation.mapping_id,
        "correction_id": correction.pk if correction else None,
        "assignment_complete": True,
        "uncertainty_reason": None,
    }
