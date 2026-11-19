"""Source-only helpers for a separately authorized saved-evidence import.

The preview command does not call these functions. They never create staff
eligibility or trigger profile-derived affiliation and movement candidates.
"""

from django.utils import timezone

from core.profile_snapshots import (
    ProfileHistoryConflict,
    ProfileSourceConflict,
    record_profile_snapshot,
)


def record_saved_profile_snapshot(
    *, account, observation, observed_at, source_post=None
):
    """Record a dated observation or return the unchanged evidence on hold."""
    if observed_at is None:
        return {
            "action": "hold",
            "reason": "missing_observation_time",
            "observation": observation,
        }
    if not observation.present_fields:
        return {
            "action": "hold",
            "reason": "no_profile_fields",
            "observation": observation,
            "observed_at": observed_at,
        }
    if timezone.is_naive(observed_at):
        raise ValueError("Profile observation time must have a timezone")
    if source_post is not None and source_post.author_id != account.pk:
        return {
            "action": "hold",
            "reason": "profile_source_account_mismatch",
            "observation": observation,
            "observed_at": observed_at,
            "source_post_id": source_post.pk,
        }
    try:
        snapshot, created, changed = record_profile_snapshot(
            account=account,
            observation=observation,
            observed_at=observed_at,
            source_kind="saved_bio",
            source_post=source_post,
            reject_ambiguous_history=True,
            preserve_source_provenance=True,
        )
    except ProfileHistoryConflict as exc:
        return {
            "action": "hold",
            "reason": "unrepresented_profile_source"
            if isinstance(exc, ProfileSourceConflict)
            else "ambiguous_profile_interval",
            "observation": exc.observation,
            "observed_at": exc.observed_at,
            "source_post_id": source_post.pk if source_post else None,
        }
    return {
        "action": "create" if created else "reuse",
        "snapshot_id": snapshot.pk,
        "changed": changed,
    }
