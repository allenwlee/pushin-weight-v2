"""Pure half-hour Chatter decisions shared by chronological replay and the worker."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import unicodedata

from pydantic import BaseModel, ConfigDict, Field

QUARTER = timedelta(minutes=15)
GRACE = timedelta(minutes=5)
HORIZON = timedelta(hours=2)
PROMPT = (
    Path(__file__).resolve().parents[2]
    / "config/editorial_chatter_chain/trends-ranking-v2.txt"
)


class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=6000)
    headline_ids: list[int] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=6000)
    qualifies: bool
    prior_episode_id: str | None
    material_change: str | None


class WindowRanking(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ranked_stories: list[Episode]


def instant(value):
    date = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError("timezone required")
    return date.astimezone(UTC)


def wording(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def decision_packet(observations, cutoff, history):
    boundary = instant(cutoff)
    if boundary.minute % 30 or boundary.second or boundary.microsecond:
        raise ValueError("decision requires a half-hour boundary")
    if history.get("cutoff") and instant(history["cutoff"]) >= boundary:
        raise ValueError("decision history must precede boundary")
    slots = {}
    for obs in observations:
        slot, receipt = instant(obs["slot"]), instant(obs["observed_at"])
        if slot.minute % 15 or slot.second or slot.microsecond or receipt < slot:
            raise ValueError("invalid capture time")
        if boundary - 4 * QUARTER < slot <= boundary and receipt <= boundary + GRACE:
            if slot in slots and slots[slot] != obs:
                raise ValueError("conflicting capture for slot")
            slots[slot] = obs
    seen = {
        k: v
        for k, v in history.get("seen", {}).items()
        if instant(v["last_seen"]) > boundary - HORIZON
    }
    groups = defaultdict(list)
    for slot, obs in sorted(slots.items()):
        rows = {}
        for idx, raw in enumerate(obs["headlines"], 1):
            key = wording(raw["trend_name"])
            if not key:
                raise ValueError("empty trend wording")
            rows.setdefault(key, (idx, raw))
        for key, (idx, raw) in rows.items():
            groups[key].append((slot, obs, idx, raw))
    headlines = []
    trigger = False
    for key, samples in groups.items():
        prev = seen.get(key, {})
        consecutive = any(b[0] - a[0] == QUARTER for a, b in zip(samples, samples[1:]))
        trigger |= not prev or (consecutive and not prev.get("repeated"))
        receipt = samples[-1][1]["observed_at"]
        seen[key] = {
            "first_seen": prev.get("first_seen", samples[0][1]["observed_at"]),
            "last_seen": receipt,
            "repeated": consecutive or prev.get("repeated", False),
        }
        headlines.append(
            {
                **samples[-1][3],
                "headline_id": len(headlines) + 1,
                "first_seen": seen[key]["first_seen"],
                "last_seen": receipt,
                "snapshot_count": len(samples),
                "consecutive": consecutive,
                "appearances": [
                    {
                        "request_id": str(o["request_id"]),
                        "row": idx,
                        "slot": s.isoformat(),
                    }
                    for s, o, idx, _ in samples
                ],
            }
        )
    return {
        "cutoff": boundary.isoformat(),
        "headlines": headlines,
        "history": history,
        "seen": seen,
        "needs_ranking": bool(trigger),
        "missing_slots": [
            (boundary - i * QUARTER).isoformat()
            for i in reversed(range(4))
            if boundary - i * QUARTER not in slots
        ],
    }


def selection_request(packet):
    history = packet["history"]
    recent = [
        {k: e[k] for k in ("episode_id", "title", "last_seen")} | {"state": state}
        for state in ("admitted", "pending")
        for e in history.get(state, [])
        if instant(e["last_seen"]) > instant(packet["cutoff"]) - HORIZON
    ]
    rows = [
        {
            k: x[k]
            for k in (
                "headline_id",
                "trend_name",
                "first_seen",
                "last_seen",
                "snapshot_count",
                "consecutive",
            )
        }
        for x in packet["headlines"]
    ]
    return {
        "packet_version": "chatter-trends-ranking-v2",
        "system": PROMPT.read_text(),
        "user": json.dumps(
            {"headlines": rows, "prior_episodes": recent}, ensure_ascii=False
        ),
    }


def apply_selection(packet, reply):
    boundary = instant(packet["cutoff"])
    history = packet["history"]
    observed = {wording(h["trend_name"]): instant(h["last_seen"]) for h in packet["headlines"]}

    def refresh(entry):
        last = max([instant(entry["last_seen"])] + [observed[k] for k in entry["wordings"] if k in observed])
        return {**entry, "last_seen": last.isoformat()}

    retained = {
        state: [
            e
            for e in map(refresh, history.get(state, []))
            if instant(e["last_seen"]) > boundary - HORIZON
        ]
        for state in ("admitted", "pending")
    }
    expired = [
        e["episode_id"]
        for e in history.get("pending", [])
        if e["episode_id"] not in {r["episode_id"] for r in retained["pending"]}
    ]
    earlier = {e["episode_id"]: e for e in retained["admitted"] + retained["pending"]}
    published = {e["episode_id"] for e in retained["admitted"]}
    if packet["needs_ranking"] != (reply is not None):
        raise ValueError("decision and ranking receipt disagree")
    groups = (
        WindowRanking.model_validate(reply).ranked_stories if reply is not None else []
    )
    rows = {h["headline_id"]: h for h in packet["headlines"]}
    if reply is not None and sorted(
        i for g in groups for i in g.headline_ids
    ) != sorted(rows):
        raise ValueError("ranking must cover every headline exactly once")
    explicit_priors = {group.prior_episode_id for group in groups if group.prior_episode_id}
    queued = []
    handled = set()
    for g in groups:
        prior = g.prior_episode_id
        if prior is not None and (prior not in earlier or prior in handled):
            raise ValueError("invalid prior episode reference")
        if g.material_change is not None and (
            not g.material_change.strip() or prior not in published
        ):
            raise ValueError("material change requires an admitted episode")
        members = [rows[i] for i in g.headline_ids]
        keys = sorted(wording(x["trend_name"]) for x in members)
        # A model may forget to reference an exact repeat. Recover the old ID by evidence.
        matches = {
            e["episode_id"]
            for e in earlier.values()
            if set(keys).intersection(e["wordings"])
        }
        if not prior and len(matches) == 1:
            match = next(iter(matches))
            if match in explicit_priors or match in handled:
                # Another group explicitly owns this ID. An exact rerun of its
                # evidence adds nothing, while a new grouping needs fresh wording.
                if set(keys).issubset(earlier[match]["wordings"]):
                    continue
            else:
                prior = match
        if prior:
            handled.add(prior)
        last = max(instant(x["last_seen"]) for x in members).isoformat()
        if prior in published:
            previous = earlier[prior]
            if not g.material_change or not set(keys).difference(previous["wordings"]):
                refreshed = {
                    **previous,
                    "last_seen": max(
                        instant(previous["last_seen"]), instant(last)
                    ).isoformat(),
                    "wordings": sorted(set(previous["wordings"]).union(keys)),
                }
                retained["admitted"] = [
                    refreshed if e["episode_id"] == prior else e
                    for e in retained["admitted"]
                ]
                continue
        if not g.qualifies:
            continue
        identity = (
            prior
            or sha256(
                json.dumps([packet["cutoff"], keys], ensure_ascii=False).encode()
            ).hexdigest()[:24]
        )
        queued.append(
            {
                "episode_id": identity,
                "title": g.title,
                "reason": g.reason,
                "last_seen": last,
                "material_change": g.material_change,
                "headlines": members,
                "wordings": keys,
            }
        )
    queued.extend(e for e in retained["pending"] if e["episode_id"] not in handled)
    admitted, pending = queued[:2], queued[2:]
    updates = {e["episode_id"] for e in admitted}
    archive = [e for e in retained["admitted"] if e["episode_id"] not in updates]
    for e in admitted:
        record = {k: e[k] for k in ("episode_id", "title", "last_seen", "wordings")}
        if e["episode_id"] in earlier:
            record["wordings"] = sorted(
                set(earlier[e["episode_id"]]["wordings"]).union(e["wordings"])
            )
        archive.append(record)
    leads = [
        {**e, "rank": n, "headline_ids": [x["headline_id"] for x in e["headlines"]]}
        for n, e in enumerate(admitted, 1)
    ]
    return {
        "history": {
            "cutoff": packet["cutoff"],
            "seen": packet["seen"],
            "pending": pending,
            "admitted": archive,
        },
        "leads": leads,
        "ranked_stories": [g.model_dump() for g in groups],
        "expired": expired,
    }
