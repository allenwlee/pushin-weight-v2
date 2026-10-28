"""Seed, and later switch off, the OpenAI/Anthropic size-test brands in xbackfiller.

Branch-only operator for
``docs/plans/2026-10-27-113859-ops-oai-anthropic-size-20261027-plan.md``
(U1 seed data, U10 switch-off). It never touches production: both database
subcommands refuse to run unless ``X_MONITOR_DEPLOYMENT_ENVIRONMENT`` is
``backfill`` and the connected database's ``current_database()`` and
``session_user`` are both ``xbackfiller`` (the rule ``validate_staging`` applies
to dedicated backfill scopes).

Subcommands
-----------
``build``
    Write the keyword and roster CSVs from the frozen query file, the lab-list
    roster JSON and the recorded evidence spellings. No database access.
``seed --keywords CSV --roster CSV --undo-receipt PATH``
    Create the literal BrandKeyword, Account and BrandAccount rows through
    ``onboard_brand --csv``, then the TwitterListMembership rows for the two
    lab lists, and write an undo receipt naming every catalog-relevant row the
    seed created or changed. Context gating is not a database property: it
    lives in ``config/harvest_policy.yaml`` ``alias_context`` and is checked
    against the keyword CSV before any write. A second seed is refused while
    the brands still carry keywords.
``switch-off --undo-receipt PATH``
    Refuse while any historical backfill run holds a live lease, then undo
    exactly what the receipt records and require the classifier catalog
    revision to equal the one recorded before the seed (R9, KTD10). The
    ``openai`` and ``anthropic`` Brand rows already exist as alias-only,
    non-sentinel rows in production and xbackfiller, so marking them sentinel
    would make July's catalog differ from production's; restoring the
    pre-seed rows keeps it identical. PostBrand rows and the test's stored
    data are kept.

Run from the repository root, e.g. ``python -m scripts.backfill_size_seed seed
--keywords docs/analysis/...-oai-anthropic-keywords.csv --roster
docs/analysis/...-oai-anthropic-roster.csv``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from x_monitor.harvest_policy import normalize_policy_token

FROZEN_QUERIES_SHA256 = "3d2c9c17114bd3de7a7070c60e35ad14eb54236fbf2efd048f657e804c994dec"
BRANDS = ("openai", "anthropic")
ROUTES = {
    "openai": ("A_OAI", "OAI_1", "OAI_2", "OAI_3", "B_OAI"),
    "anthropic": ("A_ANT", "ANT_1", "ANT_2", "ANT_3", "B_ANT"),
}
PRIMARY_KEYWORDS = {"openai": "OpenAI", "anthropic": "Anthropic"}
DISPLAY = {"openai": ("OpenAI", "#10a37f"), "anthropic": ("Anthropic", "#d97757")}
LAB_LISTS = {"openai": 2067500935769895374, "anthropic": 2067501173402460553}
ROSTER_KEYS = {"OpenAI": "openai", "Anthropic": "anthropic"}
# Lab-list roles (owner decision): these are official, every other member staff.
OFFICIAL_HANDLES = {
    "openai": ("OpenAI", "OpenAIDevs", "OpenAINewsroom"),
    "anthropic": ("AnthropicAI", "claudeai", "ClaudeDevs", "claude_code"),
}
EXPECTED_ROLE_COUNTS = {
    "openai": {"official": 3, "staff": 26},
    "anthropic": {"official": 4, "staff": 15},
}
# Handle strings that are also ordinary words get their brand's context words.
COMMON_WORD_HANDLES = frozenset({"sama"})
MEMBERSHIP_SOURCE = "size-test-roster"
SEED_NOTES = (
    "OpenAI/Anthropic size test (branch ops/oai-anthropic-size-20261027); "
    "dedicated xbackfiller database only"
)

KEYWORD_FIELDS = ("brand", "pattern", "is_regex", "context_gated", "context_words", "source")
ROSTER_FIELDS = ("list_id", "brand", "author_id", "username", "role")
ROLE_ORDER = ("official", "staff")

# Read-only production queries behind the evidence spellings (render psql
# dpg-d9koekqjobas73fvjqng-a, each wrapped in BEGIN TRANSACTION READ ONLY ...
# ROLLBACK, 2026-10-28). brand_discovery_candidate_tokens held 0 rows.
EVIDENCE_QUERIES = {
    "E1": (
        "SELECT observed_name, count(*) AS n FROM untracked_brand_promotion_evidence "
        "WHERE observed_name ~* '(open.?a|clos.?ai|chat.?g|cha.?gpt|gpt|anth|antr|athrop|"
        "claude|クロード|codex|sora|dall|altman|amodei|opus|sonnet|haiku|fable|mythos|オープン|"
        "オープンAI|앤트|오픈|챗|チャット|whisper|stargate|o3|o4|o1)' GROUP BY 1 ORDER BY 2 DESC LIMIT 400"
    ),
    "E2": (
        "SELECT 'alias', a, count(*) FROM untracked_brand_promotion_evidence e, "
        "jsonb_array_elements_text(e.aliases) a WHERE a ~* '(open.?a|clos.?ai|chat.?g|cha.?gpt|gpt|"
        "anth|antr|athrop|claude|codex|sora|dall|altman|amodei|opus|sonnet|haiku|fable|mythos|オープン|"
        "앤트|오픈|챗|チャット|クロード|클로드|克劳德)' GROUP BY 1,2 UNION ALL SELECT 'handle', h, count(*) "
        "FROM untracked_brand_promotion_evidence e, jsonb_array_elements_text(e.handles) h WHERE h ~* "
        "'(openai|chatgpt|anthropic|claude|codex|sora|sama|dario)' GROUP BY 1,2 UNION ALL SELECT "
        "'product', p, count(*) FROM untracked_brand_promotion_evidence e, "
        "jsonb_array_elements_text(e.products) p WHERE p ~* '(open.?a|chat.?g|gpt|anth|claude|codex|"
        "sora|dall|opus|sonnet|haiku|fable|mythos)' GROUP BY 1,2 ORDER BY 1, 3 DESC LIMIT 600"
    ),
    "E3": (
        "SELECT 'name', observed_name, count(*) FROM brand_discovery_candidates WHERE observed_name ~* "
        "'^(open ?ai|openal|openia|closed ?ai|closeai|chat ?g[a-z]*t|cha[a-z]?gpt|anthrop|antro|anthro|"
        "athrop|authrop|claude|chatgpt|codex|sora|altman|amodei|オープン|앤트|오픈|챗|チャット|クロード|클로드|"
        "克劳德|アンソロ|アンスロ|奥特曼|阿尔特曼|人择)' GROUP BY 1,2 UNION ALL SELECT 'alias', a, count(*) "
        "FROM brand_discovery_candidates c, jsonb_array_elements_text(c.aliases) a WHERE a ~* <same> "
        "GROUP BY 1,2 UNION ALL SELECT 'handle', h, count(*) FROM brand_discovery_candidates c, "
        "jsonb_array_elements_text(c.candidate_handles) h WHERE h ~* "
        "'(openai|chatgpt|anthropic|claude|codex|sora|sama|dario)' GROUP BY 1,2 ORDER BY 1, 3 DESC LIMIT 400"
    ),
}
# Lab-owned product/model spellings observed in that evidence, as exact values.
# Third-party products (OpenArt, NanoGPT, free-claude-code, Claude Code Router,
# ...) and descriptive phrases are excluded. Spellings already present in the
# frozen routes, or equal to a context-gated alias, are dropped by the builder.
EVIDENCE_SPELLINGS: tuple[tuple[str, str, str], ...] = (
    ("openai", "ChatGPT Plus", "E1+E2+E3"),
    ("openai", "ChatGPT Pro", "E1+E2+E3"),
    ("openai", "ChatGPT Go", "E1+E2+E3"),
    ("openai", "ChatGPT Codex", "E1+E2+E3"),
    ("openai", "ChatGPT desktop", "E1+E2+E3"),
    ("openai", "ChatGPT Luna", "E1+E2+E3"),
    ("openai", "ChatGPT 6.1 Sol", "E1+E2+E3"),
    ("openai", "chatgpt", "E2+E3"),
    ("openai", "GPT-5.6", "E1+E2"),
    ("openai", "GPT-6 Astra", "E1+E2"),
    ("openai", "gpt-6-astra", "E1+E2"),
    ("openai", "GPT-6 Luna", "E1+E2"),
    ("openai", "GPT-6-Luna", "E1+E2"),
    ("openai", "GPT-6.1 Terra", "E1+E2"),
    ("openai", "GPT LUNA", "E1+E2"),
    ("openai", "GPT Image", "E1+E2"),
    ("openai", "GPT Image 2.5", "E1+E2"),
    ("openai", "GPT OSS", "E1+E2"),
    ("openai", "Dall-E", "E1+E2"),
    ("openai", "OpenAI API", "E1+E2+E3"),
    ("openai", "OpenAI SDK", "E1+E2+E3"),
    ("openai", "OpenAI Agents SDK", "E1+E2+E3"),
    ("openai", "OpenAI Dot", "E1+E2+E3"),
    ("openai", "OpenAI ImageGen", "E1+E2+E3"),
    ("openai", "Sora", "E1+E2+E3"),
    ("anthropic", "Claude Code", "E1+E2+E3"),
    ("anthropic", "claude-code", "E1+E2+E3"),
    ("anthropic", "claudecode", "E2+E3"),
    ("anthropic", "Claude Pro", "E1+E2+E3"),
    ("anthropic", "Claude Opus 5.5", "E1+E2+E3"),
    ("anthropic", "Claude Sonnet 5", "E1+E2+E3"),
    ("anthropic", "Claude Haiku 5.5", "E1+E2+E3"),
    ("anthropic", "Claude Fable 5", "E1+E2+E3"),
    ("anthropic", "Claude Duet", "E1+E2+E3"),
    ("anthropic", "Claude Marketplace", "E1+E2+E3"),
    ("anthropic", "Claude Plugins", "E1+E2+E3"),
    ("anthropic", "Anthropic Skills", "E1+E2+E3"),
    ("anthropic", "Anthropic Claude", "E1+E2+E3"),
    ("anthropic", "haiku-5.5", "E1+E2"),
    ("anthropic", "anthropics", "E3"),
    ("anthropic", "Fable", "E1+E2"),
    ("anthropic", "Mythos", "E1+E2"),
    ("anthropic", "opus", "E1+E2"),
)


class SeedRefused(RuntimeError):
    """A precondition failed; nothing was written."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise SeedRefused(message)


# ---------------------------------------------------------------------------
# Frozen query parsing
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r'\(|\)|"[^"]*"|[^\s()]+')


def _query_body(text: str) -> str:
    body, marker, _rest = text.partition(" min_faves:")
    _require(marker, "frozen query lacks the min_faves suffix")
    return body.strip()


def _unquote(token: str) -> str:
    return token[1:-1] if len(token) >= 2 and token[0] == token[-1] == '"' else token


def parse_query(text: str) -> tuple:
    """Parse one frozen X search into ("term"|"or"|"and", ...) nodes.

    Juxtaposition (AND) binds tighter than OR, as in X advanced search.
    """
    tokens = _TOKEN_RE.findall(_query_body(text))

    def combine(disjuncts: list[list[tuple]]) -> tuple:
        _require(all(disjuncts), "empty search operand")
        conjuncts = [d[0] if len(d) == 1 else ("and", tuple(d)) for d in disjuncts]
        return conjuncts[0] if len(conjuncts) == 1 else ("or", tuple(conjuncts))

    def group(pos: int, depth: int) -> tuple[tuple, int]:
        disjuncts: list[list[tuple]] = [[]]
        while pos < len(tokens):
            token = tokens[pos]
            if token == "(":
                node, pos = group(pos + 1, depth + 1)
                disjuncts[-1].append(node)
            elif token == ")":
                _require(depth > 0, "unbalanced parenthesis")
                return combine(disjuncts), pos + 1
            elif token == "OR":
                _require(disjuncts[-1], "dangling OR")
                disjuncts.append([])
                pos += 1
            else:
                disjuncts[-1].append(("term", _unquote(token)))
                pos += 1
        _require(depth == 0, "unbalanced parenthesis")
        return combine(disjuncts), pos

    node, _ = group(0, 0)
    return node


def _leaves(node: tuple) -> list[str]:
    kind, value = node
    if kind == "term":
        return [value]
    _require(kind == "or", "unexpected AND inside a term group")
    return [term for child in value for term in _leaves(child)]


def route_terms(text: str) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Return (kind, terms, context words) for one frozen route.

    kind is "list" (list:<id> search, no keywords), "handles" (@ handles,
    returned without "@"), "gated" (``(terms) (context)``) or "standalone".
    """
    node = parse_query(text)
    if node[0] == "and":
        _require(len(node[1]) == 2, "gated route must be (terms) (context)")
        return "gated", tuple(_leaves(node[1][0])), tuple(_leaves(node[1][1]))
    terms = _leaves(node)
    if all(term.startswith("list:") for term in terms):
        return "list", (), ()
    if all(term.startswith("@") for term in terms):
        return "handles", tuple(term[1:] for term in terms), ()
    _require(not any(term.startswith(("@", "list:")) for term in terms), "mixed route terms")
    return "standalone", tuple(terms), ()


# ---------------------------------------------------------------------------
# Keyword table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeywordRow:
    brand: str
    pattern: str
    context_gated: bool
    context_words: tuple[str, ...]
    source: str


def build_keyword_rows(frozen: dict[str, Any]) -> list[KeywordRow]:
    """Every literal frozen route term, handle string and evidence spelling.

    Terms used unconditionally by a standalone route (or a non-word handle)
    stay unconditional; terms found only in the gated pack, and handles that
    are ordinary words, carry that brand's context words.
    """
    routes = {row["name"]: row["text"] for row in frozen["new"]}
    rows: list[KeywordRow] = []
    owners: dict[str, str] = {}
    for brand in BRANDS:
        candidates: list[tuple[str, str, bool]] = []  # (pattern, source, gated)
        context: tuple[str, ...] = ()
        for name in ROUTES[brand]:
            kind, terms, words = route_terms(routes[name])
            if kind == "gated":
                _require(not context, f"{brand}: more than one gated route")
                context = words
            for term in terms:
                if kind == "handles":
                    gated = term.casefold() in COMMON_WORD_HANDLES
                    candidates.append((term, f"frozen:{name}:handle", gated))
                else:
                    candidates.append((term, f"frozen:{name}", kind == "gated"))
        for handle in OFFICIAL_HANDLES[brand]:
            candidates.append((handle, "roster:official-handle", handle.casefold() in COMMON_WORD_HANDLES))
        _require(context, f"{brand}: gated route missing")
        unconditional = {normalize_policy_token(p) for p, _source, gated in candidates if not gated}
        gated_terms = {normalize_policy_token(p) for p, _source, gated in candidates if gated} - unconditional
        for brand_name, spelling, queries in EVIDENCE_SPELLINGS:
            if brand_name == brand:
                candidates.append((spelling, f"evidence:{queries}", False))
        emitted: set[str] = set()
        for pattern, source, gated in candidates:
            key = normalize_policy_token(pattern)
            if key in emitted:
                continue
            if source.startswith("evidence:") and key in gated_terms:
                continue  # evidence never ungates a context-gated alias
            if key in gated_terms and not gated:
                continue  # emitted from its gated source instead
            if key not in gated_terms and gated:
                continue  # an unconditional source owns this term
            emitted.add(key)
            prior = owners.setdefault(key, brand)
            _require(prior == brand, f"keyword {pattern!r} claimed by {prior} and {brand}")
            rows.append(KeywordRow(
                brand=brand,
                pattern=pattern,
                context_gated=key in gated_terms,
                context_words=context if key in gated_terms else (),
                source=source,
            ))
        first = next((r for r in rows if r.brand == brand), None)
        _require(first is not None and first.pattern == PRIMARY_KEYWORDS[brand],
                 f"{brand}: primary keyword must lead the table")
    for row in rows:
        _require("|" not in row.pattern and row.pattern == row.pattern.strip(), f"unsafe pattern {row.pattern!r}")
    return rows


def _keyword_header() -> list[str]:
    lines = [
        "OpenAI/Anthropic size-test keyword table: branch ops/oai-anthropic-size-20261027,",
        "dedicated xbackfiller database only. Built by scripts/backfill_size_seed.py build.",
        f"Frozen routes: docs/analysis/2026-10-27-215214-oai-anthropic-frozen-queries.json sha256 {FROZEN_QUERIES_SHA256}.",
        "context_gated rows need one of context_words in the post (config/harvest_policy.yaml alias_context).",
        "Evidence spellings: read-only production queries on 2026-10-28 (render psql dpg-d9koekqjobas73fvjqng-a):",
    ]
    lines.extend(f"{key}: {sql}" for key, sql in EVIDENCE_QUERIES.items())
    return [f"# {line}" for line in lines]


def keyword_csv_bytes(rows: list[KeywordRow]) -> bytes:
    stream = io.StringIO()
    stream.write("\n".join(_keyword_header()) + "\n")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(KEYWORD_FIELDS)
    for row in rows:
        writer.writerow((
            row.brand, row.pattern, "false", "true" if row.context_gated else "false",
            "|".join(row.context_words), row.source,
        ))
    return stream.getvalue().encode("utf-8")


def _csv_records(text: str, fields: tuple[str, ...]) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    reader = csv.DictReader(lines, strict=True)
    _require(tuple(reader.fieldnames or ()) == fields, f"CSV header must be {','.join(fields)}")
    records = []
    for record in reader:
        _require(None not in record and all(v is not None for v in record.values()), "malformed CSV row")
        records.append(record)
    return records


def read_keyword_csv(path: Path) -> list[KeywordRow]:
    rows = []
    seen: set[str] = set()
    for record in _csv_records(Path(path).read_text(encoding="utf-8"), KEYWORD_FIELDS):
        _require(record["brand"] in BRANDS, f"unknown brand {record['brand']!r}")
        _require(record["is_regex"] == "false", "size-test keywords are literal")
        _require(record["context_gated"] in {"true", "false"}, "context_gated must be true/false")
        gated = record["context_gated"] == "true"
        words = tuple(w for w in record["context_words"].split("|") if w)
        _require(gated == bool(words), f"context words disagree with gating for {record['pattern']!r}")
        key = normalize_policy_token(record["pattern"])
        _require(key and key not in seen, f"duplicate or empty keyword {record['pattern']!r}")
        seen.add(key)
        rows.append(KeywordRow(record["brand"], record["pattern"], gated, words, record["source"]))
    for brand in BRANDS:
        own = [row for row in rows if row.brand == brand]
        _require(own and own[0].pattern == PRIMARY_KEYWORDS[brand], f"{brand}: primary keyword must lead")
    return rows


def check_policy_alignment(rows: list[KeywordRow], policy: Any) -> None:
    """The gated CSV rows must be exactly the policy's alias_context rules."""
    for brand in BRANDS:
        _require(brand in policy.brands, f"{brand} missing from harvest policy")
        entry = policy.brands[brand]
        _require(entry.paths == frozenset({"none"}), f"{brand} must use paths: [none]")
        expected = {
            normalize_policy_token(row.pattern): tuple(row.context_words)
            for row in rows if row.brand == brand and row.context_gated
        }
        actual = {normalize_policy_token(rule.alias): tuple(rule.any_of) for rule in entry.alias_context}
        _require(actual == expected, f"{brand}: alias_context differs from the keyword CSV gating")
        _require({normalize_policy_token(t) for t in entry.tokens} == set(expected),
                 f"{brand}: policy tokens must be exactly the gated aliases")


# ---------------------------------------------------------------------------
# Roster table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RosterRow:
    list_id: int
    brand: str
    author_id: str
    username: str
    role: str


_HANDLE_RE = re.compile(r"[A-Za-z0-9_]{1,15}\Z")


def _validate_roster(rows: list[RosterRow]) -> list[RosterRow]:
    for brand in BRANDS:
        own = [row for row in rows if row.brand == brand]
        officials = {row.username.casefold() for row in own if row.role == "official"}
        _require(officials == {h.casefold() for h in OFFICIAL_HANDLES[brand]},
                 f"{brand}: official accounts must be exactly {', '.join(OFFICIAL_HANDLES[brand])}")
        counts = {role: sum(row.role == role for row in own) for role in ROLE_ORDER}
        _require(counts == EXPECTED_ROLE_COUNTS[brand], f"{brand}: role counts {counts} differ")
        _require(all(row.list_id == LAB_LISTS[brand] for row in own), f"{brand}: wrong list id")
        ids = [row.author_id for row in own]
        _require(len(ids) == len(set(ids)), f"{brand}: duplicate author id")
    for row in rows:
        _require(row.brand in BRANDS and row.role in ROLE_ORDER, "unknown roster brand or role")
        _require(row.author_id.isdecimal() and _HANDLE_RE.match(row.username), f"invalid member {row.username!r}")
    return rows


def build_roster_rows(members: dict[str, list[dict[str, str]]]) -> list[RosterRow]:
    _require(set(members) == set(ROSTER_KEYS), "roster must hold exactly the OpenAI and Anthropic lists")
    rows = []
    for key, brand in ROSTER_KEYS.items():
        official = {h.casefold() for h in OFFICIAL_HANDLES[brand]}
        for member in members[key]:
            username = str(member["username"])
            rows.append(RosterRow(
                list_id=LAB_LISTS[brand],
                brand=brand,
                author_id=str(member["id"]),
                username=username,
                role="official" if username.casefold() in official else "staff",
            ))
    rows.sort(key=lambda r: (BRANDS.index(r.brand), ROLE_ORDER.index(r.role), r.username.casefold(), r.author_id))
    return _validate_roster(rows)


def roster_csv_bytes(rows: list[RosterRow]) -> bytes:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(ROSTER_FIELDS)
    for row in rows:
        writer.writerow((row.list_id, row.brand, row.author_id, row.username, row.role))
    return stream.getvalue().encode("utf-8")


def read_roster_csv(path: Path) -> list[RosterRow]:
    rows = []
    for record in _csv_records(Path(path).read_text(encoding="utf-8"), ROSTER_FIELDS):
        _require(record["list_id"].isdecimal(), "list_id must be numeric")
        rows.append(RosterRow(int(record["list_id"]), record["brand"], record["author_id"],
                              record["username"], record["role"]))
    return _validate_roster(rows)


# ---------------------------------------------------------------------------
# onboard_brand input
# ---------------------------------------------------------------------------


def onboard_rows(keywords: list[KeywordRow], roster: list[RosterRow]) -> list[dict[str, str]]:
    """One ``onboard_brand --csv`` row per brand; gating stays in the policy."""
    from monitor.management.commands.onboard_brand import CSV_FIELDS

    result = []
    for brand in BRANDS:
        patterns = [row.pattern for row in keywords if row.brand == brand]
        members = {role: [r for r in roster if r.brand == brand and r.role == role] for role in ROLE_ORDER}
        display, color = DISPLAY[brand]
        row = dict.fromkeys(CSV_FIELDS, "")
        row.update({
            "brand_nickname": brand,
            "brand_display_name": display,
            "brand_display_name_en": display,
            "accent_color": color,
            "keyword_primary": patterns[0],
            "keyword_aliases": "|".join(patterns[1:]),
            "official_x_handles": "|".join(r.username for r in members["official"]),
            "official_x_author_ids": "|".join(r.author_id for r in members["official"]),
            "staff_x_handles": "|".join(r.username for r in members["staff"]),
            "staff_x_author_ids": "|".join(r.author_id for r in members["staff"]),
            "harvest_paths": "none",
            "notes": SEED_NOTES,
        })
        result.append(row)
    return result


# ---------------------------------------------------------------------------
# Database guards and reports
# ---------------------------------------------------------------------------


def require_dedicated_backfill() -> dict[str, str]:
    """Refuse anything but the dedicated xbackfiller database (validate_staging rule)."""
    from monitor import backfill_database

    _require(os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") == "backfill",
             "dedicated backfill environment required")
    actual = backfill_database.identity()
    _require(actual["name"] == actual["user"] == "xbackfiller", "dedicated backfill database required")
    return actual


def live_historical_leases() -> list[str]:
    """Job keys of historical X runs whose lease is still live (backfill_month rule)."""
    from django.db.models import Q
    from django.utils import timezone

    from core.models import CollectionRun

    now = timezone.now()
    return list(
        CollectionRun.objects.filter(job__source_id="x", job__mode="historical", status="running")
        .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__gt=now))
        .order_by("job__job_key")
        .values_list("job__job_key", flat=True)[:20]
    )


def require_no_live_lease() -> None:
    keys = live_historical_leases()
    _require(not keys, "historical backfill run holds a live lease: " + ", ".join(keys))


def catalog_report() -> dict[str, Any]:
    """Digest of the classifier's tracked-brand catalog, as classification hashes it."""
    from monitor.cycle import _classification_tracked_brand_catalog
    from x_monitor.attribution import _tracked_brand_catalog

    canonical = _tracked_brand_catalog(
        [], [{"tracked_brand_catalog": _classification_tracked_brand_catalog(), "brand_ids": []}]
    )
    ids = [row["brand_id"] for row in canonical["brands"]]
    return {
        "revision": canonical["revision"],
        "brands": len(ids),
        "size_test_brands_present": sorted(set(BRANDS) & set(ids)),
    }


def _post_brand_counts() -> dict[str, int]:
    from core.models import PostBrand

    return {brand: PostBrand.objects.filter(brand_id=brand).count() for brand in BRANDS}


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Undo receipt: the exact catalog-relevant rows a seed creates or changes
# ---------------------------------------------------------------------------

UNDO_FORMAT = "oai-anthropic-size-seed-undo/v1"
BRAND_FIELDS = ("display_name", "display_name_en", "display_name_zh_cn", "accent_color", "is_sentinel")
# Rows the classifier catalog (monitor.cycle._classification_tracked_brand_catalog)
# reads for a brand, plus the company link onboard_brand adds alongside them.
BRAND_SCOPED = ("BrandKeyword", "BrandSearchTerm", "BrandHashtag", "BrandAccount", "Product", "BrandCompany")
MEMBERSHIP_FIELDS = ("active", "first_seen_at", "last_seen_at", "last_complete_reconciliation_at",
                     "source", "source_run_id")


def _model(name: str):
    import core.models

    return getattr(core.models, name)


def _jsonable(value: Any) -> Any:
    import uuid

    if isinstance(value, uuid.UUID):
        return str(value)
    return value.isoformat() if hasattr(value, "isoformat") else value


def _key_fields(model) -> list[str]:
    """Column attnames identifying a row; several brand link tables use composite keys."""
    pk = model._meta.pk
    return [field.attname for field in getattr(pk, "fields", None) or [pk]]


def _row_keys(model, queryset) -> list[list[Any]]:
    return sorted([_jsonable(value) for value in row] for row in queryset.values_list(*_key_fields(model)))


def _delete_rows(model, keys: list[list[Any]], **scope) -> int:
    from django.db.models import Q

    if not keys:
        return 0
    names = _key_fields(model)
    match = Q()
    for key in keys:
        match |= Q(**dict(zip(names, key, strict=True)))
    return model.objects.filter(match, **scope).delete()[0]


def seed_state() -> dict[str, Any]:
    """Catalog-relevant rows for the two brands and the two lab lists, as primary keys and values."""
    brands = {
        row["nickname"]: {field: row[field] for field in BRAND_FIELDS}
        for row in _model("Brand").objects.filter(nickname__in=BRANDS).values("nickname", *BRAND_FIELDS)
    }
    rows = {name: _row_keys(_model(name), _model(name).objects.filter(brand_id__in=BRANDS)) for name in BRAND_SCOPED}
    memberships = {
        str(row["pk"]): {field: _jsonable(row[field]) for field in MEMBERSHIP_FIELDS}
        for row in _model("TwitterListMembership").objects.filter(list_id__in=LAB_LISTS.values()).values(
            "pk", *MEMBERSHIP_FIELDS)
    }
    companies = sorted(str(pk) for pk in _model("Company").objects.values_list("pk", flat=True))
    return {"brands": brands, "rows": rows, "memberships": memberships, "companies": companies}


def undo_plan(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """What a switch-off must reverse: created rows, changed brand fields and memberships."""
    _require(sorted(before["brands"]) == sorted(BRANDS), "size-test brand rows must exist before the seed")
    return {
        "brand_fields": {
            brand: values for brand, values in before["brands"].items() if after["brands"].get(brand) != values
        },
        "created_rows": {
            name: sorted(map(list, {tuple(key) for key in after["rows"][name]}
                               - {tuple(key) for key in before["rows"][name]}))
            for name in BRAND_SCOPED
        },
        "created_memberships": sorted(set(after["memberships"]) - set(before["memberships"])),
        "changed_memberships": {
            pk: values for pk, values in before["memberships"].items() if after["memberships"].get(pk) != values
        },
        "created_companies": sorted(set(after["companies"]) - set(before["companies"])),
    }


def _restore_undo(plan: dict[str, Any]) -> dict[str, int]:
    from django.utils.dateparse import parse_datetime

    deleted = {}
    for name in BRAND_SCOPED:
        deleted[name] = _delete_rows(_model(name), plan["created_rows"].get(name, []), brand_id__in=BRANDS)
    membership = _model("TwitterListMembership")
    deleted["TwitterListMembership"] = (
        membership.objects.filter(pk__in=plan["created_memberships"], list_id__in=LAB_LISTS.values()).delete()[0]
        if plan["created_memberships"] else 0
    )
    for pk, values in plan["changed_memberships"].items():
        restored = {
            field: parse_datetime(value) if field.endswith("_at") and isinstance(value, str) else value
            for field, value in values.items()
        }
        membership.objects.filter(pk=pk, list_id__in=LAB_LISTS.values()).update(**restored)
    for brand, values in plan["brand_fields"].items():
        _model("Brand").objects.filter(nickname=brand).update(**values)
    company = _model("Company")
    unreferenced = [pk for pk in plan["created_companies"]
                    if not _model("BrandCompany").objects.filter(company_id=pk).exists()]
    deleted["Company"] = company.objects.filter(pk__in=unreferenced).delete()[0] if unreferenced else 0
    return deleted


def _write_seed(keywords, roster, *, roster_sha256, config_path, policy_path) -> dict[str, Any]:
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from django.db import transaction
    from django.utils import timezone

    from core.models import Account, TwitterListMembership
    from monitor.cycle import _build_brand_index
    from monitor.list_membership import _upsert_membership
    from monitor.management.commands.onboard_brand import CSV_FIELDS
    from x_monitor.attribution import detect_brand_mentions
    from x_monitor.config import load_config

    counts = {"memberships_created": 0, "memberships_reactivated": 0, "memberships_unchanged": 0}
    with transaction.atomic(), tempfile.TemporaryDirectory() as tmp:
        onboard_csv = Path(tmp) / "onboard.csv"
        with onboard_csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(onboard_rows(keywords, roster))
        output = io.StringIO()
        try:
            call_command("onboard_brand", "--csv", str(onboard_csv), "--config", str(config_path),
                         "--policy", str(policy_path), stdout=output)
        except CommandError as exc:
            raise SeedRefused(f"onboard_brand refused: {exc}") from exc
        now = timezone.now()
        for row in roster:
            account = Account.x.get(author_id=row.author_id)
            existing = TwitterListMembership.objects.filter(list_id=row.list_id, account=account).first()
            if existing is not None and existing.active:
                counts["memberships_unchanged"] += 1
                continue
            _membership, created, _was_active = _upsert_membership(
                list_id=row.list_id, account=account, observed_at=now, source=MEMBERSHIP_SOURCE,
                source_run_id=f"roster-sha256:{roster_sha256}", complete=False,
            )
            counts["memberships_created" if created else "memberships_reactivated"] += 1
        # Production attribution path: the live index must build and honour gating.
        index = _build_brand_index(list(load_config(Path(config_path)).enabled_models))
        for text, expected in (("OpenAI", {"openai"}), ("Anthropic", {"anthropic"}),
                               ("Sol AI model", {"openai"}), ("Sol is out", set())):
            found = set(detect_brand_mentions(text, index)) & set(BRANDS)
            _require(found == expected, f"attribution probe {text!r} gave {sorted(found)}")
    return {"onboard": output.getvalue().strip().splitlines(), **counts}


def seed(keywords_path: Path, roster_path: Path, *, config_path: Path, policy_path: Path,
         undo_receipt: Path) -> dict[str, Any]:
    from django.db import transaction

    from x_monitor.harvest_policy import load_policy

    keywords = read_keyword_csv(keywords_path)
    roster = read_roster_csv(roster_path)
    check_policy_alignment(keywords, load_policy(policy_path))
    _require(not Path(undo_receipt).exists(), f"undo receipt already exists: {undo_receipt}")
    database = require_dedicated_backfill()
    require_no_live_lease()
    _require(not _model("BrandKeyword").objects.filter(brand_id__in=BRANDS).exists(),
             "size-test brands already carry keywords; switch off with the existing undo receipt first")
    with transaction.atomic():
        state_before, before = seed_state(), catalog_report()
        written = _write_seed(keywords, roster, roster_sha256=_sha256(roster_path),
                              config_path=config_path, policy_path=policy_path)
        plan = undo_plan(state_before, seed_state())
        receipt = {"format": UNDO_FORMAT, "database": database["name"], "catalog_before": before, "undo": plan,
                   "keywords_sha256": _sha256(keywords_path), "roster_sha256": _sha256(roster_path)}
        Path(undo_receipt).parent.mkdir(parents=True, exist_ok=True)
        with Path(undo_receipt).open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2)
    return {"database": database["name"], "catalog_before": before, "catalog_after": catalog_report(),
            "undo_receipt": str(undo_receipt), "keywords_sha256": receipt["keywords_sha256"],
            "roster_sha256": receipt["roster_sha256"], **written}


def read_undo_receipt(path: Path) -> dict[str, Any]:
    try:
        receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SeedRefused(f"undo receipt unreadable: {exc}") from exc
    _require(isinstance(receipt, dict), "not a size-test undo receipt")
    _require(receipt.get("format") == UNDO_FORMAT, "not a size-test undo receipt")
    _require(receipt.get("database") == "xbackfiller", "undo receipt is for another database")
    _require(isinstance(receipt.get("catalog_before", {}).get("revision"), str), "undo receipt lacks the pre-seed catalog")
    return receipt


def _write_switch_off(receipt: dict[str, Any]) -> dict[str, Any]:
    """Undo the seed in one transaction; roll back unless the pre-seed catalog returns."""
    from django.db import transaction

    with transaction.atomic():
        list(_model("Brand").objects.select_for_update().filter(nickname__in=BRANDS))
        deleted = _restore_undo(receipt["undo"])
        after = catalog_report()
        _require(after["revision"] == receipt["catalog_before"]["revision"],
                 "catalog after undo differs from the pre-seed catalog; nothing was changed")
    return {"deleted": deleted, "catalog_after": after}


def switch_off(*, undo_receipt: Path) -> dict[str, Any]:
    database = require_dedicated_backfill()
    require_no_live_lease()
    receipt = read_undo_receipt(undo_receipt)
    before, post_brands_before = catalog_report(), _post_brand_counts()
    result = _write_switch_off(receipt)
    post_brands_after = _post_brand_counts()
    _require(post_brands_after == post_brands_before, "PostBrand rows changed during switch-off")
    return {"database": database["name"], "catalog_before_switch_off": before,
            "catalog_pre_seed": receipt["catalog_before"], "post_brands": post_brands_after, **result}


def build(frozen_path: Path, members_path: Path, keywords_out: Path, roster_out: Path) -> dict[str, Any]:
    _require(_sha256(frozen_path) == FROZEN_QUERIES_SHA256, "frozen query file checksum changed")
    keywords = keyword_csv_bytes(build_keyword_rows(json.loads(Path(frozen_path).read_text(encoding="utf-8"))))
    roster = roster_csv_bytes(build_roster_rows(json.loads(Path(members_path).read_text(encoding="utf-8"))))
    Path(keywords_out).write_bytes(keywords)
    Path(roster_out).write_bytes(roster)
    return {"keywords": str(keywords_out), "keywords_sha256": hashlib.sha256(keywords).hexdigest(),
            "roster": str(roster_out), "roster_sha256": hashlib.sha256(roster).hexdigest()}


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    import django

    django.setup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--frozen-queries", type=Path,
                   default=Path("docs/analysis/2026-10-27-215214-oai-anthropic-frozen-queries.json"))
    b.add_argument("--lab-list-members", type=Path, required=True)
    b.add_argument("--keywords-out", type=Path, required=True)
    b.add_argument("--roster-out", type=Path, required=True)
    s = sub.add_parser("seed")
    s.add_argument("--keywords", type=Path, required=True)
    s.add_argument("--roster", type=Path, required=True)
    s.add_argument("--config", type=Path, default=Path("config.yaml"))
    s.add_argument("--policy", type=Path, default=Path("config/harvest_policy.yaml"))
    s.add_argument("--undo-receipt", type=Path, required=True,
                   help="new file recording the rows switch-off must undo (machine-local receipt)")
    o = sub.add_parser("switch-off")
    o.add_argument("--undo-receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build(args.frozen_queries, args.lab_list_members, args.keywords_out, args.roster_out)
        else:
            _setup_django()
            if args.command == "seed":
                result = seed(args.keywords, args.roster, config_path=args.config, policy_path=args.policy,
                              undo_receipt=args.undo_receipt)
            else:
                result = switch_off(undo_receipt=args.undo_receipt)
    except SeedRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
