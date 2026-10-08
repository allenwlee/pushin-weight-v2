"""Bounded historical acquisition; source evidence stays separate from identity review."""

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from .identity import require


def date_chunks(start, end, *, size=90):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    require(1 <= size <= 366 and first <= last, "invalid history window")
    while first <= last:
        stop = min(last, first + timedelta(days=size - 1))
        yield first.isoformat(), stop.isoformat()
        first = stop + timedelta(days=1)


def reconstruct_counts(timestamps, *, retrieved_at):
    """Arrival curve of surviving relationships, never a historical stock claim."""
    now = datetime.fromisoformat(retrieved_at)
    require(now.tzinfo is not None, "retrieval offset required")
    counts = Counter()
    for value in timestamps:
        instant = datetime.fromisoformat(value)
        require(instant.tzinfo is not None, "relationship offset required")
        require(instant <= now, "relationship after retrieval")
        counts[instant.astimezone(UTC).date()] += 1
    result = {}
    total = 0
    if counts:
        current, last = min(counts), now.astimezone(UTC).date() - timedelta(days=1)
        while current <= last:
            total += counts[current]
            result[current.isoformat()] = total
            current += timedelta(days=1)
    return {
        "counts": result,
        "history_basis": "reconstructed_current_relationships",
        "includes_removed_relationships": False,
        "retrieved_at": retrieved_at,
        "source_timezone": "UTC",
        "relationship_count": len(timestamps),
    }


def hf_relationship_history(client, identifier, *, kind, max_pages=100):
    """Use the bounded metadata client and discard individual identities at source."""
    import hashlib
    import json
    import re
    from urllib.parse import parse_qs, urlparse

    from core.hf_metadata_client import NAMESPACE, REPO_ID

    require(
        kind in {"repository", "organization", "individual"},
        "invalid relationship kind",
    )
    require(
        bool((REPO_ID if kind == "repository" else NAMESPACE).fullmatch(identifier)),
        "invalid HF identifier",
    )
    path = (
        f"/models/{identifier}/likers"
        if kind == "repository"
        else f"/{'organizations' if kind == 'organization' else 'users'}/{identifier}/followers"
    )
    field = "likedAt" if kind == "repository" else "followedAt"
    params = [("expand[]", field)]
    if kind != "repository":
        params.append(("limit", "10000"))
    timestamps, seen, cursors, hashes = [], set(), set(), []
    for _ in range(max_pages):
        result = client._get(path, params)
        require(
            result.outcome == "ok" and isinstance(result.payload, list),
            "HF relationship page unavailable",
        )
        hashes.append(
            hashlib.sha256(
                json.dumps(result.payload, sort_keys=True).encode()
            ).hexdigest()
        )
        for row in result.payload:
            require(
                isinstance(row, dict)
                and row.get("_id")
                and isinstance(row.get(field), str),
                "missing relationship timestamp",
            )
            require(row["_id"] not in seen, "duplicate relationship across pages")
            seen.add(row["_id"])
            timestamps.append(row[field])
        link = result.attempts[-1].get("link", "")
        matches = re.findall(r'<([^>]+)>;\s*rel="next"', link)
        if not matches:
            require("next" not in link, "invalid HF continuation")
            report = reconstruct_counts(
                timestamps, retrieved_at=datetime.now(UTC).isoformat()
            )
            report.update(
                identifier=identifier,
                kind=kind,
                pages=len(hashes),
                page_sha256=hashes,
                endpoint="https://huggingface.co/api" + path,
            )
            return report
        require(
            len(matches) == 1 and kind != "repository", "unexpected HF continuation"
        )
        url = urlparse(matches[0])
        query = parse_qs(url.query)
        require(
            url.scheme == "https"
            and url.netloc == "huggingface.co"
            and url.path == "/api" + path
            and not url.fragment,
            "foreign HF continuation",
        )
        cursor = query.get("cursor", [])
        require(len(cursor) == 1 and cursor[0] not in cursors, "duplicate HF cursor")
        cursors.add(cursor[0])
        params = [("expand[]", field), ("limit", "10000"), ("cursor", cursor[0])]
    raise ValueError("HF relationship page budget exceeded")
