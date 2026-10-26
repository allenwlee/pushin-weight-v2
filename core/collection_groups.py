"""Resource activity outcomes in existing collection scopes."""

from django.db import transaction

from core.models import CollectionObservation, CollectionRun, CollectionScopeRun

GROUP_SCOPE_KIND = "resource_group"


def validate_group_outcomes(groups):
    if type(groups) is not dict or any(
        type(group) is not str or not 0 < len(group) <= 32
        or type(outcome) is not str or not 0 < len(outcome) <= 64
        for group, outcome in groups.items()
    ):
        raise ValueError("invalid resource group outcomes")


def observation_group_outcomes(observation):
    """Typed outcomes win; retain additive-rollout fallback for uncopied groups."""
    validate_group_outcomes(observation.groups)
    groups = dict(observation.groups)
    for scope in observation.resource_scopes.all():
        if scope.scope_kind != GROUP_SCOPE_KIND:
            continue
        if (
            scope.run_id != observation.run_id
            or scope.parent_scope_id != observation.scope_run_id
            or scope.scope_key != f"{observation.pk}:{scope.phase}"
        ):
            raise ValueError("resource group ownership mismatch")
        groups[scope.phase] = scope.outcome
    validate_group_outcomes(groups)
    return groups


def group_scope_values(observation, group, outcome):
    validate_group_outcomes({group: outcome})
    # A saved result does not establish a request, clock or complete expansion.
    execution, coverage = "unknown", "unknown"
    if outcome in {"pending", "running"}:
        execution, coverage = outcome, "pending"
    elif outcome == "ok":
        execution, coverage = "completed", "complete"
    elif outcome == "partial_expansion":
        execution, coverage = "completed", "partial"
    elif outcome in {"request_cap", "time_cap", "response_size_cap"}:
        execution, coverage = "yielded", "partial"
    return {
        "resource_observation_id": observation.pk,
        "parent_scope_id": observation.scope_run_id,
        "phase": group,
        "outcome": outcome,
        "execution_state": execution,
        "coverage_state": coverage,
        "enumeration_complete": outcome == "ok",
    }


@transaction.atomic
def record_observation_group(observation, group, outcome):
    """Update the active outcome; captured response history remains separate."""
    values = group_scope_values(observation, group, outcome)
    CollectionRun.objects.select_for_update().only("pk").get(pk=observation.run_id)
    owner = CollectionObservation.objects.select_for_update().only(
        "run_id", "scope_run_id",
    ).get(pk=observation.pk)
    if (owner.run_id, owner.scope_run_id) != (observation.run_id, observation.scope_run_id):
        raise ValueError("resource group owner changed")
    scope, created = CollectionScopeRun.objects.get_or_create(
        run_id=observation.run_id, scope_kind=GROUP_SCOPE_KIND,
        scope_key=f"{observation.pk}:{group}",
        defaults={"ownership": {}, **values},
    )
    if not created:
        if (
            scope.resource_observation_id != observation.pk
            or scope.parent_scope_id != observation.scope_run_id
            or scope.phase != group
        ):
            raise ValueError("resource group ownership mismatch")
        if any(getattr(scope, field) != value for field, value in values.items()):
            for field, value in values.items():
                setattr(scope, field, value)
            scope.save(update_fields=list(values))
    if hasattr(observation, "_prefetched_objects_cache"):
        observation._prefetched_objects_cache.pop("resource_scopes", None)
    # Temporary dual write while older binaries/archives still consume groups.
    observation.groups[group] = outcome
    return scope
