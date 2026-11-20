"""Deterministic tracked-subject matching, independent of harvest attribution.

Products remain exact identities. Containment uses only reviewed brand terms,
official handles, linked company labels and this matcher's own configuration.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config/promotion_subject_matching.yaml"
SHARED_HOSTS = frozenset({"github.com", "huggingface.co", "x.com", "twitter.com", "t.co"})
_HANDLE = re.compile(r"^@?([A-Za-z0-9_]{1,64})$")
_VERSION = re.compile(r"[a-z]{1,2}\d+(?:\.\d+)*(?:[a-z])?", re.IGNORECASE)
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _name(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()) if isinstance(value, str) else ""


def _handle(value: Any) -> str:
    match = _HANDLE.fullmatch(value.strip()) if isinstance(value, str) else None
    return match.group(1).casefold() if match else ""


def _domain(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    raw = value.strip().casefold()
    try:
        return (urlparse(raw if "://" in raw else f"https://{raw}").hostname or "").removeprefix("www.")
    except ValueError:
        return ""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} must be a list of nonempty terms")
    terms = tuple(item.strip() for item in value)
    if len({_name(item).casefold() for item in terms}) != len(terms):
        raise ValueError(f"{label} contains duplicate terms")
    return terms


@dataclass(frozen=True)
class MatchingConfig:
    global_excluded_terms: tuple[str, ...]
    brands: dict[str, dict[str, tuple[str, ...]]]
    digest: str

    def document(self) -> dict[str, Any]:
        return {
            "version": 1,
            "global_excluded_terms": sorted(self.global_excluded_terms, key=str.casefold),
            "brands": {
                key: {field: sorted(value, key=str.casefold) for field, value in row.items()}
                for key, row in sorted(self.brands.items())
            },
        }


def parse_matching_config(
    document: Any, *, known_brand_ids: Iterable[str] | None = None,
) -> MatchingConfig:
    """Validate a document; service boundaries also provide the brand registry.

    Pure callers can validate structure without a database. Runtime validation
    supplies all persisted brand IDs before a worker claims any posts.
    """
    if not isinstance(document, dict) or set(document) != {"version", "global_excluded_terms", "brands"}:
        raise ValueError("matcher config requires version, global_excluded_terms and brands only")
    if type(document["version"]) is not int or document["version"] != 1:
        raise ValueError("matcher config version must be 1")
    exclusions = _strings(document["global_excluded_terms"], "global_excluded_terms")
    rows = document["brands"]
    if not isinstance(rows, dict):
        raise ValueError("matcher config brands must be a mapping")  # noqa: TRY004 - Malformed context is part of the ValueError boundary contract.
    known = set(known_brand_ids) if known_brand_ids is not None else None
    brands = {}
    for brand_id, row in rows.items():
        if not isinstance(brand_id, str) or not brand_id.strip() or brand_id != brand_id.strip():
            raise ValueError("matcher config has an invalid brand nickname")
        if known is not None and brand_id not in known:
            raise ValueError(f"matcher config has unknown brand {brand_id!r}")
        if not isinstance(row, dict) or set(row) - {"excluded_terms", "extra_terms"}:
            raise ValueError(f"matcher config has unknown fields for {brand_id}")
        brands[brand_id] = {
            field: _strings(row.get(field, []), f"{brand_id}.{field}")
            for field in ("excluded_terms", "extra_terms")
        }
    config = MatchingConfig(exclusions, brands, "")
    return MatchingConfig(exclusions, brands, _digest(config.document()))


class _StrictLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in result:
                raise ValueError(f"matcher config has duplicate key {key!r}")
            result[key] = loader.construct_object(value_node, deep=deep)
        except TypeError as exc:
            raise ValueError("matcher config keys must be scalar values") from exc
    return result


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_matching_config(
    path: str | Path | None = None, *, known_brand_ids: Iterable[str] | None = None,
) -> MatchingConfig:
    """Load strict YAML and retain a digest of the actual shipped bytes."""
    source = Path(path or DEFAULT_CONFIG_PATH).read_bytes()
    try:
        document = yaml.load(source, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid matcher YAML: {exc}") from exc
    config = parse_matching_config(document, known_brand_ids=known_brand_ids)
    return MatchingConfig(config.global_excluded_terms, config.brands, hashlib.sha256(source).hexdigest())


@dataclass(frozen=True)
class SubjectMatch:
    tier: str
    owners: tuple[str, ...]
    matched_terms: tuple[str, ...]
    matcher_revision: str

    @property
    def matched_term(self) -> str:
        return self.matched_terms[0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier, "owners": list(self.owners),
            "matched_term": self.matched_term, "matched_terms": list(self.matched_terms),
            "matcher_revision": self.matcher_revision,
        }


def _values(row: Mapping[str, Any], fields: Iterable[str]) -> set[str]:
    return {
        cleaned for field in fields for raw in row.get(field) or []
        if (cleaned := _name(raw))
    }


def _right_boundary(value: str, end: int) -> bool:
    return end == len(value) or not value[end].isalnum() or value[end].isdigit() or value[end].isupper()


def _contains_name(value: str, term: str, pattern: re.Pattern[str]) -> bool:
    if _CJK.search(term):
        return term.casefold() in value.casefold()
    for match in pattern.finditer(value):
        if (match.start() == 0 or not value[match.start() - 1].isalnum()) and _right_boundary(value, match.end()):
            return True
    return False


def _contains_handle(value: Any, term: str, pattern: re.Pattern[str]) -> bool:
    if not isinstance(value, str) or not _HANDLE.fullmatch(value.strip()):
        return False
    for token in value.strip().removeprefix("@").split("_"):
        match = pattern.match(token)
        if match and _right_boundary(token, match.end()):
            return True
    return False


def _registrable_label(domain: str) -> str:
    labels = domain.split(".")
    # Conventional country-code second-level namespaces need one extra label.
    country_namespace = len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in {
        "ac", "co", "com", "edu", "gov", "net", "org",
    }
    return labels[-3] if country_namespace else labels[-2] if len(labels) >= 2 else ""


class PromotionSubjectMatcher:
    """Compile one read-only catalog and reuse it for discard and publication."""

    def __init__(
        self, catalog: Iterable[Any], *, config: MatchingConfig | None = None,
        company_terms: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        self.config = config or load_matching_config()
        companies = company_terms or {}
        self.rows = []
        for row in catalog:
            if not isinstance(row, dict) or not (brand_id := _name(row.get("brand_id"))):
                continue
            names = _values(row, ("aliases", "products", "keywords")) | {brand_id}
            accounts = [account for account in row.get("accounts") or [] if isinstance(account, dict)]
            handles = {_handle(raw) for raw in row.get("handles") or []}
            handles.update(_handle(account.get("handle")) for account in accounts)
            official = {_name(account.get("handle")) for account in accounts if account.get("role") == "official"}
            domains = {_domain(raw) for raw in row.get("domains") or []}
            options = self.config.brands.get(brand_id, {})
            excluded = {
                _name(value).casefold() for value in
                (*self.config.global_excluded_terms, *options.get("excluded_terms", ()))
            }
            candidates = (
                _values(row, ("aliases", "keywords")) | {brand_id} | official
                | {_name(value) for value in companies.get(brand_id, ())}
                | set(options.get("extra_terms", ()))
            )
            terms = sorted({term for term in candidates if term and term.casefold() not in excluded
                            and not _VERSION.fullmatch(term)}, key=lambda value: (value.casefold(), value))
            self.rows.append({
                "brand_id": brand_id, "names": sorted(names),
                "handles": sorted(handles - {""}), "domains": sorted(domains - {""}),
                "terms": terms,
            })
        self.rows.sort(key=lambda row: row["brand_id"])
        self.revision = _digest({"matcher_version": 1, "rows": self.rows, "config": self.config.document()})
        terms = {term for row in self.rows for term in row["terms"]}
        self._name_patterns = {term: re.compile(re.escape(term), re.IGNORECASE) for term in terms}
        self._handle_patterns = {
            term: re.compile(re.escape(term.removeprefix("@")), re.IGNORECASE) for term in terms
        }

    def match(self, subject: Mapping[str, Any], *, exact_only: bool = False) -> SubjectMatch | None:
        name = _name(subject.get("name"))
        handles = {_handle(subject.get(key)) for key in ("handle", "account_handle")} - {""}
        domain = _domain(subject.get("domain"))
        exact = []
        for row in self.rows:
            for term in row["names"]:
                if name and name.casefold() == term.casefold():
                    exact.append((row["brand_id"], term))
            for handle in handles.intersection(row["handles"]):
                exact.append((row["brand_id"], handle))
            if domain and domain in row["domains"]:
                exact.append((row["brand_id"], domain))
        if exact:
            return self._result("exact", exact)
        if exact_only:
            return None
        contained = []
        for row in self.rows:
            for known in row["domains"]:
                if known not in SHARED_HOSTS and domain.endswith("." + known):
                    contained.append((row["brand_id"], known))
            label = _registrable_label(domain) if domain not in SHARED_HOSTS else ""
            for term in row["terms"]:
                domain_hit = any(
                    token.casefold().startswith(term.casefold())
                    and (len(token) == len(term) or token[len(term)].isdigit())
                    for token in label.split("-")
                ) if label else False
                if (_contains_name(name, term, self._name_patterns[term])
                        or _contains_handle(subject.get("handle"), term, self._handle_patterns[term])
                        or domain_hit):
                    contained.append((row["brand_id"], term))
        return self._result("containment", contained) if contained else None

    def _result(self, tier: str, matches: list[tuple[str, str]]) -> SubjectMatch:
        return SubjectMatch(
            tier, tuple(sorted({owner for owner, _term in matches})),
            tuple(sorted({term for _owner, term in matches}, key=lambda value: (value.casefold(), value))),
            self.revision,
        )
