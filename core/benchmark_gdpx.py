"""Pure GDPx parsing: chunk discovery, dataset extraction, validation and checks.

GDPx (https://gdpx.semianalysis.com/) publishes no API. Its homepage is a
Next.js build whose JavaScript chunks embed the full dataset as one
``JSON.parse('...')`` string literal, next to a partner registry built from
``a("<id>", "<name>", "<domain>", "/partners/...")`` calls. This module turns
fetched homepage and chunk text into a validated dataset or a typed failure.
It performs no network or database access; ``sources.gdpx`` does the fetching.

The published headline score is a mean over domains of the mean over that
domain's partners of each per-partner ``score`` (equal weight per domain, equal
weight per partner within a domain). ``headline_scores`` is shared with
readers that recompute it from stored per-partner rows.
"""

from __future__ import annotations

import html
import json
import math
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from core.measurement_taxonomy import digest
from scripts.benchmark_download_collector.sources import SourceError

GDPX_HOST = "gdpx.semianalysis.com"
FAILURE_CODES = frozenset(
    {
        "fetch_failed",
        "fetch_challenged",
        "dataset_not_found",
        "dataset_ambiguous",
        "shape_changed",
        "headline_mismatch",
    }
)
DATASET_KEYS = frozenset({"updatedAt", "source", "models", "overall", "results"})
MODEL_KEYS = frozenset({"id", "name", "lab", "openWeights", "harness", "reasoning"})
MODEL_OPTIONAL_KEYS = frozenset({"specialist"})
OVERALL_KEYS = frozenset({"costPerTask", "tokensPerTask"})
RESULT_KEYS = frozenset(
    {
        "modelId",
        "partnerId",
        "tasks",
        "tasksScored",
        "score",
        "tasksWithPartial",
        "partialScore",
        "costPerTask",
        "tasksWithCost",
        "tokensPerTask",
        "tasksWithTokens",
    }
)
HEADLINE_TOLERANCE = 0.05
MAX_MODELS = 1000
MAX_RESULTS = 20000

_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
# Plain (`/_next/...`), JSON-escaped (`\/_next\/...`) and quote-escaped
# (`\"/_next/...\"`) references all normalize to this after unescaping `\/`.
_CHUNK_REF = re.compile(
    r"(?P<origin>https?://[^/\s\"'\\<>]+|//[^/\s\"'\\<>]+)?"
    r"(?P<path>/_next/static/[A-Za-z0-9_~.\-/]+?\.js)(?![A-Za-z0-9_~.\-/])"
)
_JSON_PARSE = re.compile(r"JSON\.parse\(\s*(['\"])")
_PARTNER_CALL = re.compile(
    r"(?<![\w$.])[A-Za-z_$][\w$]*\(\s*\"([^\"\\]*)\"\s*,\s*\"([^\"\\]*)\"\s*,"
    r"\s*\"([^\"\\]*)\"\s*,\s*\"(/partners/[^\"\\]*)\"\s*\)"
)
_LEADERBOARD_ROW = re.compile(r"<li\b[^>]*>(.*?)</li>", re.DOTALL)
_ROW_NAME = re.compile(r'font-medium leading-snug">([^<]+)</span>')
_ROW_SCORE = re.compile(
    r'<span class="block text-sm font-semibold">\s*(\d+(?:\.\d+)?)\s*(?:<!-- -->)?%</span>'
)
_VERSION_LABEL = re.compile(r">\s*(v\d+(?:\.\d+){1,2})\s*</span>")


class GdpxError(SourceError):
    """A typed GDPx failure; ``str()`` is the fixed, non-secret code."""

    def __init__(self, code, detail=None, *, requests=None):
        if code not in FAILURE_CODES:
            raise ValueError(f"unknown GDPx failure code: {code}")
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.requests = list(requests or [])


def shape(condition, detail):
    if not condition:
        raise GdpxError("shape_changed", detail)


# --- discovery -------------------------------------------------------------


def chunk_references(page):
    """Return (same-host chunk paths in first-seen order, refused references)."""
    text = page.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    paths, refused = [], []
    for match in _CHUNK_REF.finditer(text):
        origin, path = match.group("origin") or "", match.group("path")
        same_host = origin.lower() in {"", f"https://{GDPX_HOST}", f"//{GDPX_HOST}"}
        if not same_host or "//" in path or "/./" in path or "/../" in path:
            if origin + path not in refused:
                refused.append(origin + path)
        elif path not in paths:
            paths.append(path)
    return paths, refused


# --- JavaScript string literals ------------------------------------------------

_SIMPLE_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    "v": "\v",
}


def decode_js_string(body):
    """Decode the body of a JavaScript string literal (escapes, not quotes)."""
    out = []
    i, end = 0, len(body)
    while i < end:
        char = body[i]
        if char != "\\":
            out.append(char)
            i += 1
            continue
        shape(i + 1 < end, "dangling_js_escape")
        code = body[i + 1]
        i += 2
        if code in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[code])
        elif code == "0" and not (i < end and body[i].isdigit()):
            out.append("\0")
        elif code == "x":
            digits = body[i : i + 2]
            shape(re.fullmatch(r"[0-9A-Fa-f]{2}", digits), "invalid_js_hex_escape")
            out.append(chr(int(digits, 16)))
            i += 2
        elif code == "u" and body[i : i + 1] == "{":
            close = body.find("}", i)
            digits = body[i + 1 : close] if close > 0 else ""
            shape(
                re.fullmatch(r"[0-9A-Fa-f]{1,6}", digits)
                and int(digits, 16) <= 0x10FFFF,
                "invalid_js_unicode_escape",
            )
            out.append(chr(int(digits, 16)))
            i = close + 1
        elif code == "u":
            digits = body[i : i + 4]
            shape(re.fullmatch(r"[0-9A-Fa-f]{4}", digits), "invalid_js_unicode_escape")
            out.append(chr(int(digits, 16)))
            i += 4
        elif code == "\r":
            i += 1 if body[i : i + 1] == "\n" else 0
        elif code in "\n\u2028\u2029":
            pass  # line continuation
        else:
            shape(not code.isdigit(), "legacy_octal_js_escape")
            out.append(code)
    # Join UTF-16 surrogate pairs produced by consecutive \uXXXX escapes.
    return "".join(out).encode("utf-16", "surrogatepass").decode("utf-16")


def json_parse_literals(script):
    """Yield the decoded bodies of every ``JSON.parse('...')`` literal."""
    for match in _JSON_PARSE.finditer(script):
        quote, i = match.group(1), match.end()
        start = i
        while i < len(script) and script[i] != quote:
            if script[i] in "\r\n":
                break
            i += 2 if script[i] == "\\" else 1
        if i >= len(script) or script[i] != quote:
            continue
        try:
            yield decode_js_string(script[start:i])
        except (GdpxError, UnicodeError):
            continue


def _reject_constant(value):
    raise ValueError(f"non-finite JSON constant {value}")


def dataset_candidates(script):
    """Parsed ``JSON.parse`` objects that carry every dataset key."""
    for literal in json_parse_literals(script):
        try:
            value = json.loads(literal, parse_constant=_reject_constant)
        except ValueError:
            continue
        if isinstance(value, dict) and DATASET_KEYS <= value.keys():
            yield value


def partner_registry(script):
    """Partner id -> {name, domain} from the chunk's registry calls."""
    registry = {}
    for partner_id, name, domain, _asset in _PARTNER_CALL.findall(script):
        shape(_SLUG.fullmatch(partner_id), "invalid_partner_id")
        shape(0 < len(name) <= 256, "invalid_partner_name")
        shape(_SLUG.fullmatch(domain), "invalid_partner_domain")
        entry = {"name": name, "domain": domain}
        shape(registry.setdefault(partner_id, entry) == entry, "conflicting_partner")
    shape(registry, "partner_registry_not_found")
    return registry


def select_dataset(chunks):
    """Exactly one distinct dataset across all chunks, with its chunk's registry.

    ``chunks`` maps chunk path -> script text, in reference order.
    """
    found = {}
    for path, script in chunks.items():
        for candidate in dataset_candidates(script):
            key = canonical_digest_or_none(candidate)
            if key is None:
                # A dataset-shaped literal that cannot be canonicalized is malformed.
                raise GdpxError("shape_changed", "uncanonical_dataset")
            found.setdefault(key, (candidate, path, script))
    if not found:
        raise GdpxError("dataset_not_found")
    if len(found) > 1:
        raise GdpxError("dataset_ambiguous", f"{len(found)}_distinct_datasets")
    ((dataset, path, script),) = found.values()
    return dataset, partner_registry(script), path


# --- validation -------------------------------------------------------------


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _count(value):
    return type(value) is int and 0 <= value < 10**9


def _label(value):
    return isinstance(value, str) and 0 < len(value) <= 256


def validate_dataset(dataset, partners, *, today=None):
    """Raise ``shape_changed`` unless the dataset matches the 2026-11 shape."""
    shape(isinstance(dataset, dict) and dataset.keys() == DATASET_KEYS, "dataset_keys")
    shape(isinstance(dataset["updatedAt"], str), "updated_at_type")
    try:
        updated = date.fromisoformat(dataset["updatedAt"])
    except ValueError:
        updated = None
    shape(updated and updated.isoformat() == dataset["updatedAt"], "updated_at_format")
    today = today or datetime.now(UTC).date()
    shape(updated <= today + timedelta(days=1), "future_updated_at")
    shape(_label(dataset["source"]), "source_label")

    models = dataset["models"]
    shape(isinstance(models, list) and 0 < len(models) <= MAX_MODELS, "models_list")
    by_id = {}
    for model in models:
        shape(isinstance(model, dict), "model_type")
        keys = model.keys()
        shape(MODEL_KEYS <= keys <= MODEL_KEYS | MODEL_OPTIONAL_KEYS, "model_keys")
        shape(isinstance(model["id"], str) and _SLUG.fullmatch(model["id"]), "model_id")
        shape(model["id"] not in by_id, "duplicate_model")
        for field in ("name", "lab", "harness", "reasoning"):
            shape(_label(model[field]), f"model_{field}")
        shape(type(model["openWeights"]) is bool, "model_open_weights")
        shape(
            "specialist" not in model or _label(model["specialist"]), "model_specialist"
        )
        by_id[model["id"]] = model

    overall = dataset["overall"]
    shape(isinstance(overall, dict), "overall_type")
    for model_id, entry in overall.items():
        shape(model_id in by_id, "overall_unknown_model")
        shape("specialist" not in by_id[model_id], "specialist_overall")
        shape(isinstance(entry, dict) and entry.keys() == OVERALL_KEYS, "overall_keys")
        for field in OVERALL_KEYS:
            value = entry[field]
            shape(value is None or _number(value) and value >= 0, f"overall_{field}")

    results = dataset["results"]
    shape(isinstance(results, list) and 0 < len(results) <= MAX_RESULTS, "results_list")
    seen = set()
    for row in results:
        shape(isinstance(row, dict) and row.keys() == RESULT_KEYS, "result_keys")
        shape(row["modelId"] in by_id, "result_unknown_model")
        shape(row["partnerId"] in partners, "result_unknown_partner")
        identity = row["modelId"], row["partnerId"]
        shape(identity not in seen, "duplicate_result")
        seen.add(identity)
        shape(_count(row["tasks"]) and row["tasks"] > 0, "result_tasks")
        for field in (
            "tasksScored",
            "tasksWithPartial",
            "tasksWithCost",
            "tasksWithTokens",
        ):
            shape(_count(row[field]) and row[field] <= row["tasks"], f"result_{field}")
        for field in ("score", "partialScore"):
            shape(_number(row[field]) and 0 <= row[field] <= 100, f"result_{field}")
        for field, tasks in (
            ("costPerTask", "tasksWithCost"),
            ("tokensPerTask", "tasksWithTokens"),
        ):
            value = row[field]
            if value is None:
                shape(row[tasks] == 0, f"result_null_{field}")
            else:
                shape(_number(value) and value >= 0, f"result_{field}")
    return dataset


# --- canonical digest -------------------------------------------------------


def _normalize(value):
    if type(value) is float and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def canonical_dataset(dataset):
    """Order-free, integral-float-free form so a reordering redeploy is unchanged."""
    canonical = _normalize(dataset)
    canonical["models"] = sorted(canonical["models"], key=lambda m: m["id"])
    canonical["results"] = sorted(
        canonical["results"], key=lambda r: (r["modelId"], r["partnerId"])
    )
    return canonical


def canonical_digest(dataset):
    return digest(canonical_dataset(dataset))


def canonical_digest_or_none(dataset):
    try:
        return canonical_digest(dataset)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


# --- headline ---------------------------------------------------------------


def headline_scores(rows, partner_domains):
    """Model id -> mean over domains of the mean per-partner score in that domain.

    ``rows`` yields ``(model_id, partner_id, score)``; ``partner_domains`` maps
    partner id -> domain.
    """
    by_model = defaultdict(lambda: defaultdict(list))
    for model_id, partner_id, score in rows:
        by_model[model_id][partner_domains[partner_id]].append(score)
    return {
        model_id: sum(sum(s) / len(s) for s in domains.values()) / len(domains)
        for model_id, domains in by_model.items()
    }


def published_headlines(page):
    """(display name, published score) rows of the server-rendered leaderboard."""
    rows = []
    for item in _LEADERBOARD_ROW.findall(page):
        name, score = _ROW_NAME.search(item), _ROW_SCORE.search(item)
        if name and score:
            rows.append((html.unescape(name.group(1)).strip(), float(score.group(1))))
    return rows


def check_headlines(dataset, partners, page):
    """Compare recomputed headlines with every non-specialist leaderboard row."""
    shown = published_headlines(page)
    shape(shown, "leaderboard_not_found")
    domains = {pid: entry["domain"] for pid, entry in partners.items()}
    computed = headline_scores(
        ((r["modelId"], r["partnerId"], r["score"]) for r in dataset["results"]),
        domains,
    )
    by_name = defaultdict(list)
    for model in dataset["models"]:
        by_name[model["name"]].append(model)
    checks = []
    for name, published in shown:
        matches = by_name.get(name, [])
        if len(matches) == 1 and "specialist" in matches[0]:
            continue
        if len(matches) != 1:
            raise GdpxError("headline_mismatch", "unmatched_leaderboard_name")
        model_id = matches[0]["id"]
        if model_id not in computed:
            raise GdpxError("headline_mismatch", "leaderboard_model_without_results")
        if abs(computed[model_id] - published) > HEADLINE_TOLERANCE + 1e-9:
            raise GdpxError("headline_mismatch", "headline_outside_tolerance")
        checks.append(
            {
                "model_id": model_id,
                "name": name,
                "published": published,
                "computed": computed[model_id],
            }
        )
    return checks


# --- version probe ----------------------------------------------------------


def version_probe(page, dataset):
    """Homepage version label and a fingerprint of per-partner task totals."""
    labels = sorted(set(_VERSION_LABEL.findall(page)))
    totals = defaultdict(set)
    for row in dataset["results"]:
        totals[row["partnerId"]].add(row["tasks"])
    task_totals = {pid: sorted(values) for pid, values in sorted(totals.items())}
    return {
        "label": labels[0] if len(labels) == 1 else None,
        "task_totals": task_totals,
        "task_totals_sha256": digest(task_totals),
    }


def probe_anomalies(probe, previous=None):
    """Flags only; a changed probe never blocks collection."""
    anomalies = []
    if probe["label"] is None:
        anomalies.append("version_label_unreadable")
    if previous:
        if probe["label"] is not None and probe["label"] != previous.get("label"):
            anomalies.append("version_label_changed")
        if probe["task_totals_sha256"] != previous.get("task_totals_sha256"):
            anomalies.append("task_totals_changed")
    return anomalies


def expected_observation_count(dataset):
    """One observation per result plus one per reported overall entry."""
    return len(dataset["results"]) + len(dataset["overall"])
