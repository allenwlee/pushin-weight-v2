"""Code-only preparation boundary. Adapters own queries and editorial policy."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


def encode(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def packet_bytes(value):
    # Preserve the existing editorial byte accounting, including JSON spaces.
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


@dataclass(frozen=True)
class PacketProfile:
    key: str
    version: int
    cutoff: str
    max_bytes: int
    settings_json: bytes

    @classmethod
    def create(
        cls, key: str, *, cutoff: datetime, max_bytes: int, settings=None, version=1
    ):
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("packet cutoff requires a timezone")
        if not key or version < 1 or max_bytes < 1:
            raise ValueError("invalid packet profile")
        return cls(key, version, cutoff.isoformat(), max_bytes, encode(settings or {}))


@dataclass(frozen=True)
class PreparedPacket:
    profile: PacketProfile
    reuse_key: str
    encoded: bytes

    @property
    def payload(self):
        # A caller can modify its working copy without changing a saved packet.
        return json.loads(self.encoded)


def make_packet(
    profile: PacketProfile,
    collect: Callable[[], dict],
    *,
    transform: Callable[[dict], dict] | None = None,
    project: Callable[[dict], dict] | None = None,
) -> PreparedPacket:
    """Collect once, transform whole rows, project, enforce bounds, freeze.

    The reuse identity includes private input revisions and configuration even
    when the provider projection omits them. This function never sends a request
    or reserves a call, and supplies no provider client to an adapter.
    """
    raw = collect()
    identity = sha256(
        encode(
            {
                "profile": [
                    profile.key,
                    profile.version,
                    profile.cutoff,
                    profile.max_bytes,
                    json.loads(profile.settings_json),
                ],
                "input": raw,
            }
        )
    ).hexdigest()
    working = json.loads(encode(raw))
    if transform is not None:
        working = transform(working)
    if project is not None:
        working = project(working)
    encoded = encode(working)
    if len(encoded) > profile.max_bytes:
        raise ValueError("packet byte limit exceeded")
    return PreparedPacket(profile, identity, encoded)


def evidence_identity(packet, settings):
    """Skip unchanged inputs without treating the advancing clock as new evidence."""
    return sha256(
        encode(
            {
                "settings": settings,
                "evidence": {
                    key: packet.get(key)
                    for key in (
                        "posts",
                        "context",
                        "people",
                        "headline_leads",
                        "chart_context",
                    )
                },
            }
        )
    ).hexdigest()
