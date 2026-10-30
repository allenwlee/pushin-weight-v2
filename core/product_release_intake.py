"""Source-first release intake, independent of catalogue, ORM and providers.

A candidate is one source needing reconciliation, not a verified release or a
cross-post event. Keep its entire evidence packet: one post can describe several
products, and repository links can point at teachers rather than the release.
Persistence and acquisition adapters must preserve these distinctions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

RULE_VERSION = "product-release-intake-v1"
RELEASE_LABELS = frozenset(
    {
        "model_release",
        "model_releases",
        "product_release",
        "product_releases",
        "releases_updates",
    }
)
_RELEASE = re.compile(
    r"\b(?:releas(?:e[ds]?|ing)|launch(?:ed|es|ing)?|introduc(?:e[ds]?|ing)|"
    r"unveil(?:ed|s|ing)?|announc(?:e[ds]?|ing)|now available|available now|"
    r"open[- ]sourc(?:e[ds]?|ing)|open[- ]weights?|new (?:model|checkpoint|agent|harness))\b|"
    r"发布|發布|推出|上线|上線|开源|開源|正式开放|正式開放|新模型|リリース|公開",
    re.IGNORECASE,
)
_FUTURE = re.compile(
    r"\b(?:rumou?r|unconfirmed|might|may release|will release|will launch|coming soon|"
    r"expected|reportedly|could launch|tomorrow|next week)\b|传闻|傳聞|据传|據傳|即将|即將|预计|預計|明天|下周",
    re.IGNORECASE,
)
_NEGATED = re.compile(
    r"\b(?:not|never|isn't|hasn't|haven't|won't|no)\b.{0,40}\b(?:release|launch|announc)|尚未|未发布|未發布|まだ.*(?:ない|ません)",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://[^\s<>\"\[\]]+", re.IGNORECASE)
_SEGMENT = re.compile(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]*\Z")
_VERSIONED_NAME = re.compile(
    r"(?<![\w@/])(?=[A-Za-z][A-Za-z0-9_.-]{2,79}(?![\w.-]))"
    r"(?=[A-Za-z0-9_.-]*[0-9])[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*"
)


def _required(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")


@dataclass(frozen=True)
class TextEvidence:
    locator: str
    kind: Literal["raw", "quote", "translation", "commentary", "release_extraction"]
    text: str

    def __post_init__(self):
        _required(self.locator, "locator")
        if self.kind not in {
            "raw",
            "quote",
            "translation",
            "commentary",
            "release_extraction",
        }:
            raise ValueError("Unknown text evidence kind")
        if not isinstance(self.text, str):
            raise TypeError("Evidence text must be a string")


@dataclass(frozen=True)
class SavedLabel:
    value: str
    locator: str

    def __post_init__(self):
        _required(self.value, "label")
        _required(self.locator, "locator")


@dataclass(frozen=True)
class URLReference:
    url: str
    locator: str

    def __post_init__(self):
        _required(self.url, "url")
        _required(self.locator, "locator")


@dataclass(frozen=True)
class FraudDecision:
    """An existing explicit decision; the detector never creates one from text."""

    kind: Literal["fake", "scam"]
    locator: str
    reason: str

    def __post_init__(self):
        if self.kind not in {"fake", "scam"}:
            raise ValueError("Only evidenced fake/scam decisions exclude releases")
        _required(self.locator, "fraud evidence locator")
        _required(self.reason, "fraud reason")


@dataclass(frozen=True)
class SourceRecord:
    namespace: str
    source_id: str
    texts: tuple[TextEvidence, ...] = ()
    labels: tuple[SavedLabel, ...] = ()
    urls: tuple[URLReference, ...] = ()
    is_reshare: bool = False
    fraud: FraudDecision | None = None

    def __post_init__(self):
        _required(self.namespace, "namespace")
        _required(self.source_id, "source_id")
        for name, cls in (
            ("texts", TextEvidence),
            ("labels", SavedLabel),
            ("urls", URLReference),
        ):
            rows = getattr(self, name)
            if not isinstance(rows, tuple) or any(
                not isinstance(row, cls) for row in rows
            ):
                raise ValueError(f"{name} must be an immutable tuple of {cls.__name__}")
            if len({row.locator for row in rows}) != len(rows):
                raise ValueError(f"Duplicate {name} evidence locator")
        if not isinstance(self.is_reshare, bool):
            raise TypeError("is_reshare must be boolean")
        if self.fraud is not None and not isinstance(self.fraud, FraudDecision):
            raise ValueError("fraud must be an explicit FraudDecision")

    @property
    def identity(self) -> tuple[str, str]:
        return self.namespace, self.source_id


@dataclass(frozen=True)
class ReleaseSignal:
    kind: Literal["release_wording", "saved_label", "saved_extraction"]
    locator: str
    excerpt: str
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class RepositoryReference:
    provider: str
    repository_type: str
    native_identifier: str
    url: str
    locator: str


@dataclass(frozen=True)
class ReleaseCandidate:
    key: str
    source: SourceRecord
    signals: tuple[ReleaseSignal, ...]
    references: tuple[RepositoryReference, ...]
    cautions: tuple[str, ...]
    disposition: Literal["pending", "excluded"]
    rule_version: str = RULE_VERSION


def _repository_reference(ref: URLReference) -> RepositoryReference | None:
    # Parse saved links only. No redirect resolution, verification or URL fetch.
    try:
        url = urlsplit(ref.url)
        if (
            url.scheme not in {"http", "https"}
            or url.username
            or url.password
            or url.port not in {None, 80, 443}
        ):
            return None
    except ValueError:
        return None
    host = (url.hostname or "").lower().removeprefix("www.")
    parts = url.path.strip("/").split("/")
    if any(part in {".", ".."} for part in parts):
        return None
    if host == "huggingface.co":
        provider, kind = "huggingface", "model"
        if parts[0] in {"spaces", "datasets"}:
            kind = {"spaces": "space", "datasets": "dataset"}[parts.pop(0)]
        elif parts[0] in {
            "docs",
            "collections",
            "api",
            "organizations",
            "settings",
            "blog",
            "join",
            "login",
        }:
            return None
    elif host == "github.com":
        provider, kind = "github", "repository"
        if parts[0].lower() in {
            "login",
            "settings",
            "features",
            "topics",
            "marketplace",
            "orgs",
            "users",
            "search",
            "sponsors",
        }:
            return None
        if len(parts) >= 2:
            parts[1] = parts[1].removesuffix(".git")
    else:
        return None
    if len(parts) < 2 or any(not _SEGMENT.fullmatch(part) for part in parts[:2]):
        return None
    return RepositoryReference(
        provider, kind, "/".join(parts[:2]), ref.url, ref.locator
    )


def detect(source: SourceRecord) -> ReleaseCandidate | None:
    """Retain source evidence for reconciliation, without asserting a release fact."""
    signals = []
    raw_signal = False
    saved_signal = False
    cautions = set()
    references = list(source.urls)
    for evidence in source.texts:
        matches = tuple(_RELEASE.finditer(evidence.text))
        signals.extend(
            ReleaseSignal(
                "release_wording", evidence.locator, m.group(), m.start(), m.end()
            )
            for m in matches
        )
        raw_signal |= evidence.kind == "raw" and bool(matches)
        saved_signal |= evidence.kind not in {"raw", "quote"} and bool(matches)
        if evidence.kind == "quote" and matches:
            cautions.add("quoted_context")
        if evidence.kind == "release_extraction" and evidence.text.strip():
            saved_signal = True
            signals.append(
                ReleaseSignal("saved_extraction", evidence.locator, evidence.text)
            )
        if _FUTURE.search(evidence.text):
            cautions.add("future_or_uncertain")
        if _NEGATED.search(evidence.text):
            cautions.add("negated")
        if "?" in evidence.text or "？" in evidence.text:
            cautions.add("question")
        references.extend(
            URLReference(
                m.group().rstrip(".,;:!?)）"),
                f"{evidence.locator}#chars={m.start()}:{m.end()}",
            )
            for m in _URL.finditer(evidence.text)
        )
    label_signals = tuple(
        ReleaseSignal("saved_label", label.locator, label.value)
        for label in source.labels
        if label.value in RELEASE_LABELS
    )
    signals.extend(label_signals)
    if not signals:
        return None
    if not raw_signal and (saved_signal or label_signals):
        cautions.add("saved_evidence_only")
    if source.is_reshare:
        cautions.add("reshare")
    repos = tuple(
        dict.fromkeys(
            parsed
            for ref in references
            if (parsed := _repository_reference(ref)) is not None
        )
    )
    key = hashlib.sha256(
        json.dumps(source.identity, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return ReleaseCandidate(
        key,
        source,
        tuple(signals),
        repos,
        tuple(sorted(cautions)),
        "excluded" if source.fraud else "pending",
    )


def search_leads(candidate: ReleaseCandidate) -> tuple[dict, ...]:
    """Expose saved release names as attributable search leads, not identities.

    Keep ineligible names visible for later resolution. Repository references are
    deliberately excluded: they can name teachers or comparison models.
    """
    leads = []
    for evidence in candidate.source.texts:
        if evidence.kind != "release_extraction" or not evidence.text.strip():
            continue
        term = " ".join(evidence.text.split())
        leads.append(
            {
                "term": term,
                "locator": evidence.locator,
                "eligible": len(term) <= 256
                and any(char.isalnum() for char in term)
                and not _URL.search(term),
            }
        )
    return tuple(leads)


def raw_versioned_name_leads(text: str, *, limit: int = 3) -> tuple[dict, ...]:
    """Find bounded, source-verbatim search terms; never assert product identity.

    This deliberately misses unversioned names. All hits, including teacher
    names and unrelated version strings, remain provisional search leads.
    """
    if not isinstance(text, str) or type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Text and a name lead limit between 1 and 10 are required")
    anchors = list(_RELEASE.finditer(text))
    if not anchors:
        return ()
    urls = [match.span() for match in _URL.finditer(text)]
    found = {}
    for match in _VERSIONED_NAME.finditer(text):
        if any(start <= match.start() < end for start, end in urls):
            continue
        term = match.group().rstrip("-_.")
        if len(term) < 3:
            continue
        distance = min(abs(match.start() - anchor.end()) for anchor in anchors)
        found.setdefault(term.casefold(), {
            "term": term, "start": match.start(), "end": match.start() + len(term),
            "distance": distance,
        })
    ranked = sorted(found.values(), key=lambda row: (row["distance"], row["start"]))[:limit]
    return tuple({key: row[key] for key in ("term", "start", "end")} for row in ranked)
