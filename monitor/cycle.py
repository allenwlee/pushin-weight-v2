"""Cycle orchestrator for x-monitor v2 Django migration (U6 + U1/U2).

Reuses x_monitor pipeline modules (query_plan, apify, attribution,
translator, reattribute) for the fetch / attribute / persist / translate /
classify steps.  Persists results via Django ORM instead of
x_monitor.store.Store.

The cycle flow:
  1. Load primary keywords from BrandKeyword (Django ORM)
  2. Plan calls via x_monitor.query_plan.plan_calls()
  3. For each call: fetch tweets via TwitterApiClient
  4. Attribute to brands via x_monitor.attribution.attribute_to_brands
  5. Persist via Django ORM (Post, Account, PostBrand, PostBrandMention,
     PostBrandSignal)
  6. Translate via x_monitor.translator.translate_batch_pragmatics (U1)
  7. Classify via x_monitor.attribution.classify_batch_pragmatics_full (U1)
  8. Quote-tweet channel (official every cycle + non-official daily)
  9. Emit run summary in LATEST.json compatible shape

LLM guardrails (U2):
  - Pause between classifier batches via X_MONITOR_LLM_PAUSE_SECONDS
  - Hard cap via _max_llm_calls (None = no cap, used by backfill command)

Key constraint (KTD2): The legacy x_monitor/run.py and macOS launchd
agents MUST remain untouched. This is a NEW entry point.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import Case, F, Q, Value, When
from django.utils import timezone as django_timezone

from core.models import (
    Account,
    Brand,
    BrandKeyword,
    BrandSearchTerm,
    CallState,
    HarvestBacklogWindow,
    Post,
    PostBrand,
    PostBrandMention,
    PostBrandSignal,
    PostEnrichmentState,
    PostTypeKey,
    SentimentKey,
)
from monitor.backlog import finish_claim, return_claim, transfer_truncated_coverage
from monitor.harvest_summary import summarize_latency
from monitor.list_membership import (
    observe_call_a_authors,
    resolve_call_a_author_contexts,
    run_due_reconciliation,
)
from monitor.post_enrichment import (
    CANONICAL_LANG_CODES as _CANONICAL_LANG_CODES,
)
from monitor.post_enrichment import (
    ENRICHMENT_COUNT_KEYS,
    enrichment_stage_outcome,
    persisted_output_complete_q,
    post_persisted_output_complete,
)
from monitor.post_enrichment import (
    commentary_is_distinct as _commentary_is_distinct,
)
from monitor.post_enrichment import (
    persisted_output_complete as _translation_output_complete,
)
from monitor.post_enrichment import (
    present_text as _present_text,
)

# x_monitor imports — reuse existing pipeline modules.
# These have no import-time side effects; they don't touch Store or
# read config.yaml at module level.
from x_monitor.apify import (
    TwitterApiAuthError,
    TwitterApiClient,
    TwitterApiRateLimitError,
    TwitterApiServerError,
)
from x_monitor.attribution import (
    UNATTRIBUTED_BRAND_ID,
    MentionRow,
    attribute_to_brands,
    compile_keyword_index,
)
from x_monitor.config import Config, CycleConfig, load_config
from x_monitor.harvest_policy import HarvestPolicy
from x_monitor.queries import X_LENGTH_CAP, assert_under_length_cap
from x_monitor.query_plan import PlannedCall, XQuerySpec, plan_calls
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Brand alias map (mirrors x_monitor/run.py:_BRAND_ALIASES)
# ---------------------------------------------------------------------------

_BRAND_ALIASES: dict[str, str] = {
    "kimi": "moonshot_kimi",
    "k2": "moonshot_kimi",
    "月之暗面": "moonshot_kimi",
    "暗面": "moonshot_kimi",
    "mimo": "mimo",
    "xiaomi": "mimo",
    "ling": "inclusionai",
    "ring": "inclusionai",
    "ming": "inclusionai",
    "chatglm": "glm",
    "智谱": "glm",
    "通义千问": "qwen",
    "通义": "qwen",
    "深度求索": "deepseek",
    "海螺": "minimax",
    "hailuo": "minimax",
}


# ============================================================================
# Helpers
# ============================================================================


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _requeue_recent_incomplete_translations(
    *, cfg: Any, now: datetime | None = None
) -> int:
    """Reopen recent false successes without resurrecting historical debt."""
    now = now or django_timezone.now()
    age_cutoff = now - timedelta(hours=cfg.max_age_hours)
    return PostEnrichmentState.objects.filter(
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        created_at__gt=age_cutoff,
    ).exclude(persisted_output_complete_q(prefix="post__")).update(
        translation_status=PostEnrichmentState.Status.PENDING,
        translation_next_attempt_at=now,
        translation_error_code="translation_output_incomplete",
    )


@dataclass(frozen=True)
class EnrichmentClaimBatch:
    current_cycle_states: tuple[PostEnrichmentState, ...] = ()
    carryover_states: tuple[PostEnrichmentState, ...] = ()
    quarantined: int = 0

    @property
    def states(self) -> tuple[PostEnrichmentState, ...]:
        return self.carryover_states + self.current_cycle_states

    @property
    def current_cycle_post_ids(self) -> tuple[str, ...]:
        return tuple(str(state.pk) for state in self.current_cycle_states)

    @property
    def carryover_post_ids(self) -> tuple[str, ...]:
        return tuple(str(state.pk) for state in self.carryover_states)


def _claim_enrichment_states(
    *,
    cfg: Any,
    run_id: str,
    now: datetime | None = None,
    prefer_created_before: datetime | None = None,
) -> EnrichmentClaimBatch:
    """Quarantine exhausted debt, then claim one atomic two-lane batch.

    Active leases are excluded, expired leases are recoverable, and attempt/
    age exhaustion becomes an explicit failed state instead of an immortal
    pending row. Aged rows are transitioned outside the claim budget so they
    cannot consume slots before live work reaches the classifier.
    ``skip_locked`` lets a second writer avoid rows currently owned by another
    transaction even though the outer writer lock normally serializes
    production entrypoints. A cutoff creates disjoint carryover (older than
    cutoff) and current-cycle (at or after cutoff) allocations that never
    borrow from one another. Omitting the cutoff preserves the legacy bounded
    backlog/backfill claim.
    """

    now = now or django_timezone.now()
    age_cutoff = now - timedelta(hours=cfg.max_age_hours)
    due = (
        Q(translation_status=PostEnrichmentState.Status.PENDING)
        | Q(classification_status=PostEnrichmentState.Status.PENDING)
    ) & (Q(claim_expires_at__isnull=True) | Q(claim_expires_at__lte=now))
    current_cycle: list[PostEnrichmentState] = []
    carryover: list[PostEnrichmentState] = []

    with transaction.atomic():
        expired_due = due & Q(created_at__lte=age_cutoff)
        quarantined = PostEnrichmentState.objects.filter(expired_due).update(
            translation_status=Case(
                When(
                    translation_status=PostEnrichmentState.Status.PENDING,
                    then=Value(PostEnrichmentState.Status.FAILED),
                ),
                default=F("translation_status"),
            ),
            translation_error_code=Case(
                When(
                    translation_status=PostEnrichmentState.Status.PENDING,
                    then=Value("age_exhausted"),
                ),
                default=F("translation_error_code"),
            ),
            classification_status=Case(
                When(
                    classification_status=PostEnrichmentState.Status.PENDING,
                    then=Value(PostEnrichmentState.Status.FAILED),
                ),
                default=F("classification_status"),
            ),
            classification_error_code=Case(
                When(
                    classification_status=PostEnrichmentState.Status.PENDING,
                    then=Value("age_exhausted"),
                ),
                default=F("classification_error_code"),
            ),
            claim_owner="",
            claim_run_id="",
            claimed_at=None,
            claim_expires_at=None,
        )

        # Transition attempt-exhausted stages before either bounded lane is
        # sliced. Otherwise terminal debt can consume a claim slot and starve
        # eligible work at the edge of the cap.
        attempt_exhausted = due & Q(created_at__gt=age_cutoff) & (
            Q(
                translation_status=PostEnrichmentState.Status.PENDING,
                translation_attempts__gte=cfg.max_attempts,
            )
            | Q(
                classification_status=PostEnrichmentState.Status.PENDING,
                classification_attempts__gte=cfg.max_attempts,
            )
        )
        attempt_exhausted_ids = tuple(
            str(post_id)
            for post_id in PostEnrichmentState.objects.filter(
                attempt_exhausted
            ).values_list("post_id", flat=True)
        )
        if attempt_exhausted_ids:
            PostEnrichmentState.objects.filter(
                post_id__in=attempt_exhausted_ids
            ).update(
                translation_status=Case(
                    When(
                        translation_status=PostEnrichmentState.Status.PENDING,
                        translation_attempts__gte=cfg.max_attempts,
                        then=Value(PostEnrichmentState.Status.FAILED),
                    ),
                    default=F("translation_status"),
                ),
                translation_error_code=Case(
                    When(
                        translation_status=PostEnrichmentState.Status.PENDING,
                        translation_attempts__gte=cfg.max_attempts,
                        then=Value("attempts_exhausted"),
                    ),
                    default=F("translation_error_code"),
                ),
                classification_status=Case(
                    When(
                        classification_status=PostEnrichmentState.Status.PENDING,
                        classification_attempts__gte=cfg.max_attempts,
                        then=Value(PostEnrichmentState.Status.FAILED),
                    ),
                    default=F("classification_status"),
                ),
                classification_error_code=Case(
                    When(
                        classification_status=PostEnrichmentState.Status.PENDING,
                        classification_attempts__gte=cfg.max_attempts,
                        then=Value("attempts_exhausted"),
                    ),
                    default=F("classification_error_code"),
                ),
            )

            terminal_attempt_ids = tuple(
                str(post_id)
                for post_id in PostEnrichmentState.objects.filter(
                    post_id__in=attempt_exhausted_ids
                )
                .exclude(
                    Q(translation_status=PostEnrichmentState.Status.PENDING)
                    | Q(classification_status=PostEnrichmentState.Status.PENDING)
                )
                .values_list("post_id", flat=True)
            )
            if terminal_attempt_ids:
                quarantined += len(terminal_attempt_ids)
                PostEnrichmentState.objects.filter(
                    post_id__in=terminal_attempt_ids
                ).update(
                    claim_owner="",
                    claim_run_id="",
                    claimed_at=None,
                    claim_expires_at=None,
                )

        eligible_qs = (
            PostEnrichmentState.objects.select_for_update(skip_locked=True)
            .select_related("post")
            .filter(due, created_at__gt=age_cutoff)
            .annotate(
                _retry_priority=Case(
                    When(
                        Q(
                            translation_status=PostEnrichmentState.Status.PENDING,
                            translation_attempts__gt=0,
                        )
                        | Q(
                            classification_status=PostEnrichmentState.Status.PENDING,
                            classification_attempts__gt=0,
                        ),
                        then=Value(0),
                    ),
                    default=Value(1),
                )
            )
            .order_by("-created_at", "_retry_priority", "post_id")
        )

        if prefer_created_before is None:
            legacy_cap = min(
                cfg.claim_per_cycle,
                cfg.carryover_claim_per_cycle,
            )
            carryover = list(eligible_qs[:legacy_cap])
        else:
            carryover = list(
                eligible_qs.filter(created_at__lt=prefer_created_before)[
                    : cfg.carryover_claim_per_cycle
                ]
            )
            aggregate_remainder = max(cfg.claim_per_cycle - len(carryover), 0)
            current_cap = min(
                cfg.current_cycle_claim_per_cycle,
                aggregate_remainder,
            )
            current_cycle = list(
                eligible_qs.filter(created_at__gte=prefer_created_before)[:current_cap]
            )

        candidates = [*carryover, *current_cycle]
        for state in candidates:
            state.claim_owner = f"harvester:{run_id}"[:128]
            state.claim_run_id = str(run_id)[:128]
            state.claimed_at = now
            state.claim_expires_at = now + timedelta(seconds=cfg.claim_ttl_seconds)
            for prefix in ("translation", "classification"):
                if (
                    getattr(state, f"{prefix}_status")
                    != PostEnrichmentState.Status.PENDING
                ):
                    continue
                attempts_name = f"{prefix}_attempts"
                first_name = f"{prefix}_first_attempt_at"
                setattr(state, attempts_name, getattr(state, attempts_name) + 1)
                if getattr(state, first_name) is None:
                    setattr(state, first_name, now)
                setattr(state, f"{prefix}_last_attempt_at", now)
            state.save()

    return EnrichmentClaimBatch(
        current_cycle_states=tuple(current_cycle),
        carryover_states=tuple(carryover),
        quarantined=quarantined,
    )


def _release_enrichment_claim(post_id: str, *, run_id: str) -> bool:
    return bool(
        PostEnrichmentState.objects.filter(
            post_id=post_id,
            claim_run_id=str(run_id)[:128],
        ).update(
            claim_owner="",
            claim_run_id="",
            claimed_at=None,
            claim_expires_at=None,
        )
    )


def _finish_enrichment_stage(
    *,
    post_ids: list[str],
    run_id: str,
    stage: str,
    succeeded_ids: set[str],
    error_code: str,
    cfg: Any,
    now: datetime | None = None,
) -> int:
    """Resolve one claimed stage and return new terminal failures."""

    if stage not in {"translation", "classification"}:
        raise ValueError(f"unknown enrichment stage: {stage}")
    now = now or django_timezone.now()
    age_cutoff = now - timedelta(hours=cfg.max_age_hours)
    failed = 0
    with transaction.atomic():
        states = list(
            PostEnrichmentState.objects.select_for_update()
            .filter(post_id__in=post_ids, claim_run_id=str(run_id)[:128])
            .order_by("post_id")
        )
        for state in states:
            status_name = f"{stage}_status"
            if getattr(state, status_name) != PostEnrichmentState.Status.PENDING:
                continue
            next_name = f"{stage}_next_attempt_at"
            error_name = f"{stage}_error_code"
            if str(state.post_id) in succeeded_ids:
                setattr(state, status_name, PostEnrichmentState.Status.SUCCEEDED)
                setattr(state, next_name, None)
                setattr(state, error_name, "")
            else:
                exhausted = getattr(state, f"{stage}_attempts") >= cfg.max_attempts
                aged = state.created_at <= age_cutoff
                if exhausted or aged:
                    setattr(state, status_name, PostEnrichmentState.Status.FAILED)
                    setattr(
                        state,
                        error_name,
                        "age_exhausted" if aged else "attempts_exhausted",
                    )
                    setattr(state, next_name, None)
                    failed += 1
                else:
                    setattr(state, next_name, now)
                    setattr(state, error_name, str(error_code or "stage_failed")[:128])
            state.save(update_fields=[status_name, next_name, error_name, "updated_at"])
    return failed


# ============================================================================
# Incremental harvest cursor (plan 2026-07-27-002, U1)
# ============================================================================
#
# v1 (x_monitor/run.py) swept a time window per call: it read
# call_state.last_completed_at, derived a `since_time` floor from it, fetched
# everything in that window, then advanced the cursor.  v2 shipped without
# this, so every 15-minute cycle re-requested the newest <=100 posts per query
# with no time bounds -- cycles overlapped heavily and anything that scrolled
# past that slice between cycles was lost.  That was ~half of daily volume.
#
# These helpers restore the cursor.  Two deliberate differences from v1:
#   * the first window is CLAMPED (see cfg.cycle.max_lookback) so a stale cursor cannot
#     request a multi-day sweep that would silently truncate against the
#     per-call page cap;
#   * the value written is the same instant passed as `until_time`, so
#     consecutive windows chain exactly (v1 never bounded the upper end and
#     leaned on the overlap to absorb the difference).

# Boundary overlap re-requested on each cycle so a post written in the same
# second as the previous cursor cannot fall between two windows.  Mirrors v1's
# CURSOR_OVERLAP_HOURS (x_monitor/run.py:67).  Duplicates are discarded by
# tweet_id dedup, so overlap is cheap; a gap is not recoverable.





# CallState.bucket is TextField(blank=True, default=""), but every v2
# PlannedCall carries bucket=None.  Normalize on both read and write so the
# two never address different rows.  Mirrors v1's _NULL_BUCKET_SENTINEL
# (x_monitor/store.py:455-459).
_NULL_BUCKET_SENTINEL = ""
_DEFAULT_CYCLE_CONFIG = CycleConfig()




def _matches_any_term(text: str, quoted_text: str, terms: list[str]) -> bool:
    """Return True if any term appears in text or quoted_text (case-insensitive).

    Used by the U5 post-fetch ban match in CycleRunner.run(). terms
    must already be lowercased. Empty terms list → no match.
    """
    if not terms:
        return False
    haystack = ((text or "") + "\n" + (quoted_text or "")).lower()
    return any(term in haystack for term in terms if term)


def _apply_relevancy_gate(
    items: list[dict[str, Any]],
    *,
    call_id: str,
    llm_call,
) -> list[dict[str, Any]]:
    """Apply the U6 binary LLM relevancy gate to items.

    Per-item brand_id (set by _attribute_items) drives the gate via
    x_monitor.relevancy.should_apply_binary_gate. Drop decisions are
    returned; KEEP/uncertain items pass through. When llm_call is
    None the gate is a no-op (the constructor's default).
    """
    if llm_call is None:
        return items
    # Lazy import — x_monitor.relevancy is a thin module without
    # Django dependencies, but we keep the import deferred so the
    # cycle module can be imported in environments where the relevancy
    # gate is intentionally disabled.
    from x_monitor.relevancy import (
        call_binary_relevancy_llm,
        should_apply_binary_gate,
    )

    out: list[dict[str, Any]] = []
    for it in items:
        brand_hints = it.get("brand_id") or ""
        if not should_apply_binary_gate(
            call_id=call_id, brand_hints=brand_hints
        ):
            out.append(it)
            continue
        text = it.get("text") or ""
        verdict = call_binary_relevancy_llm(
            post_text=text,
            call_id=call_id,
            brand_hints=brand_hints,
            llm_call=llm_call,
        )
        if verdict.decision == "DROP":
            continue  # drop
        out.append(it)
    return out


def _item_created_epoch(it: dict[str, Any]) -> int | None:
    """Best-effort unix epoch for a normalized tweet dict (for window walks)."""
    raw_ep = it.get("created_at_epoch") or it.get("createdAtEpoch")
    if raw_ep is not None:
        try:
            return int(raw_ep)
        except (TypeError, ValueError):
            pass
    created_at_str = it.get("created_at") or it.get("createdAt") or ""
    if not created_at_str:
        return None
    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            parsed = datetime.strptime(created_at_str, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp())
        except (ValueError, TypeError):
            continue
    try:
        parsed = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except (ValueError, TypeError):
        return None


def _cursor_key(call: PlannedCall) -> dict[str, str]:
    """Build the call_state identity tuple for one planned call.

    Note that `brand_id` here is the *planner's placeholder*, not a real
    brand: "*" for the list-based Call A, and the first brand in iteration
    order for the B/C specs (x_monitor/query_plan.py:351, 370-379).
    Disambiguation between the seven rows is owned by `call_id`.  Never
    re-derive brand_id from post-attribution -- that would collapse several
    B/C specs onto one cursor row.

    `query_id` follows v1's convention of carrying the planner's call_id
    (x_monitor/run.py:199-203).
    """
    return {
        "brand_id": call.brand_id,
        "call_id": call.call_id,
        "call_kind": call.call_kind,
        "bucket": call.bucket or _NULL_BUCKET_SENTINEL,
        "query_id": call.call_id,
    }


def _read_cursor_since(
    call: PlannedCall, *, now: datetime, cfg: Config | None = None
) -> datetime:
    """Resolve the `since_time` floor for one call, clamped to cfg.cycle.max_lookback.

    Returns an aware UTC datetime, always.  Four cases:
      * no cursor row (cold start)  -> now - cfg.cycle.max_lookback
      * fresh cursor                -> cursor - cfg.cycle.cursor_overlap
      * stale cursor (or DB error)  -> now - cfg.cycle.max_lookback (the clamp)
      * future cursor (NTP rollback, a v1 legacy row whose TZ was
        mis-parsed, a manual psql write) -> now - cfg.cycle.cursor_overlap

    The future case is the subtle one: a prior AFTER now would otherwise
    produce since > until, TwitterAPI.io returns [] with no error, and the
    successful-empty-sweep advance rewinds the cursor to now -- permanently
    losing the (now, prior) span. Clamping since to (now - overlap) bounds
    the damage to a one-cycle re-fetch, which dedup absorbs.
    """
    cycle_cfg = cfg.cycle if cfg is not None else _DEFAULT_CYCLE_CONFIG
    floor = now - timedelta(hours=cycle_cfg.max_lookback_hours)
    ceiling = now - timedelta(seconds=cycle_cfg.cursor_overlap_seconds)
    try:
        row = CallState.objects.filter(**_cursor_key(call)).first()
        if row is None or row.last_completed_at is None:
            return floor
        prior = row.last_completed_at
        # Defensive: a naive value (USE_TZ flipped, a raw SQL insert, or a
        # value carried over from v1's ISO-string storage) would make the
        # comparison below raise TypeError. The per-call loop has no
        # try/except, so that would abort the WHOLE cycle -- all seven calls --
        # rather than degrade one. Coerce to UTC instead.
        if prior.tzinfo is None:
            logger.warning(
                "_read_cursor_since: naive last_completed_at for call_id=%s; "
                "assuming UTC",
                call.call_id,
            )
            prior = prior.replace(tzinfo=timezone.utc)
        # A prior in the FUTURE would invert the window (since > until),
        # make TwitterAPI.io return [] with no error, and the empty-sweep
        # advance would rewind the cursor to now -- permanently losing the
        # (now, prior) span. Clamp the lower bound to (now - overlap) so the
        # damage is bounded to a single re-fetch that dedup absorbs.
        if prior > now:
            logger.warning(
                "_read_cursor_since: future last_completed_at for call_id=%s "
                "(%s, ahead of now by %s); clamping to now - overlap. Likely "
                "causes: NTP rollback, v1 import with TZ mis-parse, or a "
                "manual DB write.",
                call.call_id,
                prior.isoformat(),
                prior - now,
            )
            return ceiling
        return max(prior - timedelta(seconds=cycle_cfg.cursor_overlap_seconds), floor)
    except Exception as exc:
        logger.warning(
            "_read_cursor_since: cursor read failed for call_id=%s: %s; "
            "falling back to clamped lookback",
            call.call_id,
            exc,
        )
        return floor


def _advance_cursor(
    call: PlannedCall, *, upper_bound: datetime, now: datetime | None = None
) -> bool:
    """Record that this call swept through `upper_bound`. Returns success.

    `upper_bound` must be the exact instant passed to the API as
    `until_time`, so the next cycle's window begins where this one ended.

    Refuses to persist a value in the future. A future stored cursor
    would invert the next window (since > until), TwitterAPI.io would
    return [] with no error, and the successful-empty-sweep advance would
    rewind the cursor to now -- permanently losing the (now, prior) span.
    Reachable on NTP rollback, a v1 legacy import with TZ mis-parse, or a
    manual psql write. The in-tree writer is the only one we control, so
    refuse here and let the read-side clamp handle anything external.

    `now` is injectable so tests with a fixed `NOW` constant do not become
    time-sensitive.

    A cursor-write failure must never abort the cycle -- the posts are
    already stored, and not advancing only costs a bounded re-fetch that
    dedup discards.  So this logs and reports False rather than raising.
    """
    if upper_bound.tzinfo is None:
        raise ValueError(
            "_advance_cursor requires an aware datetime; got a naive one "
            "(CallState.last_completed_at is TIMESTAMPTZ under USE_TZ=True)"
        )
    if upper_bound > (now or datetime.now(timezone.utc)):
        raise ValueError(
            f"_advance_cursor refuses a future upper_bound ({upper_bound}); "
            "would invert the next window and lose data. Investigate clock "
            "or call site before allowing it."
        )
    try:
        CallState.objects.update_or_create(
            **_cursor_key(call),
            defaults={"last_completed_at": upper_bound},
        )
        return True
    except Exception as exc:
        logger.warning(
            "_advance_cursor: failed to advance call_state for call_id=%s "
            "(kind=%s brand=%s): %s -- next cycle will re-sweep this window",
            call.call_id,
            call.call_kind,
            call.brand_id,
            exc,
        )
        return False


def _load_primary_keywords() -> dict[str, list[str]]:
    """Load {brand_id: [pattern, ...]} for is_primary=1 keywords from the DB.

    Mirrors Store.read_primary_brand_keywords() but via Django ORM.
    Returns empty dict on DB unavailability (safe for dry-run).
    """
    out: dict[str, list[str]] = {}
    try:
        for kw in BrandKeyword.objects.filter(is_primary=True).select_related("brand"):
            brand_id = kw.brand_id
            out.setdefault(brand_id, []).append(kw.pattern)
    except Exception as exc:
        logger.warning("_load_primary_keywords: DB read failed: %s", exc)
    return out


def _load_brand_search_terms() -> dict[str, str]:
    """Load {term: brand_id} map from brand_search_terms table.

    Mirrors Store.read_brand_search_terms() but via Django ORM.
    Returns empty dict on DB unavailability.
    """
    out: dict[str, str] = {}
    try:
        for st in BrandSearchTerm.objects.all():
            out[st.term.lower()] = st.brand_id
    except Exception as exc:
        logger.warning("_load_brand_search_terms: DB read failed: %s", exc)
    # Fold brand aliases into the map so CJK / short-form tokens resolve.
    for alias, brand_id in _BRAND_ALIASES.items():
        out.setdefault(alias.lower(), brand_id)
    return out


def _build_brand_index(
    models: list[str],
) -> Any:
    """Build the live body-attribution index from enabled DB keywords.

    ``BrandKeyword`` is the attribution source of truth. Search policy is
    loaded as the source of truth for what the cycle emits, then every active
    policy token must have a literal DB mapping before this index is returned.
    Do not synthesize nickname rows: that masks onboarding and schema drift.

    ``BrandSearchTerm`` is loaded separately by the caller only for query
    provenance; it is not a body-keyword fallback.
    """
    from collections import defaultdict

    from x_monitor.harvest_policy import load_policy
    from x_monitor.specs_from_policy import (
        active_policy_tokens,
        normalize_policy_token,
    )

    policy = load_policy(Path("config") / "harvest_policy.yaml")
    expected = active_policy_tokens(policy, brand_nicknames=models)

    try:
        rows = list(
            BrandKeyword.objects.filter(
                brand_id__in=models,
                brand__is_sentinel=False,
            ).values_list("brand_id", "pattern", "is_regex")
        )
    except DatabaseError as exc:
        logger.exception("_build_brand_index: BrandKeyword DB read failed")
        raise RuntimeError(
            "BrandKeyword DB read failed during attribution preflight"
        ) from exc

    literal_by_brand: dict[str, set[str]] = defaultdict(set)
    keyword_triples: list[tuple[str, str, bool]] = []
    for brand_id, pattern, is_regex in rows:
        compiled_pattern = (
            str(pattern) if is_regex else normalize_policy_token(pattern)
        )
        if not compiled_pattern:
            continue
        keyword_triples.append(
            (str(brand_id), compiled_pattern, bool(is_regex))
        )
        if not is_regex:
            literal_by_brand[brand_id].add(compiled_pattern)

    missing = sorted(
        (brand_id, token)
        for brand_id, tokens in expected.items()
        for token in tokens
        if token not in literal_by_brand.get(brand_id, set())
    )
    if missing:
        formatted = ", ".join(f"{brand}/{token}" for brand, token in missing)
        raise ValueError(
            "BrandKeyword coverage is incomplete for active policy tokens: "
            f"{formatted}"
        )

    return compile_keyword_index(keyword_triples)


def _resolve_enabled_models(cfg: Config, brand_filter: list[str] | None = None) -> list[str]:
    """Resolve the enabled model list for a cycle.

    Reads from Config.enabled_models (plan 2026-08-01-001 U2). When
    brand_filter is set (--brands CLI flag), restricts to that subset,
    intersected with the brands that exist in the DB.
    """
    base = list(cfg.enabled_models)
    if not brand_filter:
        return base
    existing = set(
        Brand.objects.filter(nickname__in=brand_filter).values_list(
            "nickname", flat=True
        )
    )
    return [b for b in brand_filter if b in existing]
def _resolve_x_monitor_list_id(cfg: Config) -> int | None:
    """Resolve the X list ID from Config.

    The Config schema's x_monitor_list_id is read from config.yaml directly.
    """
    list_id = cfg.x_monitor_list_id
    if list_id is None:
        return None
    try:
        return int(list_id)
    except (TypeError, ValueError):
        return None


def _resolve_x_query_specs(
    cfg: Config,
    *,
    policy: HarvestPolicy | None = None,
) -> list[XQuerySpec]:
    """Resolve per-cycle XQuerySpec list.

    The brand-centric harvest policy is the only live Django search source.
    Missing or invalid policy is a preflight error; checked-in
    ``cfg.x_query_specs`` remains available for explicitly injected local
    fixtures and legacy CLI consumers, but is never a production fallback.

    Returns:
        list[XQuerySpec] ready for plan_calls(). Already validated by
        the policy loader.
    """
    from x_monitor.harvest_policy import load_policy
    from x_monitor.specs_from_policy import (
        specs_from_policy,
        validate_derived_call_ids,
    )

    # Do not check exists() and silently select a second source. Let the
    # missing-file exception identify the failed live preflight explicitly.
    if policy is None:
        policy = load_policy(Path("config") / "harvest_policy.yaml")
    specs = validate_derived_call_ids(
        specs_from_policy(policy, brand_nicknames=cfg.enabled_models)
    )
    return list(specs)


def _upsert_account(raw: dict[str, Any]) -> Account | None:
    """Create or update an Account row from a normalized tweet dict.

    Returns the Account instance or None if the tweet has no author info.

    Dual-write (U3, R14): the Account table carries a denormalized snapshot of
    author fields that overlap with the new posts.author_* columns. Update
    Account here so downstream consumers that key off Account don't lose
    recency. Use the *correct* key names — the prior version referenced
    `author_followers` / `author_following` (without the `_count` suffix) and
    the normalize layer never set those, so the corresponding Account fields
    were silently never written.
    """
    author_id = str(raw.get("author_id") or raw.get("authorId") or "")
    if not author_id:
        return None
    candidates: dict[str, Any] = {}
    present: set[str] = set()
    field_keys = {
        "handle": ("author_handle", "authorHandle"),
        "display_name": ("author_display_name", "author_name", "authorName"),
        "verified": ("author_verified", "authorVerified"),
        "followers_count": ("author_followers_count",),
        "following_count": ("author_following_count",),
        "favourites_count": ("author_favourites_count",),
        "statuses_count": ("author_statuses_count",),
        "media_count": ("author_media_count",),
        "fast_followers_count": ("author_fast_followers_count",),
        "is_blue_verified": ("author_is_blue_verified",),
        "protected": ("author_protected",),
        "verified_type": ("author_verified_type",),
        "profile_picture": ("author_profile_picture",),
        "location": ("author_location",),
        "description": ("author_description",),
        "profile_bio_text": ("author_profile_bio_text",),
        "created_at": ("author_created_at_raw",),
    }
    for field_name, source_keys in field_keys.items():
        for source_key in source_keys:
            if source_key in raw and raw[source_key] is not None:
                candidates[field_name] = raw[source_key]
                present.add(field_name)
                break

    if "created_at" in candidates and isinstance(candidates["created_at"], str):
        parsed = None
        for fmt in (
            "%a %b %d %H:%M:%S %z %Y",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
        ):
            try:
                parsed = datetime.strptime(candidates["created_at"], fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        candidates["created_at"] = parsed or candidates["created_at"]

    if "author_affiliates_highlighted_label" in raw:
        from monitor.twitterapi.user_about import SchemaDriftError, flatten_label

        try:
            label_values, label_fields = flatten_label(
                raw["author_affiliates_highlighted_label"],
                prefix="affiliate_label",
                path="post.author_affiliates_highlighted_label",
            )
        except SchemaDriftError:
            label_fields = {
                "affiliate_label_badge_url",
                "affiliate_label_description",
                "affiliate_label_url",
                "affiliate_label_url_type",
                "affiliate_label_user_label_display_type",
                "affiliate_label_user_label_type",
            }
            label_values = {field: object() for field in label_fields}
        candidates.update(label_values)
        present.update(label_fields)

    outcome = Account.apply_observation(
        author_id=author_id,
        observed_author_id=author_id,
        source="post",
        observed_at=django_timezone.now(),
        candidates=candidates,
        present_fields=present,
    )
    if outcome.rejected_fields:
        logger.warning(
            "account post observation rejected fields=%s",
            sorted(outcome.rejected_fields),
        )
    return outcome.account


def _upsert_post(
    raw: dict[str, Any], account: Account | None = None
) -> tuple[Post | None, bool]:
    """Create or update a Post row from a normalized tweet dict.

    Returns ``(Post, created)`` or ``(None, False)`` when the tweet has no id.

    Posts.raw denormalization (U3): writes both the typed columns (per
    `docs/plans/2026-07-27-004-…`) AND the `raw` JSONField for one release
    cycle. The dual-write is removed in U4 once the harvest has had ≥1
    cycle on the new code. The `quoted_status_id` is gated by Policy A
    (only set if the parent tweet_id already exists in posts).
    """
    tweet_id = str(raw.get("id") or raw.get("tweet_id") or "")
    if not tweet_id:
        return None, False
    defaults: dict[str, Any] = {}
    if account is not None:
        defaults["author"] = account
    handle = raw.get("author_handle") or raw.get("authorHandle") or ""
    if handle:
        defaults["author_handle"] = handle
    text = raw.get("text") or ""
    if text:
        defaults["text"] = text
    lang = raw.get("lang") or ""
    if lang:
        defaults["lang"] = lang
    created_at_str = raw.get("created_at") or raw.get("createdAt") or ""
    if created_at_str:
        parsed = None
        for fmt in (
            "%a %b %d %H:%M:%S %z %Y",   # Twitter API: "Wed Jul 22 03:40:35 +0000 2026"
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
        ):
            try:
                parsed = datetime.strptime(created_at_str, fmt).replace(tzinfo=timezone.utc)
                break
            except (ValueError, TypeError):
                continue
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        if parsed:
            defaults["created_at"] = parsed
    like_count = raw.get("like_count") or raw.get("likeCount")
    if like_count is not None:
        defaults["like_count"] = int(like_count)
    retweet_count = raw.get("retweet_count") or raw.get("retweetCount")
    if retweet_count is not None:
        defaults["retweet_count"] = int(retweet_count)
    reply_count = raw.get("reply_count") or raw.get("replyCount")
    if reply_count is not None:
        defaults["reply_count"] = int(reply_count)
    quote_count = raw.get("quote_count") or raw.get("quoteCount")
    if quote_count is not None:
        defaults["quote_count"] = int(quote_count)
    in_reply_to = raw.get("in_reply_to_user_id") or raw.get("inReplyToUserId") or ""
    if in_reply_to:
        defaults["in_reply_to_user_id"] = str(in_reply_to)
    quoted_id = raw.get("quoted_status_id") or raw.get("quotedStatusId") or ""
    if quoted_id:
        # quoted_status_id is a FK to Post (self); must be a Post instance
        # or None. Look up the parent Post first; if it doesn't exist
        # (not yet harvested), leave the FK unset (NULL via
        # on_delete=SET_NULL).
        # The 2026-07-31 cycle run hit 8 persist failures because this
        # was passing the raw tweet-id string into a FK field.
        try:
            parent_post = Post.objects.filter(tweet_id=str(quoted_id)).only("tweet_id").first()
            if parent_post is not None:
                defaults["quoted_status_id"] = parent_post
            # else: leave FK unset; will be populated when parent is harvested
        except Exception:
            pass
    conversation_id = raw.get("conversation_id") or raw.get("conversationId") or ""
    if conversation_id:
        defaults["conversation_id"] = str(conversation_id)
    entities = raw.get("entities") or {}
    if entities:
        defaults["entities"] = entities
    source_qid = raw.get("source_query_id") or raw.get("sourceQueryId") or ""
    if source_qid:
        defaults["source_query_id"] = source_qid
    quoted_text = raw.get("quoted_text") or ""
    if quoted_text:
        defaults["quoted_text"] = quoted_text
    created_at_epoch = raw.get("created_at_epoch") or raw.get("createdAtEpoch")
    if created_at_epoch is not None:
        defaults["created_at_epoch"] = int(created_at_epoch)

    # --- § 1.2 New tweet top-level typed columns (U3).
    # Per § 1.7: new fields use NULL-when-absent, not 0/false coercion. The
    # `is not None` guard skips both missing keys AND None sentinels; the
    # normalize layer uses None for absent keys (not 0).
    account_count_columns = {
        "author_followers_count",
        "author_following_count",
        "author_media_count",
        "author_statuses_count",
        "author_favourites_count",
        "author_fast_followers_count",
    }
    account_boolean_columns = {"author_verified", "author_is_blue_verified"}
    for col, val in (
        ("created_at_raw", raw.get("created_at_raw")),
        ("bookmark_count", raw.get("bookmark_count")),
        ("is_reply", raw.get("is_reply")),
        ("is_retweet", raw.get("is_retweet")),
        ("is_quote", raw.get("is_quote")),
        ("in_reply_to_id", raw.get("in_reply_to_id")),
        ("in_reply_to_username", raw.get("in_reply_to_username")),
        ("tweet_type", raw.get("tweet_type")),
        ("tweet_url", raw.get("tweet_url")),
        ("tweet_twitter_url", raw.get("tweet_twitter_url")),
        ("card", raw.get("card")),
        ("place", raw.get("place")),
        ("client_source", raw.get("client_source")),
        ("view_count", raw.get("view_count")),
        ("article", raw.get("article")),
        ("is_limited_reply", raw.get("is_limited_reply")),
        ("community_info", raw.get("community_info")),
        ("display_text_range", raw.get("display_text_range")),
        ("extended_entities", raw.get("extended_entities")),
        ("quoted_author_handle", raw.get("quoted_author_handle")),
    ):
        if val is not None:
            defaults[col] = val

    # --- § 1.3 New author typed columns (U3).
    for col, val in (
        ("author_name", raw.get("author_name")),
        ("author_followers_count", raw.get("author_followers_count")),
        ("author_following_count", raw.get("author_following_count")),
        ("author_verified", raw.get("author_verified")),
        ("author_is_blue_verified", raw.get("author_is_blue_verified")),
        ("author_verified_type", raw.get("author_verified_type")),
        ("author_is_translator", raw.get("author_is_translator")),
        ("author_is_automated", raw.get("author_is_automated")),
        ("author_automated_by", raw.get("author_automated_by")),
        ("author_description", raw.get("author_description")),
        ("author_location", raw.get("author_location")),
        ("author_media_count", raw.get("author_media_count")),
        ("author_statuses_count", raw.get("author_statuses_count")),
        ("author_favourites_count", raw.get("author_favourites_count")),
        ("author_fast_followers_count", raw.get("author_fast_followers_count")),
        ("author_can_dm", raw.get("author_can_dm")),
        ("author_can_media_tag", raw.get("author_can_media_tag")),
        ("author_profile_picture", raw.get("author_profile_picture")),
        ("author_profile_bio", raw.get("author_profile_bio")),
        ("author_cover_picture", raw.get("author_cover_picture")),
        ("author_pinned_tweet_ids", raw.get("author_pinned_tweet_ids")),
        ("author_affiliates_highlighted_label",
         raw.get("author_affiliates_highlighted_label")),
        ("author_withheld_in_countries",
         raw.get("author_withheld_in_countries")),
        ("author_possibly_sensitive", raw.get("author_possibly_sensitive")),
        ("author_has_custom_timelines",
         raw.get("author_has_custom_timelines")),
        ("author_entities", raw.get("author_entities")),
        ("author_twitter_url", raw.get("author_twitter_url")),
        ("author_type", raw.get("author_type")),
        ("author_url", raw.get("author_url")),
        ("author_created_at_raw", raw.get("author_created_at_raw")),
        ("author_status", raw.get("author_status")),
    ):
        if col in account_count_columns and (
            type(val) is not int or val < 0 or val > 2_147_483_647
        ):
            continue
        if col in account_boolean_columns and type(val) is not bool:
            continue
        if val is not None:
            defaults[col] = val

    post, created = Post.objects.update_or_create(
        tweet_id=tweet_id, defaults=defaults
    )
    return post, created


def _persist_attribution(
    post: Post,
    brand_ids: list[str],
    mentions: list[MentionRow],
    classifications: dict[str, tuple[str, str]] | None = None,
) -> int:
    """Persist PostBrand, PostBrandMention, and PostBrandSignal rows.

    Idempotent: uses get_or_create for junction tables, update_or_create
    for signals.

    Returns the number of brands this post was attributed to.
    """
    n = 0
    seen_sources: set[tuple[str, str, str]] = set()  # (brand_id, source) for dedup
    for mention in mentions:
        if not mention.brand_id or mention.brand_id == UNATTRIBUTED_BRAND_ID:
            continue
        bid = mention.brand_id
        # PostBrand (junction)
        PostBrand.objects.get_or_create(
            post=post,
            brand_id=bid,
            defaults={"weight": 1.0},
        )
        # PostBrandMention (one per source per brand)
        source_key = (bid, mention.source or "body_keyword")
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            PostBrandMention.objects.get_or_create(
                post=post,
                brand_id=bid,
                source=mention.source or "body_keyword",
                defaults={"raw_token": mention.raw_token or ""},
            )
        if bid not in brand_ids:
            brand_ids.append(bid)
        n += 1

    # PostBrandSignal (per brand, per post_type)
    if classifications:
        for bid, (post_type, sentiment) in classifications.items():
            # Ensure the lookup keys exist
            pt_key, _ = PostTypeKey.objects.get_or_create(key=post_type)
            sent_key, _ = SentimentKey.objects.get_or_create(key=sentiment)
            PostBrandSignal.objects.update_or_create(
                post=post,
                brand_id=bid,
                post_type=pt_key,
                defaults={"sentiment": sent_key},
            )
    return len(set(brand_ids))


# ============================================================================
# CycleRunner
# ============================================================================


def plan_calls_for_cycle(cfg: Config | None = None) -> list[PlannedCall]:
    """Plan harvest calls from settings — shared by CycleRunner and backfill.

    Reads X_MONITOR_LIST_ID, brand filter, primary keywords, and
    x_query_specs from Django settings. Returns empty list when the
    list ID is not configured.

    The optional `cfg` parameter exists so production callers can pass
    the loaded Config (avoids a second disk read for callers that
    already loaded it). When `cfg is None`, the function falls back
    to load_config(Path("config.yaml")) — preserving backward
    compatibility with test monkeypatches that shim the function
    with zero-arg lambdas.
    """
    if cfg is None:
        cfg = load_config(Path("config.yaml"))

    list_id = _resolve_x_monitor_list_id(cfg)
    if list_id is None:
        logger.warning(
            "plan_calls_for_cycle: X_MONITOR_LIST_ID not set — "
            "Call A is list-based; without it no calls are planned."
        )
        return []

    from x_monitor.harvest_policy import load_policy
    from x_monitor.specs_from_policy import (
        primary_keywords_from_policy,
        specs_from_policy,
    )

    policy = load_policy(Path("config") / "harvest_policy.yaml")
    brand_filter_raw = getattr(settings, "X_MONITOR_CYCLE_BRAND_FILTER", None)
    brand_filter: list[str] = []
    if brand_filter_raw and isinstance(brand_filter_raw, str):
        brand_filter = [b.strip() for b in brand_filter_raw.split(",") if b.strip()]
    if brand_filter:
        # A historical backfill must narrow both the query contents and the
        # attribution index. Full scheduled runs retain the exact-call-set
        # validation in _resolve_x_query_specs; a deliberate brand subset is
        # allowed to emit only the paths that apply to that subset.
        x_query_specs = specs_from_policy(
            policy,
            brand_nicknames=brand_filter,
        )
        selected_models = brand_filter
        logger.info("plan_calls_for_cycle: brand filter active — %s", brand_filter)
    else:
        x_query_specs = _resolve_x_query_specs(cfg, policy=policy)
        selected_models = list(cfg.enabled_models)
    primary_keywords = primary_keywords_from_policy(
        policy,
        brand_nicknames=selected_models,
    )

    return plan_calls(
        list_id,
        x_query_specs,
        primary_keywords=primary_keywords,
    )


class CycleRunner:
    """Orchestrates one full harvest cycle.

    Usage:
        runner = CycleRunner(dry_run=True)
        stats = runner.run()
    """

    def __init__(
        self,
        *,
        cfg: Config | None = None,
        dry_run: bool = False,
        cycle_kind: str = "manual",
        _backfill_call_ids: list[str] | None = None,
        _max_llm_calls: int | None = None,
        _relevancy_llm_call=None,
        _clock=None,
        _monotonic=None,
    ) -> None:
        # Single config source-of-truth (plan 2026-08-01-001). When None,
        # load from config.yaml at the repo root. Tests pass a pre-built
        # Config to avoid disk I/O.
        if cfg is None:
            cfg = load_config(Path("config.yaml"))
        self.cfg = cfg
        self.dry_run = dry_run
        self.cycle_kind = cycle_kind  # 'scheduled' or 'manual'
        # If set, only execute these call IDs (all must be in the plan).
        # Used by the backfill command for batched, resumable execution.
        self._backfill_call_ids = _backfill_call_ids
        # Hard cap on LLM batches per invocation.  None = no cap.
        # Used by the backfill command to limit API spend on large windows.
        self._max_llm_calls = _max_llm_calls
        # U6 runtime wire-in: injected llm_call(system, user) -> str
        # dependency for the binary relevancy gate (R19a +
        # x_monitor/relevancy.py). Default None → gate is a no-op (KEEP).
        # Production wire-in passes an anthropic_messages_call function.
        self._relevancy_llm_call = _relevancy_llm_call
        # U14 keeps server-owned clocks injectable for deterministic latency
        # proof. Production defaults remain the wall/monotonic clocks.
        self._clock = _clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = _monotonic or time.monotonic
        self._llm_call_count: int = 0

        # Per-cycle accumulators for the run summary
        self._posts_seen: int = 0
        self._posts_inserted: int = 0
        self._posts_updated: int = 0
        self._posts_persist_failed: int = 0
        self._posts_attributed: int = 0
        self._api_calls: int = 0
        self._latency_observations: list[dict[str, Any]] = []
        self._errors: list[str] = []
        # Plan 2026-08-01-002 U4: typed counters surfaced via --json
        # n_errors_by_type. Each key represents a class of tolerated error
        # the cycle can recover from. The dashboard uses these to flag
        # silent-failure modes (e.g., "translator_batch_failed > 0 for 3
        # cycles in a row" = lang_detected regression in production).
        self._error_counts: dict[str, int] = {
            "translator_batch_failed": 0,
            "classifier_batch_failed": 0,
            "translator_unavailable": 0,
            "classifier_unavailable": 0,
            "classifier_flags_invalid": 0,
            "enrichment_quarantined": 0,
        }

    @property
    def twitterapi_credential_purpose(self) -> TwitterApiCredentialPurpose:
        """Resolve the credential lane without a permissive default."""

        if self.cycle_kind in {"scheduled", "manual"}:
            return TwitterApiCredentialPurpose.SCHEDULED
        if self.cycle_kind == "backfill":
            return TwitterApiCredentialPurpose.ON_DEMAND
        raise ValueError(f"unsupported cycle kind: {self.cycle_kind!r}")

    def _wall_now(self) -> datetime:
        """Return the server-owned wall clock used by U14 evidence."""

        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _now_iso(self) -> str:
        return self._wall_now().isoformat(timespec="seconds")

    def _record_latency_observations(self, items: list[dict[str, Any]]) -> None:
        for item in items:
            tweet_id = str(item.get("id") or item.get("tweet_id") or "")
            received = item.get("_api_received_at")
            committed = item.get("_db_committed_at")
            if tweet_id and received and committed:
                self._latency_observations.append(
                    {
                        "tweet_id": tweet_id,
                        "api_received_at": received,
                        "db_committed_at": committed,
                    }
                )

    @staticmethod
    def _page_receipt_timing(
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str | None, float | None]:
        seen: set[tuple[int, str]] = set()
        rows: list[dict[str, Any]] = []
        receipt_monos: list[float] = []
        for item in items:
            received = item.get("_api_received_at")
            page = item.get("_api_page_number")
            if not received or page is None:
                continue
            try:
                page_number = int(page)
            except (TypeError, ValueError):
                continue
            key = (page_number, str(received))
            if key in seen:
                continue
            seen.add(key)
            rows.append({"page_number": page_number, "received_at": str(received)})
            if item.get("_api_received_monotonic") is not None:
                try:
                    receipt_monos.append(float(item["_api_received_monotonic"]))
                except (TypeError, ValueError):
                    pass
        rows = sorted(rows, key=lambda row: (row["page_number"], row["received_at"]))
        first_received = rows[0]["received_at"] if rows else None
        first_mono = min(receipt_monos) if receipt_monos else None
        return rows, first_received, first_mono

    def _finish_summary(
        self,
        summary: dict[str, Any],
        *,
        started_monotonic: float,
        api: Any | None = None,
    ) -> dict[str, Any]:
        """Apply the final server-owned clocks and emit one canonical record."""

        if summary["status"] == "running":
            summary["status"] = "completed" if not self._errors else "degraded"
        summary["finished_at"] = self._now_iso()
        summary["wall_clock_sec"] = round(self._monotonic() - started_monotonic, 3)
        summary["errors"] = list(self._errors)
        summary.setdefault("latency", {}).update(
            summarize_latency(self._latency_observations)
        )
        if api is not None or not self.dry_run:
            try:
                from scripts.harvest_cost.emit import finalize_and_persist

                emitted = finalize_and_persist(summary, api)
                if emitted is None:
                    summary["degraded"]["report_emit_failed"] = 1
                    self._errors.append("report_emit_failed")
            except Exception as exc:
                logger.warning("cycle summary emit failed: %s", exc)
                summary["degraded"]["report_emit_failed"] = 1
                self._errors.append("report_emit_failed")
            if self._errors and summary["status"] == "completed":
                summary["status"] = "degraded"
            summary["errors"] = list(self._errors)
        return summary

    # ------------------------------------------------------------------
    # Step 1: Plan
    # ------------------------------------------------------------------

    def _plan_calls(self) -> list[PlannedCall]:
        """Build the per-cycle call list via plan_calls_for_cycle()."""
        try:
            calls = plan_calls_for_cycle(self.cfg)
        except (TypeError, ValueError) as exc:
            logger.warning("CycleRunner._plan_calls: plan_calls failed: %s", exc)
            self._errors.append(f"plan: {exc}")
            return []

        logger.info(
            "CycleRunner._plan_calls: %d calls planned",
            len(calls),
        )
        return calls

    # ------------------------------------------------------------------
    # Step 2: Fetch
    # ------------------------------------------------------------------

    def _resolve_window(
        self, call: PlannedCall, *, now: datetime
    ) -> tuple[int, int, bool]:
        """Resolve the (since_time, until_time) epoch window for one call.

        Returns (since_epoch, until_epoch, cursor_owned).  `cursor_owned` is
        False when the operator supplied an explicit window (the backfill
        command sets X_MONITOR_CYCLE_SINCE_TIME / _UNTIL_TIME): those runs
        sweep a historical span, so advancing the live cursor to their upper
        bound would skip everything in between.  R6.
        """
        op_since = getattr(settings, "X_MONITOR_CYCLE_SINCE_TIME", None)
        op_until = getattr(settings, "X_MONITOR_CYCLE_UNTIL_TIME", None)
        # `is not None`, not a falsy check: epoch 0 is a legitimate (if exotic)
        # lower bound for a full-history backfill, and silently substituting
        # the 2h cursor floor would quietly shrink an operator's window.
        if op_since is not None and str(op_since) != "":
            return (
                int(op_since),
                int(op_until)
                if op_until is not None and str(op_until) != ""
                else int(now.timestamp()),
                False,
            )

        since_dt = _read_cursor_since(call, now=now, cfg=self.cfg)
        return int(since_dt.timestamp()), int(now.timestamp()), True

    def _fetch_tweets(
        self,
        call: PlannedCall,
        api: TwitterApiClient,
        *,
        window: tuple[int, int],
        tip_only: bool = False,
        deadline: Any | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Fetch tweets for one PlannedCall via TwitterAPI.io.

        Returns (items, outcome) where outcome is one of:
          "ok"                  -- the call ran; items may still be empty,
                                   which is a successful sweep of a quiet
                                   window and may advance the cursor (KTD5).
          "truncated"           -- the per-call ceiling hit before the window
                                   was exhausted. ``items`` still holds every
                                   tweet retrieved across walk passes; the
                                   caller MUST persist them but MUST NOT
                                   advance the cursor past the original window.
          "error"               -- the call failed (auth/rate/server/other).
          "length_cap_exceeded" -- the query would exceed the 512-char cap
                                   once the time operators are injected.

        The distinction matters because an empty list alone cannot tell a
        quiet window from a failure, and only the former may advance the
        cursor (R2).  Per-call errors are caught -- one bad query doesn't kill
        the cycle.

        When truncated, we walk ``until_time`` backward (Latest order returns
        newest first) up to ``self.cfg.cycle.max_truncation_walks`` times so a noisy call
        like C1 can drain a 2h clamp instead of deadlocking on the tip.
        """
        limit_per_call = getattr(settings, "X_MONITOR_CYCLE_LIMIT_PER_CALL", None)
        max_pages = getattr(settings, "X_MONITOR_CYCLE_MAX_PAGES_PER_CALL", None)
        max_per_page_cfg = getattr(settings, "X_MONITOR_CYCLE_MAX_PER_PAGE", None)
        max_results_cap = (
            int(limit_per_call)
            if limit_per_call is not None
            else self.cfg.search.max_results
        )
        max_pages_cap = (
            int(max_pages) if max_pages is not None else self.cfg.search.max_pages
        )
        max_per_page_cap = (
            int(max_per_page_cfg)
            if max_per_page_cfg is not None
            else self.cfg.search.max_per_page
        )
        if tip_only:
            # Scheduled delivery is breadth-first: admit one fresh page for
            # every logical call before bounded backlog/deep-page work starts.
            max_results_cap = min(max_results_cap, max_per_page_cap)
            max_pages_cap = 1
        if deadline is not None:
            request_envelope = (
                float(getattr(api, "timeout_s", 60))
                * (int(getattr(api, "max_retries", 2)) + 1)
                + 8.0
            )
            page_budget = int(deadline.remaining() // request_envelope)
            if page_budget < 1:
                return [], "truncated"
            max_pages_cap = min(max_pages_cap, page_budget)
            max_results_cap = min(
                max_results_cap, max_pages_cap * max_per_page_cap
            )
        since_time, until_time = window

        logger.info(
            "_fetch_tweets: call_id=%s window=[%s, %s] (%.1f min) "
            "cap=%d pages=%d",
            call.call_id,
            since_time,
            until_time,
            (until_time - since_time) / 60.0,
            max_results_cap,
            max_pages_cap,
        )

        # Guard the post-injection length (R7 / KTD6). plan_calls already ran
        # assert_under_length_cap, but on the PRE-injection query -- it cannot
        # see the ~44 chars the two time operators add. An over-cap query is
        # the worst failure mode here: TwitterAPI.io returns zero results with
        # NO error, so the call looks like a quiet window and the cursor would
        # advance straight past a span that was never searched. Reporting it as
        # a distinct failure keeps the cursor pinned so the window is retried.
        # Length uses the original until_time (widest injection); walking the
        # upper bound shorter only shrinks the operator payload.
        effective_query = (
            f"{call.query_string} since_time:{since_time} until_time:{until_time}"
        )
        try:
            assert_under_length_cap(effective_query)
        except ValueError as exc:
            logger.error(
                "_fetch_tweets: %s would be %d chars after injecting the time "
                "operators (cap %d); skipping the call rather than letting "
                "TwitterAPI.io return a silent zero. %s",
                call.call_id,
                len(effective_query),
                X_LENGTH_CAP,
                exc,
            )
            self._errors.append(
                f"fetch.{call.call_id}: query length {len(effective_query)} "
                f"exceeds {X_LENGTH_CAP} after time operators"
            )
            return [], "length_cap_exceeded"

        all_items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        cur_until = until_time
        still_truncated = False
        page_offset = 0

        max_walks = (
            1
            if tip_only or deadline is not None
            else self.cfg.cycle.max_truncation_walks
        )
        for walk in range(max_walks):
            try:
                items, truncated = api.run_search(
                    call.query_string,
                    max_results=max_results_cap,
                    max_pages=max_pages_cap,
                    max_per_page=max_per_page_cap,
                    since_time=since_time,
                    until_time=cur_until,
                )
            except TwitterApiAuthError as exc:
                logger.error(
                    "_fetch_tweets: auth failure on %s: %s", call.call_id, exc
                )
                self._errors.append(f"fetch.{call.call_id}: auth: {exc}")
                return all_items, ("error" if not all_items else "truncated")
            except (TwitterApiRateLimitError, TwitterApiServerError) as exc:
                logger.warning(
                    "_fetch_tweets: rate/server error on %s: %s", call.call_id, exc
                )
                self._errors.append(f"fetch.{call.call_id}: {exc}")
                return all_items, ("error" if not all_items else "truncated")
            except Exception as exc:
                logger.warning(
                    "_fetch_tweets: error on %s: %s", call.call_id, exc
                )
                self._errors.append(f"fetch.{call.call_id}: {exc}")
                return all_items, ("error" if not all_items else "truncated")

            response_wall = self._wall_now()
            response_mono = self._monotonic()
            self._api_calls += 1
            new_on_pass = 0
            max_observed_page = 0
            fallback_received_at = response_wall.isoformat()
            for it in items or []:
                # The concrete client stamps the exact page receipt. Fakes
                # and compatibility clients do not, so preserve a server-
                # owned response clock rather than falling back to X.created_at.
                if "_api_received_at" not in it:
                    it["_api_received_at"] = fallback_received_at
                it.setdefault("_api_received_monotonic", response_mono)
                try:
                    local_page = max(1, int(it.get("_api_page_number", 1)))
                except (TypeError, ValueError):
                    local_page = 1
                page_number = page_offset + local_page
                it["_api_page_number"] = page_number
                max_observed_page = max(max_observed_page, local_page)
                tid = str(it.get("id") or it.get("tweet_id") or "")
                if tid and tid in seen_ids:
                    continue
                if tid:
                    seen_ids.add(tid)
                all_items.append(it)
                new_on_pass += 1

            page_offset += max_observed_page or 1

            if not truncated:
                still_truncated = False
                if walk > 0:
                    logger.info(
                        "_fetch_tweets: call_id=%s drained window after %d "
                        "walk(s); total_items=%d",
                        call.call_id,
                        walk + 1,
                        len(all_items),
                    )
                break

            still_truncated = True
            epochs = [
                ep
                for it in (items or [])
                if (ep := _item_created_epoch(it)) is not None
            ]
            if not epochs:
                logger.warning(
                    "_fetch_tweets: call_id=%s truncated but no parseable "
                    "created_at on %d items; cannot walk further "
                    "(total_items=%d)",
                    call.call_id,
                    len(items or []),
                    len(all_items),
                )
                break
            oldest = min(epochs)
            # until_time is exclusive; set upper bound to the oldest returned
            # so the next Latest page covers older posts only.
            if oldest <= since_time or oldest >= cur_until:
                logger.warning(
                    "_fetch_tweets: call_id=%s truncated; oldest_epoch=%s "
                    "does not advance walk (since=%s cur_until=%s); "
                    "stopping (total_items=%d)",
                    call.call_id,
                    oldest,
                    since_time,
                    cur_until,
                    len(all_items),
                )
                break
            logger.warning(
                "_fetch_tweets: call_id=%s TRUNCATED pass=%d/%d n_pass=%d "
                "total=%d window=[%s,%s] -> walk until=%s (%.1f min left)",
                call.call_id,
                walk + 1,
                max_walks,
                new_on_pass,
                len(all_items),
                since_time,
                cur_until,
                oldest,
                (oldest - since_time) / 60.0,
            )
            cur_until = oldest
        else:
            # exhausted walk budget while still truncated
            still_truncated = True
            logger.warning(
                "_fetch_tweets: call_id=%s still truncated after %d walks; "
                "total_items=%d — caller must hold cursor",
                call.call_id,
                max_walks,
                len(all_items),
            )

        if still_truncated:
            return all_items, "truncated"
        return all_items, "ok"


    def _prepare_call_a_roles(
        self, items: list[dict[str, Any]], *, list_id: int
    ) -> list[str]:
        contexts, degraded = resolve_call_a_author_contexts(
            list_id=list_id, items=items
        )
        for item in items:
            author_id = str(item.get("author_id") or "")
            context = contexts.get(author_id)
            if context is None:
                continue
            item["_author_membership_source"] = context.membership_source
            item["_author_membership_run_id"] = context.membership_run_id
            item["_author_membership_reconciled_at"] = (
                context.last_complete_reconciliation_at.isoformat()
                if context.last_complete_reconciliation_at
                else ""
            )
            if context.official_brands:
                # Official precedence: seed only official brands and bypass
                # relevance even if this author is staff for another brand.
                item["_author_seed_brands"] = list(context.official_brands)
                item["_author_staff_brands"] = []
                item["_call_a_staff_candidate"] = False
            elif context.staff_brands:
                item["_author_seed_brands"] = []
                item["_author_staff_brands"] = list(context.staff_brands)
                item["_call_a_staff_candidate"] = True
        return degraded

    @staticmethod
    def _seed_author_brands(
        item: dict[str, Any], *, brands: list[str], role: str
    ) -> None:
        if not brands:
            return
        tweet_id = str(item.get("id") or item.get("tweet_id") or "")
        created_at = str(item.get("created_at") or _now_iso())
        author_id = str(item.get("author_id") or "")
        source = str(item.get("_author_membership_source") or "unknown")
        source_run_id = str(item.get("_author_membership_run_id") or "")
        mentions: list[MentionRow] = list(item.get("mentions") or [])
        brand_ids: list[str] = list(item.get("brand_ids") or [])
        mention_keys = {(mention.brand_id, mention.source) for mention in mentions}
        for brand_id in brands:
            if (brand_id, "author_account") not in mention_keys:
                mentions.append(
                    MentionRow(
                        post_id=tweet_id,
                        brand_id=brand_id,
                        source="author_account",
                        raw_token=(
                            f"author_id={author_id};role={role};membership={source};"
                            f"run={source_run_id}"
                        ),
                        mentioned_at=created_at,
                    )
                )
            if brand_id not in brand_ids:
                brand_ids.append(brand_id)
        item["mentions"] = mentions
        item["brand_ids"] = brand_ids
        item["brand_id"] = brand_ids[0]
        item["_unattributed"] = False

    def _gate_call_a_staff_items(
        self, items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        from x_monitor.relevancy import call_binary_relevancy_llm

        kept: list[dict[str, Any]] = []
        drops = 0
        degraded: list[str] = []
        for item in items:
            brands = list(item.get("_author_staff_brands") or [])
            tweet_id = str(item.get("id") or item.get("tweet_id") or "?")
            receipt = item.get("_api_received_monotonic")
            receipt_age = (
                self._monotonic() - float(receipt) if receipt is not None else 0.0
            )
            keep = True
            if receipt_age >= 105:
                degraded.append(f"receipt_age_fail_open:{tweet_id}")
            elif self._relevancy_llm_call is None:
                degraded.append(f"relevancy_unavailable:{tweet_id}")
            else:
                started = self._monotonic()
                try:
                    verdict = call_binary_relevancy_llm(
                        post_text=item.get("text") or "",
                        call_id="A",
                        brand_hints=",".join(brands),
                        llm_call=self._relevancy_llm_call,
                    )
                    elapsed = self._monotonic() - started
                    if elapsed > self.cfg.harvest.relevancy_timeout_seconds:
                        degraded.append(f"relevancy_timeout_fail_open:{tweet_id}")
                    else:
                        keep = verdict.decision != "DROP"
                        if verdict.parse_failed:
                            degraded.append(f"relevancy_parse_fail_open:{tweet_id}")
                except Exception as exc:
                    degraded.append(f"relevancy_error_fail_open:{tweet_id}:{exc}")
            if not keep:
                drops += 1
                continue
            self._seed_author_brands(item, brands=brands, role="staff")
            kept.append(item)
        return kept, drops, degraded

    def _route_and_persist(
        self, call: PlannedCall, items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int, int, int, int, int, list[str]]:
        """Persist non-gated posts before any staff relevance request."""

        if call.call_id != "A":
            inserted, updated, attributed, failed = self._persist_items(items)
            return items, inserted, updated, attributed, failed, 0, []

        nongated = [item for item in items if not item.get("_call_a_staff_candidate")]
        staff = [item for item in items if item.get("_call_a_staff_candidate")]
        inserted, updated, attributed, failed = self._persist_items(nongated)
        kept = list(nongated)
        drops = 0
        degraded: list[str] = []
        # One ID-keyed unit at a time keeps the already-accepted prefix durable
        # even if a later relevance call times out or returns malformed output.
        for candidate in staff:
            accepted, candidate_drops, candidate_degraded = (
                self._gate_call_a_staff_items([candidate])
            )
            drops += candidate_drops
            degraded.extend(candidate_degraded)
            if accepted:
                n_inserted, n_updated, n_attributed, n_failed = (
                    self._persist_items(accepted)
                )
                inserted += n_inserted
                updated += n_updated
                attributed += n_attributed
                failed += n_failed
                kept.extend(accepted)
        return kept, inserted, updated, attributed, failed, drops, degraded

    def _attribute_items(
        self,
        items: list[dict[str, Any]],
        index: Any,
        brand_search_terms: dict[str, str],
    ) -> int:
        """Stamp brand_id / brand_ids / mentions on each item via
        attribute_to_brands.

        Returns the count of items that matched at least one brand.
        """
        classified = 0
        for it in items:
            body = it.get("text") or ""
            quoted = it.get("quoted_text") or ""
            post_like = {
                "tweet_id": str(it.get("id") or it.get("tweet_id") or ""),
                "id": str(it.get("id") or it.get("tweet_id") or ""),
                "text": (body + "\n" + quoted) if quoted else body,
                "created_at": it.get("created_at") or _now_iso(),
                "entities": it.get("entities", {}),
            }
            mentions: list[MentionRow] = list(
                attribute_to_brands(
                    post_like,
                    brands_accounts={},
                    brand_hashtags={},
                    compiled_keyword_index=index,
                    search_query=[],
                    brand_search_terms=brand_search_terms,
                )
            )
            it["mentions"] = mentions
            it["brand_ids"] = []
            self._seed_author_brands(
                it,
                brands=list(it.get("_author_seed_brands") or []),
                role="official",
            )
            mentions = list(it.get("mentions") or mentions)
            brand_ids: list[str] = []
            seen_brand: set[str] = set()
            for m in mentions:
                if (
                    m.brand_id
                    and m.brand_id != UNATTRIBUTED_BRAND_ID
                    and m.brand_id not in seen_brand
                ):
                    brand_ids.append(m.brand_id)
                    seen_brand.add(m.brand_id)
            if not brand_ids:
                it["_unattributed"] = True
                it["brand_ids"] = []
                it["brand_id"] = UNATTRIBUTED_BRAND_ID
                it["mentions"] = mentions
                it["classifications"] = {}
            else:
                it["brand_id"] = brand_ids[0]
                it["brand_ids"] = brand_ids
                it["mentions"] = mentions
                it["classifications"] = {}
                classified += 1
        return classified

    # ------------------------------------------------------------------
    # Step 4: Persist
    # ------------------------------------------------------------------

    def _persist_items(
        self,
        items: list[dict[str, Any]],
    ) -> tuple[int, int, int, int]:
        """Persist attributed items via Django ORM.

        For each item: upsert Account → upsert Post → persist attribution
        (PostBrand + PostBrandMention + PostBrandSignal).

        Returns (n_inserted, n_updated, n_attributed, n_failed).  `n_failed` matters for
        the cursor: a per-item transaction that rolled back means that tweet
        was NOT stored, so the caller must not advance past its window. Losing
        the count would make the failure permanent, because the overlap only
        re-covers the last minute and tweet_id dedup only suppresses
        duplicates of writes that already succeeded.
        """
        n_inserted = 0
        n_updated = 0
        n_attributed = 0
        n_failed = 0
        for it in items:
            if it.get("_unattributed"):
                continue
            it.pop("_db_inserted", None)
            it.pop("_persisted_post_id", None)
            try:
                with transaction.atomic():
                    account = _upsert_account(it)
                    post, created = _upsert_post(it, account=account)
                    if post is None:
                        continue
                    if created:
                        n_inserted += 1
                    else:
                        n_updated += 1
                    PostEnrichmentState.objects.get_or_create(post=post)
                    brand_ids: list[str] = list(it.get("brand_ids") or [])
                    mentions: list[MentionRow] = list(it.get("mentions") or [])
                    classifications: dict = it.get("classifications") or {}
                    n_attr = _persist_attribution(
                        post, brand_ids, mentions, classifications
                    )
                    n_attributed += n_attr
                # The timestamp is taken after the atomic block exits: this
                # is the server-owned commit boundary, including duplicate
                # updates. It is intentionally not Post.fetched_at.
                it["_db_inserted"] = bool(created)
                it["_persisted_post_id"] = str(post.pk)
                it["_db_committed_at"] = self._wall_now().isoformat()
            except Exception as exc:
                n_failed += 1
                tid = str(it.get("id") or it.get("tweet_id") or "?")
                logger.warning("_persist_items: failed for tweet_id=%s: %s", tid, exc)
                self._errors.append(f"persist.{tid}: {exc}")
        return n_inserted, n_updated, n_attributed, n_failed

    # ------------------------------------------------------------------
    # Step 5: Post-fetch (translate + classify)
    # ------------------------------------------------------------------

    def _run_post_fetch(
        self,
        kept_posts: list[dict[str, Any]],
        *,
        run_id: str = "post-fetch",
        deadline: Any | None = None,
        prefer_created_before: datetime | None = None,
    ) -> dict[str, Any]:
        """Drain a bounded durable translation/classification claim batch.

        Stage 1 (translate): calls translate_batch_pragmatics to produce
        text_en / text_zh_cn / bilingual commentary / lang_detected for each
        post.

        Stage 2 (classify): calls classify_batch_pragmatics_full to produce
        PostBrandSignal and PostBrandDiscourse rows for each post.

        Guardrails:
          - Pause between classifier batches (X_MONITOR_LLM_PAUSE_SECONDS).
          - Hard cap on LLM batches (self._max_llm_calls).  When reached,
            classification stops — remaining posts are persisted without
            labels and will be picked up by the next invocation.

        Lazy imports are used so the module loads without LLM deps.
        """
        counters = {
            **{key: 0 for key in ENRICHMENT_COUNT_KEYS},
            "n_translated": 0,
            "n_discourse": 0,
            "n_nationalism": 0,
            "n_failed_translate": 0,
            "n_translation_requeued": 0,
            "n_translator_unavailable": 0,
            "n_classifier_unavailable": 0,
            "n_unsanctioned_persisted": 0,
            "n_unsanctioned_cleared": 0,
            "flag_dead_letters": [],
            "inserted_post_ids": sorted(
                {
                    str(item.get("_persisted_post_id"))
                    for item in kept_posts
                    if item.get("_db_inserted")
                    and item.get("_persisted_post_id")
                }
            ),
            "enrichment_current_cycle_post_ids": [],
            "enrichment_carryover_post_ids": [],
            "enrichment_state_facts": [],
        }

        enrichment_cfg = self.cfg.harvest.enrichment
        claim_safe_envelope = enrichment_cfg.claim_safe_envelope_seconds
        if deadline is not None and not deadline.can_start(claim_safe_envelope):
            counters["n_enrichment_deferred"] = PostEnrichmentState.objects.filter(
                Q(translation_status=PostEnrichmentState.Status.PENDING)
                | Q(classification_status=PostEnrichmentState.Status.PENDING)
            ).count()
            return counters

        counters["n_translation_requeued"] = (
            _requeue_recent_incomplete_translations(cfg=enrichment_cfg)
        )

        claim_batch = _claim_enrichment_states(
            cfg=enrichment_cfg,
            run_id=run_id,
            prefer_created_before=prefer_created_before,
        )
        claimed_states = list(claim_batch.states)
        counters["n_enrichment_claimed"] = len(claimed_states)
        counters["n_enrichment_claimed_current_cycle"] = len(
            claim_batch.current_cycle_post_ids
        )
        counters["n_enrichment_claimed_carryover"] = len(
            claim_batch.carryover_post_ids
        )
        counters["enrichment_current_cycle_post_ids"] = list(
            claim_batch.current_cycle_post_ids
        )
        counters["enrichment_carryover_post_ids"] = list(
            claim_batch.carryover_post_ids
        )
        counters["n_enrichment_quarantined"] = claim_batch.quarantined
        if claim_batch.quarantined:
            self._error_counts["enrichment_quarantined"] += claim_batch.quarantined
            self._errors.append(
                f"post_fetch.enrichment_quarantined:{claim_batch.quarantined}"
            )
        if not claimed_states:
            return counters

        # Normalize claimed Django rows to v1 format. ``kept_posts`` remains
        # in the signature for caller compatibility; durable state is the
        # queue authority so retries survive later cycles and processes.
        translation_tweets: list[dict[str, Any]] = []
        classification_tweets: list[dict[str, Any]] = []
        for state in claimed_states:
            post = state.post
            tid = str(post.pk)
            text = post.text or ""
            brand_ids = list(post.brands.values_list("brand_id", flat=True))
            if tid and text:
                tweet = {
                    "tweet_id": tid,
                    "text": text,
                    "brand_ids": list(brand_ids),
                }
                if state.translation_status == PostEnrichmentState.Status.PENDING:
                    translation_tweets.append(tweet)
                if state.classification_status == PostEnrichmentState.Status.PENDING:
                    classification_tweets.append(tweet)

        if not translation_tweets and not classification_tweets:
            for state in claimed_states:
                _release_enrichment_claim(state.pk, run_id=run_id)
            return counters

        # Build only the clients required by pending stages. The translator and
        # classifier use distinct role-specific routes in production.
        from x_monitor.reattribute import (
            build_anthropic_client_from_env,
            build_translator_client_from_env,
        )

        translator_client = (
            build_translator_client_from_env(self.cfg)
            if translation_tweets
            else None
        )
        classifier_client = (
            build_anthropic_client_from_env(self.cfg)
            if classification_tweets
            else None
        )

        # Build brand_registry from Brand model
        from core.models import Brand as BrandModel

        # Convert Django Brand models to v1 BrandRow shape expected by classifier
        from x_monitor.attribution import BrandRow as _BrandRow
        brand_registry = [
            _BrandRow(
                brand_id=b.nickname,
                display_name=b.display_name or b.nickname,
                accent_color=b.accent_color or "#9ca3af",
                is_sentinel=b.is_sentinel,
            )
            for b in BrandModel.objects.filter(is_sentinel=False)
        ]

        # ---- Stage 1: translate ----
        from x_monitor.translator import translate_batch_pragmatics

        claimed_post_ids = [str(state.pk) for state in claimed_states]
        translation_succeeded: set[str] = set()
        if translation_tweets and translator_client is None:
            logger.warning(
                "_run_post_fetch: no translator client (ANTHROPIC_BASE_URL "
                "+ MINIMAX_API_TOKEN not set) — skipping translate; "
                "classifier stage will run if its client is available"
            )
            self._error_counts["translator_unavailable"] += 1
            self._errors.append("post_fetch.translator_unavailable")
            counters["n_translator_unavailable"] = 1
            translation_rows = []
        elif translation_tweets:
            translation_deadline = enrichment_cfg.start_attempt_deadline(
                monotonic=self._monotonic
            )
            try:
                translation_rows = translate_batch_pragmatics(
                    translation_tweets,
                    ["en", "zh_cn"],
                    translator_client,
                    on_batch_error=lambda batch, exc: self._error_counts.__setitem__(
                        "translator_batch_failed",
                        self._error_counts["translator_batch_failed"] + 1,
                    ),
                    cfg=self.cfg,
                    deadline=translation_deadline,
                    max_workers=3,
                )
            except Exception as exc:
                logger.warning("_run_post_fetch: translate failed: %s", exc, exc_info=True)
                self._error_counts["translator_batch_failed"] += 1
                translation_rows = []
        else:
            translation_rows = []

        # Persist translations back to Post rows.
        # Invariant: if lang_detected is canonical Simplified Chinese,
        # text_zh_cn MUST equal the source text. Same for EN when
        # lang_detected is "en". Without this, the dashboard's 翻译 column under
        # zh_CN falls back to text_translated -> text (the English
        # source) which is wrong for already-Chinese posts.
        #
        # Note: translation_rows from translate_batch_pragmatics do NOT
        # carry the source `text` (the LLM already saw it). We do one
        # bulk SELECT for the affected tweet_ids to fetch the source
        # text, then apply the per-row invariant.
        if translation_rows:
            from core.models import Post as PostModel

            CHINESE_LANG_CODES = {"zh-Hans"}
            tids = [r.get("tweet_id") for r in translation_rows if r.get("tweet_id")]
            posts_by_tid: dict[str, Any] = {}
            if tids:
                posts_by_tid = {
                    str(post.tweet_id): post
                    for post in PostModel.objects.filter(tweet_id__in=tids)
                }
            for r in translation_rows:
                tid = r.get("tweet_id")
                if not tid:
                    continue
                post = posts_by_tid.get(str(tid))
                if post is None:
                    continue
                if r.get("translation_failed"):
                    continue
                lang_detected = _present_text(r.get("lang_detected"))
                if lang_detected not in _CANONICAL_LANG_CODES:
                    lang_detected = None
                source_text = post.text or ""
                text_zh_cn = _present_text(
                    r.get("text_zh_cn") or r.get("literal_zh")
                )
                text_en = _present_text(r.get("text_en"))
                # Invariant: Chinese-detected posts must have text_zh_cn
                # populated (use the source text if the LLM didn't emit one).
                if lang_detected in CHINESE_LANG_CODES and not text_zh_cn:
                    text_zh_cn = source_text or None
                # Same for English-detected posts and text_en.
                if lang_detected == "en" and not text_en:
                    text_en = source_text or None
                comparison_values = (
                    source_text,
                    text_en or post.text_en,
                    text_zh_cn or post.text_zh_cn,
                )
                commentary_en = _present_text(r.get("en_equivalent"))
                if not _commentary_is_distinct(
                    commentary_en, *comparison_values
                ):
                    commentary_en = None
                commentary_zh_cn = _present_text(r.get("cn_equivalent"))
                if not _commentary_is_distinct(
                    commentary_zh_cn, *comparison_values
                ):
                    commentary_zh_cn = None
                effective = {
                    "text_en": text_en or post.text_en,
                    "text_zh_cn": text_zh_cn or post.text_zh_cn,
                    "commentary_en": commentary_en or post.commentary_en,
                    "commentary_zh_cn": commentary_zh_cn or post.commentary_zh_cn,
                    "lang_detected": lang_detected or post.lang_detected,
                }
                updates = {
                    field: value
                    for field, value in effective.items()
                    if _present_text(value) is not None
                }
                if updates:
                    PostModel.objects.filter(tweet_id=tid).update(**updates)
                if _translation_output_complete(
                    source_text=source_text,
                    **effective,
                ):
                    translation_succeeded.add(str(tid))
            counters["n_translated"] = len(translation_rows)
            counters["n_failed_translate"] = sum(
                1 for r in translation_rows if r.get("translation_failed")
            )

        newly_failed = _finish_enrichment_stage(
            post_ids=claimed_post_ids,
            run_id=run_id,
            stage="translation",
            succeeded_ids=translation_succeeded,
            error_code=(
                "translator_unavailable"
                if translation_tweets and translator_client is None
                else "translation_incomplete"
            ),
            cfg=enrichment_cfg,
        )
        counters["n_enrichment_quarantined"] += newly_failed

        # ---- Stage 2: classify ----
        from x_monitor.attribution import classify_batch_pragmatics_full

        pause_sec = getattr(settings, "X_MONITOR_LLM_PAUSE_SECONDS", 1)

        results: list[dict[str, Any]] = []
        classification_error_code = "classification_incomplete"
        if classification_tweets and classifier_client is None:
            logger.warning("_run_post_fetch: no classifier client — skipping classify")
            self._error_counts["classifier_unavailable"] += 1
            self._errors.append("post_fetch.classifier_unavailable")
            counters["n_classifier_unavailable"] = 1
            classification_error_code = "classifier_unavailable"
        elif classification_tweets:
            classification_deadline = enrichment_cfg.start_attempt_deadline(
                monotonic=self._monotonic
            )
            try:
                results = classify_batch_pragmatics_full(
                    classification_tweets,
                    brand_registry,
                    classifier_client,
                    model=self.cfg.llm.classifier_model,
                    on_batch_error=lambda batch, exc: self._error_counts.__setitem__(
                        "classifier_batch_failed",
                        self._error_counts["classifier_batch_failed"] + 1,
                    ),
                    deadline=classification_deadline,
                    max_workers=3,
                )
            except Exception as exc:
                logger.warning(
                    "_run_post_fetch: classify failed: %s", exc, exc_info=True
                )
                self._error_counts["classifier_batch_failed"] += 1
                classification_error_code = "classifier_exception"

        # Persist classifications with guardrails
        from core.models import (
            PostBrandDiscourse as PBDiscourse,
        )
        from core.models import (
            PostBrandSignal as PBSignal,
        )

        _CLASSIFY_BATCH_SIZE = getattr(
            settings, "X_MONITOR_CLASSIFY_BATCH_SIZE", 20
        )

        from monitor.unsanctioned_flags import persist_classifier_flags

        classification_succeeded: set[str] = set()
        for i, (tweet, result) in enumerate(zip(classification_tweets, results)):
            tid = tweet["tweet_id"]
            by_brand = (
                (result.get("by_brand") or {})
                if isinstance(result, dict)
                else {}
            )

            flag_result = persist_classifier_flags(
                post_id=tid,
                classifier_result=result,
                run_id=run_id,
            )
            if flag_result.outcome in {"persisted", "cleared"}:
                classification_succeeded.add(tid)
                counters[
                    "n_unsanctioned_persisted"
                    if flag_result.outcome == "persisted"
                    else "n_unsanctioned_cleared"
                ] += 1
            if flag_result.degraded:
                self._error_counts["classifier_flags_invalid"] += 1
                self._errors.append(f"post_fetch.classifier_flags_invalid:{tid}")
                if flag_result.dead_letter is not None:
                    counters["flag_dead_letters"].append(flag_result.dead_letter)

            for brand_id, cls in by_brand.items():
                post_type = cls.get("post_type")
                sentiment = cls.get("sentiment")
                if post_type:
                    try:
                        PBSignal.objects.update_or_create(
                            post_id=tid,
                            brand_id=brand_id,
                            post_type_id=post_type,
                            defaults={"sentiment_id": sentiment or ""},
                        )
                        counters["n_discourse"] += 1
                    except Exception:
                        logger.debug(
                            "_run_post_fetch: signal FK violation for %s/%s — skipping",
                            tid, post_type,
                        )

                discourse_raw = cls.get("discourse_role")
                # discourse_role may be a string or a list — normalize
                if isinstance(discourse_raw, str):
                    discourse_keys = [discourse_raw] if discourse_raw else []
                elif isinstance(discourse_raw, list):
                    discourse_keys = discourse_raw
                else:
                    discourse_keys = []
                cn_nat = cls.get("china_nationalism")
                us_nat = cls.get("us_nationalism")

                if discourse_keys:
                    for act_idx, dk in enumerate(discourse_keys):
                        if not dk:
                            continue
                        try:
                            PBDiscourse.objects.update_or_create(
                                post_id=tid,
                                brand_id=brand_id,
                                discourse_id=dk,
                                act_id=act_idx,
                                defaults={
                                    "china_nationalism_id": cn_nat or None,
                                    "us_nationalism_id": us_nat or None,
                                },
                            )
                        except Exception:
                            logger.debug(
                                "_run_post_fetch: discourse key %r not in FK table — skipping",
                                dk,
                            )
                    counters["n_nationalism"] += 1
                elif cn_nat or us_nat:
                    # Nationalism flags present without explicit discourse role —
                    # store under an empty discourse key.
                    PBDiscourse.objects.update_or_create(
                        post_id=tid,
                        brand_id=brand_id,
                        discourse_id="",
                        act_id=0,
                        defaults={
                            "china_nationalism_id": cn_nat or None,
                            "us_nationalism_id": us_nat or None,
                        },
                    )
                    counters["n_nationalism"] += 1

            # Guard: pause / cap at batch boundaries.
            # classify_batch_pragmatics_full batches 20 posts per LLM call
            # internally.  We track boundaries in the result loop so the
            # max_llm_calls cap can stop processing past a boundary.
            if (
                (i + 1) % _CLASSIFY_BATCH_SIZE == 0
                and i + 1 < len(classification_tweets)
            ):
                if pause_sec > 0:
                    import time as _time

                    _time.sleep(pause_sec)
                self._llm_call_count += 1
                if (
                    self._max_llm_calls is not None
                    and self._llm_call_count >= self._max_llm_calls
                ):
                    logger.info(
                        "_run_post_fetch: max_llm_calls (%d) reached — "
                        "stopping classification",
                        self._max_llm_calls,
                    )
                    break
            elif (i + 1) % _CLASSIFY_BATCH_SIZE == 0:
                self._llm_call_count += 1

        newly_failed += _finish_enrichment_stage(
            post_ids=claimed_post_ids,
            run_id=run_id,
            stage="classification",
            succeeded_ids=classification_succeeded,
            error_code=classification_error_code,
            cfg=enrichment_cfg,
        )
        resolved_states = list(
            PostEnrichmentState.objects.select_related("post").filter(
                post_id__in=claimed_post_ids
            )
        )
        current_cycle_id_set = set(claim_batch.current_cycle_post_ids)
        counters["enrichment_state_facts"] = [
            {
                "post_id": str(state.post_id),
                "lane": (
                    "current_cycle"
                    if str(state.post_id) in current_cycle_id_set
                    else "carryover"
                ),
                "translation_status": state.translation_status,
                "classification_status": state.classification_status,
                "output_complete": post_persisted_output_complete(state.post),
            }
            for state in resolved_states
        ]
        for state in claimed_states:
            _release_enrichment_claim(state.pk, run_id=run_id)
        for fact in counters["enrichment_state_facts"]:
            outcome = enrichment_stage_outcome(
                translation_status=fact["translation_status"],
                classification_status=fact["classification_status"],
            )
            lane = fact["lane"]
            counters[f"n_enrichment_{outcome}"] += 1
            counters[f"n_enrichment_{outcome}_{lane}"] += 1
        counters["n_enrichment_quarantined"] = (
            claim_batch.quarantined + counters["n_enrichment_failed"]
        )
        if newly_failed:
            self._error_counts["enrichment_quarantined"] += newly_failed
            self._errors.append(f"post_fetch.enrichment_quarantined:{newly_failed}")
        return counters

    def _replay_backlog(
        self,
        *,
        calls: list[PlannedCall],
        api: TwitterApiClient,
        index: Any,
        search_terms: dict[str, str],
        kept_all: list[dict[str, Any]],
        run_id: str,
        deadline: Any,
        include_quarantined: bool = False,
        quarantined_only: bool = False,
        cycle_started_monotonic: float | None = None,
    ) -> list[dict[str, Any]]:
        """Replay a bounded number of oldest pending residual windows."""

        by_identity = {
            tuple(sorted(_cursor_key(call).items())): call for call in calls
        }
        reports: list[dict[str, Any]] = []
        cycle_started_monotonic = (
            self._monotonic()
            if cycle_started_monotonic is None
            else cycle_started_monotonic
        )
        request_envelope = (
            float(getattr(api, "timeout_s", 60))
            * (int(getattr(api, "max_retries", 2)) + 1)
            + 8.0
        )
        backlog_cfg = self.cfg.harvest.backlog

        for _ in range(backlog_cfg.replays_per_cycle):
            if not deadline.can_start(request_envelope):
                reports.append({"status": "deadline_exhausted"})
                break
            claim = HarvestBacklogWindow.objects.claim_next(
                owner=f"cycle:{run_id}",
                run_id=run_id,
                claim_expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=max(int(request_envelope * 2), 60)),
                include_quarantined=include_quarantined,
                only_quarantined=quarantined_only,
            )
            if claim is None:
                break

            identity = {
                field: getattr(claim, field)
                for field in ("brand_id", "call_id", "call_kind", "bucket", "query_id")
            }
            call = by_identity.get(tuple(sorted(identity.items())))
            report: dict[str, Any] = {
                "window_id": claim.pk,
                "call_id": claim.call_id,
                "attempt": claim.attempts,
                "status": "error",
                "execution_kind": "backlog_replay",
                "replay": True,
                "request_started_at": self._wall_now().isoformat(),
            }
            replay_started = self._monotonic()
            try:
                if call is None:
                    report["status"] = return_claim(
                        claim.pk,
                        reason="planned_call_missing",
                        max_attempts=backlog_cfg.max_attempts,
                        max_age_hours=backlog_cfg.max_age_hours,
                    )
                    reports.append(report)
                    continue

                items, outcome = self._fetch_tweets(
                    call,
                    api,
                    window=(
                        int(claim.remaining_since.timestamp()),
                        int(claim.remaining_until.timestamp()),
                    ),
                    deadline=deadline,
                )
                replay_finished = self._monotonic()
                replay_page_receipts, first_page_received_at, first_page_mono = (
                    self._page_receipt_timing(items)
                )
                if replay_page_receipts:
                    report["page_receipts"] = replay_page_receipts
                    report["first_page_received_at"] = first_page_received_at
                    first_page_mono = first_page_mono or replay_finished
                    report["cycle_start_to_first_page_ms"] = max(
                        0, round((first_page_mono - cycle_started_monotonic) * 1000)
                    )
                else:
                    report["first_page_received_at"] = self._wall_now().isoformat()
                    report["cycle_start_to_first_page_ms"] = max(
                        0, round((replay_finished - cycle_started_monotonic) * 1000)
                    )
                persist_failed = 0
                kept: list[dict[str, Any]] = []
                if items:
                    self._posts_seen += len(items)
                    list_id = _resolve_x_monitor_list_id(self.cfg)
                    if call.call_id == "A" and list_id is not None:
                        observation = observe_call_a_authors(
                            list_id=int(list_id),
                            items=items,
                            run_id=run_id,
                        )
                        role_degraded = self._prepare_call_a_roles(
                            items, list_id=int(list_id)
                        )
                        report["membership_run_id"] = run_id
                        report["role_degraded"] = [
                            *observation.degraded,
                            *role_degraded,
                        ]
                    self._attribute_items(items, index, search_terms)
                    kept = [
                        item
                        for item in items
                        if not item.get("_unattributed")
                        or item.get("_call_a_staff_candidate")
                    ]
                    terms = [term.lower() for term in (call.not_include or []) if term]
                    if terms:
                        kept = [
                            item
                            for item in kept
                            if not _matches_any_term(
                                item.get("text") or "",
                                item.get("quoted_text") or "",
                                terms,
                            )
                        ]
                    (
                        kept,
                        inserted,
                        updated,
                        attributed,
                        persist_failed,
                        llm_drops,
                        relevancy_degraded,
                    ) = self._route_and_persist(call, kept)
                    self._posts_inserted += inserted
                    self._posts_updated += updated
                    self._posts_persist_failed += persist_failed
                    self._posts_attributed += attributed
                    self._record_latency_observations(kept)
                    report["n_inserted"] = inserted
                    report["n_updated"] = updated
                    report["n_persist_failed"] = persist_failed
                    existing_ids = {
                        str(item.get("id") or item.get("tweet_id") or "")
                        for item in kept_all
                    }
                    for item in kept:
                        tweet_id = str(item.get("id") or item.get("tweet_id") or "")
                        if tweet_id and tweet_id not in existing_ids:
                            kept_all.append(item)
                            existing_ids.add(tweet_id)
                    report.update(
                        n_results=len(items),
                        n_kept=len(kept),
                        n_inserted=inserted,
                        llm_drops=llm_drops,
                        relevancy_degraded=relevancy_degraded,
                    )
                    report["n_attributed"] = attributed

                if outcome in {"error", "length_cap_exceeded"} or persist_failed:
                    report["status"] = return_claim(
                        claim.pk,
                        reason=(
                            "persist_incomplete" if persist_failed else outcome
                        ),
                        max_attempts=backlog_cfg.max_attempts,
                        max_age_hours=backlog_cfg.max_age_hours,
                    )
                elif outcome == "ok":
                    report["status"] = (
                        "completed" if finish_claim(claim.pk) else "ownership_changed"
                    )
                else:
                    epochs = [
                        epoch
                        for item in items
                        if (epoch := _item_created_epoch(item)) is not None
                    ]
                    narrowed_until = (
                        datetime.fromtimestamp(min(epochs) + 1, tz=timezone.utc)
                        if epochs
                        else None
                    )
                    report["status"] = return_claim(
                        claim.pk,
                        reason="replay_truncated",
                        max_attempts=backlog_cfg.max_attempts,
                        max_age_hours=backlog_cfg.max_age_hours,
                        remaining_until=narrowed_until,
                    )
            except Exception as exc:
                logger.warning("backlog replay failed for window=%s: %s", claim.pk, exc)
                report["status"] = return_claim(
                    claim.pk,
                    reason="replay_exception",
                    max_attempts=backlog_cfg.max_attempts,
                    max_age_hours=backlog_cfg.max_age_hours,
                )
                self._errors.append(f"backlog.{claim.call_id}: {exc}")
            report["wall_clock_ms"] = round((self._monotonic() - replay_started) * 1000)
            reports.append(report)
        return reports

    def replay_backlog_only(self, *, include_quarantined: bool = False) -> dict[str, Any]:
        """Run explicit recovery without reading or advancing live cursors."""

        run_id = f"backlog-{uuid.uuid4().hex[:12]}"
        calls = self._plan_calls()
        enabled_models = _resolve_enabled_models(self.cfg, None)
        try:
            index = _build_brand_index(enabled_models)
        except Exception as exc:
            logger.exception("backlog replay attribution preflight failed")
            self._errors.append(f"attribution_preflight: {exc}")
            return {
                "run_id": run_id,
                "status": "aborted",
                "backlog_replays": [],
                "post_fetch": {},
                "errors": list(self._errors),
            }
        api = TwitterApiClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
        search_terms = _load_brand_search_terms()
        kept_all: list[dict[str, Any]] = []
        replay_started_monotonic = self._monotonic()
        deadline = self.cfg.harvest.start_deadline()
        reports = self._replay_backlog(
            calls=calls,
            api=api,
            index=index,
            search_terms=search_terms,
            kept_all=kept_all,
            run_id=run_id,
            deadline=deadline,
            include_quarantined=include_quarantined,
            quarantined_only=include_quarantined,
            cycle_started_monotonic=replay_started_monotonic,
        )
        post_fetch = self._run_post_fetch(
            kept_all,
            run_id=run_id,
            deadline=deadline,
        )
        return {
            "run_id": run_id,
            "status": "completed" if not self._errors else "degraded",
            "backlog_replays": reports,
            "post_fetch": post_fetch,
            "errors": list(self._errors),
        }

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Execute one harvest cycle.

        Returns a run summary dict (compatible with LATEST.json shape).
        """
        cycle_started_wall = self._wall_now()
        cycle_started_at = cycle_started_wall.isoformat(timespec="seconds")
        t0 = self._monotonic()
        run_id = (
            f"{cycle_started_at.replace(':', '').replace('+', '_').replace('-', '')}"
            f"-{uuid.uuid4().hex[:8]}"
        )
        started_at = cycle_started_at
        deadline = self.cfg.harvest.start_deadline()

        summary: dict[str, Any] = {
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": None,
            "status": "running",
            "cycle_kind": self.cycle_kind,
            "dry_run": self.dry_run,
            "degraded": {},
            "planned_calls": [],
            "calls": [],
            "backlog_replays": [],
            "latency": {"cycle_started_at": cycle_started_at},
            "totals": {
                "n_calls_planned": 0,
                "n_calls_run": 0,
                "n_results": 0,
                "n_inserted": 0,
                "n_updated": 0,
                "n_persist_failed": 0,
                "n_attributed": 0,
                "n_classifications_written": 0,
            },
            "errors": [],
        }

        # ---- Step 1: Plan calls ----
        try:
            calls = self._plan_calls()
        except Exception as exc:
            logger.exception("CycleRunner.run: plan_calls failed: %s", exc)
            summary["status"] = "aborted"
            summary["degraded"]["plan"] = str(exc)
            return self._finish_summary(summary, started_monotonic=t0)

        summary["totals"]["n_calls_planned"] = len(calls)

        # Backfill batching: narrow to the requested call IDs.
        if self._backfill_call_ids:
            requested = set(self._backfill_call_ids)
            calls = [c for c in calls if c.call_id in requested]
            if not calls:
                summary["status"] = "completed"
                summary["degraded"]["backfill"] = (
                    "No matching calls in requested batch — may already be done."
                )
                return self._finish_summary(summary, started_monotonic=t0)

        if not calls:
            summary["status"] = "degraded"
            summary["degraded"]["no_calls"] = (
                "No calls planned — check X_MONITOR_LIST_ID in settings"
            )
            return self._finish_summary(summary, started_monotonic=t0)

        # Record planned metadata separately. ``calls`` is reserved for one
        # row per executed live call; conflating these two lists previously
        # made cost reports double-count planned rows.
        for call in calls:
            summary["planned_calls"].append({
                "call_id": call.call_id,
                "call_kind": call.call_kind,
                "brand_id": call.brand_id,
                "bucket": call.bucket,
                "query_length": call.query_length,
            })

        # ---- Dry-run: stop here ----
        if self.dry_run:
            summary["status"] = "completed"
            logger.info(
                "CycleRunner.run (dry-run): %d calls planned",
                len(calls),
            )
            return self._finish_summary(summary, started_monotonic=t0)

        # ---- Live run: fetch + attribute + persist ----
        # Check skip_fetch flag
        skip_fetch = getattr(settings, "X_MONITOR_CYCLE_SKIP_FETCH", False)

        if skip_fetch:
            logger.info("CycleRunner.run: --skip-fetch active; plan only.")
            summary["status"] = "completed"
            return self._finish_summary(summary, started_monotonic=t0)

        # Build the attribution index before constructing the provider client.
        # Missing policy/DB coverage must stop the cycle before any provider
        # work can begin.
        brand_filter_str = getattr(settings, "X_MONITOR_CYCLE_BRAND_FILTER", None)
        brand_filter: list[str] | None = None
        if brand_filter_str and isinstance(brand_filter_str, str):
            brand_filter = [
                b.strip() for b in brand_filter_str.split(",") if b.strip()
            ]
        enabled_models = _resolve_enabled_models(self.cfg, brand_filter)
        try:
            index = _build_brand_index(enabled_models)
        except Exception as exc:
            logger.exception("CycleRunner.run: attribution preflight failed")
            summary["status"] = "aborted"
            summary["degraded"]["attribution_preflight"] = str(exc)
            return self._finish_summary(summary, started_monotonic=t0)

        # Build TwitterAPI client from environment only after attribution
        # policy and database coverage have passed preflight.
        try:
            api = TwitterApiClient.from_env(self.twitterapi_credential_purpose)
        except RuntimeError as exc:
            logger.error("CycleRunner.run: cannot create API client: %s", exc)
            summary["status"] = "aborted"
            summary["degraded"]["api_client"] = str(exc)
            return self._finish_summary(summary, started_monotonic=t0)

        search_terms = _load_brand_search_terms()
        list_id = _resolve_x_monitor_list_id(self.cfg)

        kept_all: list[dict[str, Any]] = []
        first_page_max_ms = 0

        for call in calls:
            call_t0 = self._monotonic()
            request_started_at = self._wall_now().isoformat()
            call_entry: dict[str, Any] = {
                "call_id": call.call_id,
                "call_kind": call.call_kind,
                "brand_id": call.brand_id,
                "bucket": call.bucket,
                "query_length": call.query_length,
                "status": "error",
                "execution_kind": "live",
                "replay": False,
                "n_results": 0,
                "n_kept": 0,
                "n_inserted": 0,
                "n_updated": 0,
                "n_persist_failed": 0,
                "request_started_at": request_started_at,
            }

            # Resolve this call's time window from its cursor (or the
            # operator-supplied override) BEFORE fetching, so the value we
            # later store is exactly the upper bound we queried.
            call_now = self._wall_now()
            since_epoch, until_epoch, cursor_owned = self._resolve_window(
                call, now=call_now
            )
            call_entry["window_since"] = since_epoch
            call_entry["window_until"] = until_epoch

            # Fetch
            items, outcome = self._fetch_tweets(
                call,
                api,
                window=(since_epoch, until_epoch),
                tip_only=(self.cycle_kind == "scheduled" and cursor_owned),
            )
            fetch_finished_mono = self._monotonic()
            fetch_finished_wall = self._wall_now()
            page_receipts, first_page_received_at, first_page_mono = (
                self._page_receipt_timing(items)
            )
            if page_receipts:
                call_entry["page_receipts"] = page_receipts
                first_page_mono = first_page_mono or fetch_finished_mono
            else:
                # Empty responses have no tweet carrying the receipt clock;
                # the response return is the server-owned page receipt.
                first_page_received_at = fetch_finished_wall.isoformat()
                first_page_mono = fetch_finished_mono
                call_entry["page_receipts"] = [
                    {"page_number": 1, "received_at": first_page_received_at}
                ]
            call_entry["first_page_received_at"] = first_page_received_at
            call_entry["cycle_start_to_first_page_ms"] = max(
                0, round((first_page_mono - t0) * 1000)
            )
            first_page_max_ms = max(
                first_page_max_ms, call_entry["cycle_start_to_first_page_ms"]
            )
            if call.call_id == "A" and list_id is not None and items:
                observation = observe_call_a_authors(
                    list_id=int(list_id),
                    items=items,
                    run_id=run_id,
                )
                call_entry["list_membership_observation"] = {
                    "status": observation.status,
                    "observed": observation.observed,
                    "degraded": list(observation.degraded),
                }
                if observation.degraded:
                    summary["degraded"]["list_membership_observation"] = list(
                        observation.degraded
                    )
                role_degraded = self._prepare_call_a_roles(
                    items, list_id=int(list_id)
                )
                if role_degraded:
                    call_entry["author_role_degraded"] = role_degraded
                    summary["degraded"]["call_a_author_roles"] = role_degraded
            # Hard failures: no items to keep, hold cursor, move on.
            # "truncated" is NOT a hard failure -- items were retrieved and
            # must be persisted; only the cursor advance is withheld so the
            # remainder of the window is re-swept next cycle.
            if outcome in ("error", "length_cap_exceeded"):
                logger.warning(
                    "run: call_id=%s outcome=%s -- holding cursor, no persist",
                    call.call_id,
                    outcome,
                )
                call_entry["status"] = outcome
                call_entry["cursor_advanced"] = False
                call_entry["fetch_n"] = call_entry.get("n_results", 0)
                call_entry["wall_clock_ms"] = round((self._monotonic() - call_t0) * 1000)
                summary["calls"].append(call_entry)
                summary["totals"]["n_calls_run"] += 1
                continue

            if not items:
                if outcome == "ok":
                    # Empty but successful sweep: advance (KTD5), else a quiet
                    # brand would re-request the same window forever.
                    if cursor_owned:
                        call_entry["cursor_advanced"] = _advance_cursor(
                            call,
                            upper_bound=datetime.fromtimestamp(
                                until_epoch, tz=timezone.utc
                            ),
                        )
                        if not call_entry["cursor_advanced"]:
                            self._errors.append(
                                f"cursor.{call.call_id}: successful empty sweep "
                                "could not advance"
                            )
                            call_entry["status"] = "cursor_write_failed"
                        else:
                            call_entry["status"] = "no_results"
                    else:
                        call_entry["cursor_advanced"] = False
                        call_entry["status"] = "no_results"
                else:
                    if cursor_owned:
                        transfer = transfer_truncated_coverage(
                            call_identity=_cursor_key(call),
                            original_since=since_epoch,
                            original_until=until_epoch,
                            oldest_seen_at=None,
                            reason_code="truncated_without_parseable_oldest",
                            pending_limit=self.cfg.harvest.backlog.pending_per_call,
                            quarantined_limit=(
                                self.cfg.harvest.backlog.quarantined_per_call
                            ),
                        )
                        call_entry["coverage_transfer"] = transfer.outcome
                        call_entry["cursor_advanced"] = transfer.cursor_advanced
                        call_entry["backlog_window_id"] = transfer.backlog_window_id
                        call_entry["status"] = (
                            "truncated_replay_queued"
                            if transfer.outcome == "transferred"
                            else transfer.outcome
                        )
                        if not transfer.cursor_advanced:
                            self._errors.append(
                                f"coverage.{call.call_id}: {transfer.outcome}"
                            )
                    else:
                        call_entry["status"] = "truncated"
                        call_entry["cursor_advanced"] = False
                call_entry["fetch_n"] = call_entry.get("n_results", 0)
                call_entry["wall_clock_ms"] = round((self._monotonic() - call_t0) * 1000)
                summary["calls"].append(call_entry)
                summary["totals"]["n_calls_run"] += 1
                continue

            call_entry["n_results"] = len(items)
            self._posts_seen += len(items)

            # Attribute
            self._attribute_items(items, index, search_terms)

            # Staff-only Call A candidates may have no body keyword yet; keep
            # them until the bounded relevance decision can seed author brands.
            kept = [
                it
                for it in items
                if not it.get("_unattributed")
                or it.get("_call_a_staff_candidate")
            ]
            self._posts_attributed += len(kept)
            call_entry["n_kept"] = len(kept)

            # U5 runtime wire-in: post-fetch ban match against
            # call.not_include (R12). Stable hijacks like F1/Kimi for
            # moonshot_kimi are listed in config.yaml's x_query_specs[*]
            # .not_include. We match case-insensitively against the
            # tweet's text and quoted_text. Drop counters surface in
            # call_entry["not_include_drops"] for ops dashboards.
            ni_terms = [t.lower() for t in (call.not_include or []) if t]
            ni_drop_count = 0
            if ni_terms:
                pre_drop = len(kept)
                kept = [
                    it for it in kept
                    if not _matches_any_term(
                        it.get("text") or "", it.get("quoted_text") or "",
                        ni_terms,
                    )
                ]
                ni_drop_count = pre_drop - len(kept)
            call_entry["not_include_drops"] = ni_drop_count
            self._posts_attributed -= ni_drop_count  # adjust attributed count

            (
                kept,
                n_inserted,
                n_updated,
                _n_attributed,
                n_persist_failed,
                llm_drop_count,
                relevancy_degraded,
            ) = self._route_and_persist(call, kept)
            call_entry["llm_drops"] = llm_drop_count
            if relevancy_degraded:
                call_entry["relevancy_degraded"] = relevancy_degraded
                summary["degraded"].setdefault("relevancy", []).extend(
                    relevancy_degraded
                )
            self._posts_attributed -= llm_drop_count
            # Re-derive n_kept after both gates
            call_entry["n_kept"] = len(kept)
            # Update U7 keep_rate with post-gate counts
            nr = call_entry.get("n_results", 0)
            call_entry["keep_rate"] = round(len(kept) / nr, 4) if nr > 0 else 0.0

            self._posts_inserted += n_inserted
            self._posts_updated += n_updated
            self._posts_persist_failed += n_persist_failed
            self._record_latency_observations(kept)
            call_entry["n_inserted"] = n_inserted
            call_entry["n_updated"] = n_updated
            call_entry["n_persist_failed"] = n_persist_failed
            call_entry["n_attributed"] = _n_attributed

            # Accumulate for post-fetch
            seen_ids: set[str] = {
                str(k.get("id") or k.get("tweet_id") or "")
                for k in kept_all
            }
            for k in kept:
                tid = str(k.get("id") or k.get("tweet_id") or "")
                if tid and tid not in seen_ids:
                    kept_all.append(k)
                    seen_ids.add(tid)

            if n_persist_failed:
                call_entry["status"] = "persist_incomplete"
                call_entry["cursor_advanced"] = False
                logger.warning(
                    "run: holding cursor for call_id=%s -- %d of %d items "
                    "failed to persist; the window will be re-swept",
                    call.call_id,
                    n_persist_failed,
                    len(kept),
                )
            elif outcome == "truncated":
                if cursor_owned:
                    epochs = [
                        epoch
                        for item in items
                        if (epoch := _item_created_epoch(item)) is not None
                    ]
                    oldest_seen_at = (
                        datetime.fromtimestamp(min(epochs), tz=timezone.utc)
                        if epochs
                        else None
                    )
                    transfer = transfer_truncated_coverage(
                        call_identity=_cursor_key(call),
                        original_since=since_epoch,
                        original_until=until_epoch,
                        oldest_seen_at=oldest_seen_at,
                        reason_code=(
                            "page_cap" if epochs else "invalid_oldest_created_at"
                        ),
                        pending_limit=self.cfg.harvest.backlog.pending_per_call,
                        quarantined_limit=(
                            self.cfg.harvest.backlog.quarantined_per_call
                        ),
                    )
                    call_entry["coverage_transfer"] = transfer.outcome
                    call_entry["cursor_advanced"] = transfer.cursor_advanced
                    call_entry["backlog_window_id"] = transfer.backlog_window_id
                    call_entry["status"] = (
                        "truncated_replay_queued"
                        if transfer.outcome == "transferred"
                        else transfer.outcome
                    )
                    if not transfer.cursor_advanced:
                        self._errors.append(
                            f"coverage.{call.call_id}: {transfer.outcome}"
                        )
                else:
                    call_entry["status"] = "truncated"
                    call_entry["cursor_advanced"] = False
            else:
                call_entry["status"] = "completed"
                # Advance only when fetch AND attribute AND persist all
                # succeeded AND the window was fully drained.
                if cursor_owned:
                    call_entry["cursor_advanced"] = _advance_cursor(
                        call,
                        upper_bound=datetime.fromtimestamp(
                            until_epoch, tz=timezone.utc
                        ),
                    )
                    if not call_entry["cursor_advanced"]:
                        call_entry["status"] = "cursor_write_failed"
                        self._errors.append(
                            f"cursor.{call.call_id}: completed sweep could not advance"
                        )
            call_entry["wall_clock_sec"] = round(self._monotonic() - call_t0, 3)
            call_entry["wall_clock_ms"] = round(call_entry["wall_clock_sec"] * 1000)

            call_entry["fetch_n"] = call_entry.get("n_results", 0)
            nr = call_entry["fetch_n"]
            nk = call_entry.get("n_kept", 0)
            call_entry["keep_rate"] = round(nk / nr, 4) if nr > 0 else 0.0

            summary["calls"].append(call_entry)
            summary["totals"]["n_calls_run"] += 1

            # U7 cycle-level anomaly aggregates: min/mean keep_rate
            # across calls, plus max keep_rate (a spike here means a
            # single call is much looser than the rest — investigate).
            tr = summary["totals"]
            rates = [c.get("keep_rate", 0.0) for c in summary["calls"]]
            tr["keep_rate_min"] = round(min(rates), 4) if rates else 0.0
            tr["keep_rate_mean"] = round(sum(rates) / len(rates), 4) if rates else 0.0
            tr["keep_rate_max"] = round(max(rates), 4) if rates else 0.0

        summary["tip_sweep_wall_clock_sec"] = round(self._monotonic() - t0, 3)
        tip_sweep_target_ms = int(self.cfg.harvest.tip_sweep_target_seconds * 1000)
        summary["tip_sweep_within_target"] = (
            first_page_max_ms <= tip_sweep_target_ms
        )
        summary["latency"]["tip_sweep_wall_clock_ms"] = round(
            summary["tip_sweep_wall_clock_sec"] * 1000
        )
        summary["latency"]["tip_sweep_first_page_max_ms"] = max(
            first_page_max_ms, 0
        )
        summary["latency"]["tip_sweep_target_ms"] = tip_sweep_target_ms
        summary["latency"]["tip_sweep_within_target"] = bool(
            summary["tip_sweep_within_target"]
        )
        if not summary["tip_sweep_within_target"]:
            summary["degraded"]["tip_sweep_first_page_timeout"] = 1
            self._errors.append("tip_sweep_first_page_timeout")

        # ---- Bounded post-fetch queue: immediately after all live tips ----
        if summary["status"] != "aborted":
            post_fetch_started = self._monotonic()
            pf_counters = self._run_post_fetch(
                kept_all,
                run_id=run_id,
                deadline=deadline,
                prefer_created_before=(
                    None if self.cycle_kind == "backfill" else cycle_started_wall
                ),
            )
            post_fetch_completed_at = self._wall_now().isoformat()
            pf_counters["completed_at"] = post_fetch_completed_at
            pf_counters["wall_clock_ms"] = round(
                (self._monotonic() - post_fetch_started) * 1000
            )
            summary["latency"]["post_fetch_completed_at"] = post_fetch_completed_at
            summary.setdefault("post_fetch", {}).update(pf_counters)
            if pf_counters.get("n_translator_unavailable"):
                summary["degraded"]["translator_unavailable"] = True
            if pf_counters.get("n_classifier_unavailable"):
                summary["degraded"]["classifier_unavailable"] = True
            if pf_counters.get("n_enrichment_quarantined"):
                summary["degraded"]["enrichment_quarantined"] = int(
                    pf_counters["n_enrichment_quarantined"]
                )
            if pf_counters.get("flag_dead_letters"):
                summary["degraded"]["classifier_flag_dead_letters"] = list(
                    pf_counters["flag_dead_letters"]
                )
            summary.setdefault("n_errors_by_type", {}).update(
                dict(self._error_counts)
            )

        if self.cycle_kind == "scheduled":
            if list_id is not None:
                reconciliation = run_due_reconciliation(
                    api=api,
                    cfg=self.cfg,
                    list_id=int(list_id),
                    deadline=deadline,
                    run_id=run_id,
                )
                summary["list_membership_reconciliation"] = {
                    "status": reconciliation.status,
                    "observed": reconciliation.observed,
                    "activated": reconciliation.activated,
                    "deactivated": reconciliation.deactivated,
                    "snapshot_id": reconciliation.snapshot_id,
                    "degraded": list(reconciliation.degraded),
                }
                if reconciliation.status in {"incomplete", "deferred"}:
                    summary["degraded"]["list_membership_reconciliation"] = list(
                        reconciliation.degraded
                    )
            summary["backlog_replays"] = self._replay_backlog(
                calls=calls,
                api=api,
                index=index,
                search_terms=search_terms,
                kept_all=kept_all,
                run_id=run_id,
                deadline=deadline,
                cycle_started_monotonic=t0,
            )

        # ---- One-shot metrics refresh (plan 2026-08-10-002) ----
        # Replaces continuous official/staff + daily QT recheck. Never
        # aborts the cycle — refresh failures are degraded stats.
        if summary["status"] != "aborted" and self.cycle_kind != "backfill":
            try:
                from monitor.metrics_refresh import run_metrics_refresh

                mr_out = run_metrics_refresh(api, self.cfg, deadline=deadline)
                summary.setdefault("metrics_refresh", {}).update(mr_out)
                if int(mr_out.get("n_refreshed") or 0):
                    logger.info(
                        "CycleRunner.run: metrics_refresh refreshed=%s due=%s",
                        mr_out.get("n_refreshed"),
                        mr_out.get("n_due"),
                    )
            except Exception as exc:
                logger.warning("metrics_refresh channel failed: %s", exc)
                summary.setdefault("metrics_refresh", {})["error"] = str(exc)

        # ---- Finalize ----
        summary["totals"]["n_results"] = self._posts_seen
        summary["totals"]["n_inserted"] = self._posts_inserted
        summary["totals"]["n_updated"] = self._posts_updated
        summary["totals"]["n_persist_failed"] = self._posts_persist_failed
        summary["totals"]["n_attributed"] = self._posts_attributed

        summary = self._finish_summary(summary, started_monotonic=t0, api=api)

        logger.info(
            "CycleRunner.run: %d calls, %d posts seen, %d inserted, "
            "%d attributed in %.2fs",
            summary["totals"]["n_calls_run"],
            summary["totals"]["n_results"],
            summary["totals"]["n_inserted"],
            summary["totals"]["n_attributed"],
            summary["wall_clock_sec"],
        )
        return summary
