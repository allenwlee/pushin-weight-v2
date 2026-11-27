"""GDPx reader: discovery, extraction and validation without network or database."""

import json
import re
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from core.benchmark_gdpx import (
    GdpxError,
    canonical_digest,
    decode_js_string,
    headline_scores,
    partner_registry,
)
from scripts.benchmark_download_collector.sources import (
    GDPX_URL,
    SOURCE_URLS,
    Budget,
    gdpx,
    safe_error,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "benchmark_download_collector"
    / "gdpx-2026-11-25"
)
DATA_PATH = "/_next/static/immutable/chunks/1p0q26iuw5iw2.js"
DECOY_PATH = "/_next/static/immutable/chunks/2kvsey2b0882z.js"
STUB = "(globalThis.TURBOPACK||(globalThis.TURBOPACK=[])).push([0,1,()=>{}]);\n"
HOMEPAGE = (FIXTURE / "homepage.html").read_text()
DATA_CHUNK = (FIXTURE / "chunk-1p0q26iuw5iw2.js").read_text()
DECOY_CHUNK = (FIXTURE / "chunk-decoy.js").read_text()
EXPECTED = json.loads((FIXTURE / "expected.json").read_text())
LITERAL = re.compile(r"JSON\.parse\('((?:[^'\\]|\\.)*)'\)", re.DOTALL)


def js_single_quoted(text):
    return text.replace("\\", "\\\\").replace("'", "\\'")


def chunk_with(dataset, chunk=DATA_CHUNK):
    """Re-embed a dataset in the real chunk exactly as the site's bundler does."""
    body = js_single_quoted(json.dumps(dataset, separators=(",", ":")))
    replaced, count = LITERAL.subn(lambda _: f"JSON.parse('{body}')", chunk)
    assert count == 1
    return replaced


def site(overrides=None, requests=None):
    """Serve the recorded homepage, data chunk and decoy; other chunks are stubs."""
    files = {"/": HOMEPAGE, DATA_PATH: DATA_CHUNK, DECOY_PATH: DECOY_CHUNK}
    files.update(overrides or {})

    def respond(request):
        if requests is not None:
            requests.append(request)
        assert request.url.host == "gdpx.semianalysis.com"
        body = files.get(request.url.path, STUB)
        if callable(body):
            body = body(request)
        if isinstance(body, httpx.Response):
            return body
        kind = "text/html" if request.url.path == "/" else "application/javascript"
        return httpx.Response(200, text=body, headers={"content-type": kind})

    return respond


def reader_budget(handler, *, sleeps=None, **kwargs):
    return Budget(
        httpx.Client(
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "inherited-secret"},
            cookies={"session": "cookie"},
        ),
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
        **kwargs,
    )


def read(overrides=None, requests=None, **kwargs):
    return gdpx(reader_budget(site(overrides, requests)), **kwargs)


def failure(overrides=None, requests=None, **kwargs):
    with pytest.raises(GdpxError) as caught:
        read(overrides, requests, **kwargs)
    assert safe_error(caught.value) == caught.value.code
    return caught.value


def dataset():
    return deepcopy(EXPECTED["dataset"])


def test_recorded_fixture_yields_complete_dataset_and_registry():
    requests = []
    result = read(requests=requests)
    data = result["dataset"]
    assert result["status"] == "ok"
    assert data == EXPECTED["dataset"]
    assert data["updatedAt"] == result["updated_at"] == "2026-11-25"
    assert len(data["models"]) == 29
    assert len(data["overall"]) == 26
    assert len(data["results"]) == 367
    assert len(result["partners"]) == 14
    assert len({p["domain"] for p in result["partners"].values()}) == 11
    assert result["partners"]["arithmetic"] == {
        "name": "Arithmetic",
        "domain": "cybersecurity",
    }
    assert result["expected_observation_count"] == 367 + 26
    assert result["dataset_chunk"] == DATA_PATH
    assert result["dataset_sha256"] == canonical_digest(EXPECTED["dataset"])
    assert result["source_url"] == GDPX_URL == SOURCE_URLS["gdpx"]
    # 17 published null costs all have zero costed tasks and pass validation.
    nulls = [r for r in data["results"] if r["costPerTask"] is None]
    assert len(nulls) == 17 and {r["tasksWithCost"] for r in nulls} == {0}
    assert sum(type(r["score"]) is int for r in data["results"]) == 95
    # The homepage plus every distinct referenced JavaScript chunk, once each.
    paths = [r.url.path for r in requests]
    assert paths[0] == "/" and len(paths) == len(set(paths)) == 13
    assert all(p.startswith("/_next/static/") and p.endswith(".js") for p in paths[1:])
    assert [r["url"] for r in result["requests"]] == [str(r.url) for r in requests]
    assert all(len(r["body_sha256"]) == 64 for r in result["requests"])
    assert result["refused_references"] == []
    assert result["version_probe"]["label"] == "v1.0"
    assert result["version_probe"]["task_totals"]["fleet"] == [18]
    assert result["anomalies"] == []


def test_requests_carry_declared_user_agent_and_no_cookies_or_credentials():
    requests = []
    read(requests=requests)
    for request in requests:
        assert request.headers["user-agent"] == "PushinWeight-public-metadata"
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        assert request.url.scheme == "https" and not request.url.query


def test_headline_recomputation_matches_server_rendered_table():
    result = read()
    published = {row["name"]: row["published"] for row in result["headline_check"]}
    assert published == EXPECTED["headlines"]
    assert list(published.values()) == [
        19.3,
        16.4,
        11.9,
        11.5,
        10.1,
        9.0,
        8.2,
        7.4,
        6.3,
        5.4,
        5.1,
    ]
    for row in result["headline_check"]:
        assert abs(row["computed"] - row["published"]) <= 0.05
    domains = {k: v["domain"] for k, v in result["partners"].items()}
    scores = headline_scores(
        (
            (r["modelId"], r["partnerId"], r["score"])
            for r in EXPECTED["dataset"]["results"]
        ),
        domains,
    )
    assert round(scores["gpt-6-2-astra"], 4) == 19.2612
    # Specialists only have their own domain and are never checked against the table.
    assert scores["hinoki-ho1"] == 18.52
    assert "hinoki-ho1" not in {row["model_id"] for row in result["headline_check"]}


def test_decoy_ignored_but_two_distinct_datasets_are_ambiguous():
    # The decoy chunk (unrelated JSON.parse, including an updatedAt key) is ignored.
    assert read()["status"] == "ok"
    # The same dataset referenced from two chunks is still exactly one dataset.
    assert read({DECOY_PATH: DATA_CHUNK})["status"] == "ok"
    other = dataset()
    other["results"][0]["score"] = 1.0
    assert failure({DECOY_PATH: chunk_with(other)}).code == "dataset_ambiguous"


def test_no_dataset_literal_is_dataset_not_found():
    assert failure({DATA_PATH: STUB}).code == "dataset_not_found"
    partial = dataset()
    del partial["source"]
    # Without all five dataset keys the literal is not a dataset candidate.
    assert failure({DATA_PATH: chunk_with(partial)}).code == "dataset_not_found"


def test_escaped_refs_are_discovered():
    escaped = HOMEPAGE.replace(f'src="{DATA_PATH}"', 'src="/ignored.js"')
    escaped = escaped.replace(
        f'\\"{DATA_PATH}\\"',
        '\\"\\/_next\\/static\\/immutable\\/chunks\\/1p0q26iuw5iw2.js\\"',
    )
    assert DATA_PATH not in escaped
    requests = []
    result = read({"/": escaped}, requests)
    assert result["dataset_chunk"] == DATA_PATH
    assert DATA_PATH in [r.url.path for r in requests]


def test_js_string_escapes_decode_exactly_and_digest_is_stable():
    assert decode_js_string(r"O\'Brien \"x\" \\ é \x41 \u{1F600} 😀 \n") == (
        'O\'Brien "x" \\ é A \U0001f600 \U0001f600 \n'
    )
    original = dataset()
    target = next(m for m in original["models"] if m["id"] == "inkling")
    chunk = DATA_CHUNK.replace(
        '"name":"Inkling"', '"name":"Ink\\\'ling \\u00e9 \\\\\\\\ \\ud83d\\ude00"'
    )
    assert chunk != DATA_CHUNK
    result = read({DATA_PATH: chunk})
    model = next(m for m in result["dataset"]["models"] if m["id"] == "inkling")
    assert model["name"] == "Ink'ling é \\ \U0001f600"
    target["name"] = model["name"]
    assert result["dataset_sha256"] == canonical_digest(original)
    assert read({DATA_PATH: chunk})["dataset_sha256"] == result["dataset_sha256"]


def test_canonical_digest_ignores_order_and_integral_float_spelling():
    original = dataset()
    shuffled = dataset()
    shuffled["models"].reverse()
    shuffled["results"].reverse()
    shuffled["overall"] = dict(reversed(list(shuffled["overall"].items())))
    integral = next(r for r in shuffled["results"] if type(r["score"]) is int)
    integral["score"] = float(integral["score"])
    assert canonical_digest(shuffled) == canonical_digest(original)
    # The same holds end to end through the chunk.
    assert read({DATA_PATH: chunk_with(shuffled)})[
        "dataset_sha256"
    ] == canonical_digest(original)
    changed = dataset()
    changed["results"][0]["score"] += 0.01
    assert canonical_digest(changed) != canonical_digest(original)
    flipped = dataset()
    flipped["models"][0]["openWeights"] = True
    assert canonical_digest(flipped) != canonical_digest(original)


@pytest.mark.parametrize(
    "problem",
    [
        "unknown_partner",
        "missing_results",
        "renamed_field",
        "unknown_model",
        "score_out_of_range",
        "negative_cost",
        "boolean_score",
        "duplicate_result",
        "specialist_overall",
        "future_date",
    ],
)
def test_shape_changes_are_rejected(problem):
    data = dataset()
    row = data["results"][0]
    if problem == "unknown_partner":
        row["partnerId"] = "new-partner"
    elif problem == "missing_results":
        del data["results"]
    elif problem == "renamed_field":
        row["cost_per_task"] = row.pop("costPerTask")
    elif problem == "unknown_model":
        row["modelId"] = "unlisted-model"
    elif problem == "score_out_of_range":
        row["score"] = 100.5
    elif problem == "negative_cost":
        row["costPerTask"] = -0.01
    elif problem == "boolean_score":
        row["score"] = True
    elif problem == "duplicate_result":
        data["results"].append(deepcopy(row))
    elif problem == "specialist_overall":
        data["overall"]["hinoki-ho1"] = {"costPerTask": 1.0, "tokensPerTask": 5}
    elif problem == "future_date":
        data["updatedAt"] = "2099-01-01"
    error = failure({DATA_PATH: chunk_with(data)})
    # "missing_results" drops a dataset key, so it is no longer a candidate.
    expected = "dataset_not_found" if problem == "missing_results" else "shape_changed"
    assert error.code == expected


def test_missing_results_key_alongside_registry_is_shape_change_in_validation():
    from core.benchmark_gdpx import validate_dataset

    data = dataset()
    del data["results"]
    registry = partner_registry(DATA_CHUNK)
    with pytest.raises(GdpxError) as caught:
        validate_dataset(data, registry)
    assert caught.value.code == "shape_changed"


def test_partner_registry_requires_known_partner_calls():
    registry = partner_registry(DATA_CHUNK)
    assert len(registry) == 14
    assert registry["latchbio"] == {"name": "LatchBio", "domain": "biology"}
    without = re.sub(
        r'\b[A-Za-z_$][\w$]*\("[^"]*","[^"]*","[^"]*","/partners/[^"]*"\)',
        "0",
        DATA_CHUNK,
    )
    assert failure({DATA_PATH: without}).code == "shape_changed"


def test_null_cost_requires_zero_costed_tasks():
    data = dataset()
    row = next(r for r in data["results"] if r["costPerTask"] is not None)
    row["costPerTask"] = None
    row["tasksWithCost"] = 0
    assert read({DATA_PATH: chunk_with(data)})["status"] == "ok"
    row["tasksWithCost"] = 1
    assert failure({DATA_PATH: chunk_with(data)}).code == "shape_changed"


def test_altered_published_headline_is_mismatch():
    altered = HOMEPAGE.replace(
        '<span class="block text-sm font-semibold">19.3<!-- -->%</span>',
        '<span class="block text-sm font-semibold">19.5<!-- -->%</span>',
    )
    assert altered != HOMEPAGE
    requests = []
    error = failure({"/": altered}, requests)
    assert error.code == "headline_mismatch"
    # Every fetched body stays referenced so request archives can be kept.
    assert len(error.requests) == len(requests) == 13


def test_missing_leaderboard_table_cannot_be_checked():
    stripped = re.sub(r"<ol>.*?</ol>", "<ol></ol>", HOMEPAGE, flags=re.DOTALL)
    assert failure({"/": stripped}).code == "shape_changed"


def test_homepage_server_errors_retry_three_times_then_fail():
    requests = []
    error = failure({"/": httpx.Response(503)}, requests)
    assert error.code == "fetch_failed" and error.detail == "http_503"
    assert len(requests) == 3


def test_retry_after_is_honored_on_429():
    calls = []

    def homepage(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "7"})
        return httpx.Response(200, text=HOMEPAGE)

    sleeps = []
    result = gdpx(reader_budget(site({"/": homepage}), sleeps=sleeps))
    assert result["status"] == "ok"
    assert sleeps == [7.0] and len(calls) == 2


@pytest.mark.parametrize(
    "response,attempts",
    [
        (httpx.Response(403, text="<html>Just a moment...</html>"), 1),
        (httpx.Response(429, headers={"retry-after": "1"}), 3),
        (
            httpx.Response(200, text="<html><body>Checking your browser</body></html>"),
            1,
        ),
    ],
)
def test_challenges_are_fetch_challenged(response, attempts):
    requests = []
    assert failure({"/": response}, requests).code == "fetch_challenged"
    assert len(requests) == attempts


def test_homepage_invalid_utf8_is_fetch_failed():
    requests = []
    error = failure(
        {
            "/": httpx.Response(
                200, content=b"\xff\xfe\xfd", headers={"content-type": "text/html"}
            )
        },
        requests,
    )
    assert error.code == "fetch_failed" and error.detail == "malformed_text"
    assert len(requests) == 1


def test_chunk_challenge_is_fetch_challenged():
    assert failure({DATA_PATH: httpx.Response(403)}).code == "fetch_challenged"
    assert failure({DATA_PATH: httpx.Response(500)}).code == "fetch_failed"


def test_redirect_is_refused_and_recorded():
    requests = []
    error = failure(
        {"/": httpx.Response(307, headers={"location": "https://evil.example/"})},
        requests,
    )
    assert error.code == "fetch_failed" and error.detail == "http_307"
    assert [r.url.host for r in requests] == ["gdpx.semianalysis.com"]


def test_chunk_reference_on_another_host_is_refused_and_recorded():
    foreign = HOMEPAGE.replace(
        "</head>",
        '<script src="https://evil.example/_next/static/chunks/x.js"></script>'
        '<script src="//cdn.example/_next/static/chunks/y.js"></script></head>',
    )
    requests = []
    result = read({"/": foreign}, requests)
    assert result["status"] == "ok"
    assert {r.url.host for r in requests} == {"gdpx.semianalysis.com"}
    assert result["refused_references"] == [
        "https://evil.example/_next/static/chunks/x.js",
        "//cdn.example/_next/static/chunks/y.js",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/_next/static/chunks/x.js",
        "http://gdpx.semianalysis.com/",
        "https://gdpx.semianalysis.com/terms",
        "https://gdpx.semianalysis.com/_next/static/../../secret",
        "https://gdpx.semianalysis.com/_next/static/x.js?v=1",
        "https://user:pw@gdpx.semianalysis.com/",
        "https://gdpx.semianalysis.com:8443/",
    ],
)
def test_text_mode_is_pinned_to_homepage_and_static_paths(url):
    requests = []
    with pytest.raises(ValueError, match="untrusted_gdpx_url"):
        reader_budget(site(requests=requests)).get(url, None, text=True)
    assert requests == []


def test_text_mode_keeps_byte_cap():
    with pytest.raises(GdpxError) as caught:
        gdpx(reader_budget(site(), max_bytes=1000))
    assert caught.value.code == "fetch_failed"
    assert caught.value.detail == "response_size_cap"


def test_version_label_or_task_total_change_is_flagged_not_blocking():
    baseline = read()["version_probe"]
    relabeled = HOMEPAGE.replace(">v1.0</span>", ">v2.0</span>")
    result = read({"/": relabeled}, previous_probe=baseline)
    assert result["status"] == "ok"
    assert result["version_probe"]["label"] == "v2.0"
    assert result["anomalies"] == ["version_label_changed"]
    data = dataset()
    for row in data["results"]:
        if row["partnerId"] == "aria":
            row["tasks"] += 1
    result = read({DATA_PATH: chunk_with(data)}, previous_probe=baseline)
    assert result["status"] == "ok"
    assert result["anomalies"] == ["task_totals_changed"]
    assert result["version_probe"]["task_totals"]["aria"] == [11]
    assert read(previous_probe=baseline)["anomalies"] == []


def test_unreadable_version_label_is_flagged_not_blocking():
    # Zero version labels: nothing on the homepage matches a vX.Y span.
    unlabeled = HOMEPAGE.replace(">v1.0</span>", ">unreleased</span>")
    result = read({"/": unlabeled})
    assert result["status"] == "ok"
    assert result["version_probe"]["label"] is None
    assert result["anomalies"] == ["version_label_unreadable"]
    # Two distinct version labels: the probe can't pick one.
    duplicated = HOMEPAGE.replace(
        "</head>", '<span class="hidden">v9.9</span></head>'
    )
    assert duplicated != HOMEPAGE
    result = read({"/": duplicated})
    assert result["status"] == "ok"
    assert result["version_probe"]["label"] is None
    assert result["anomalies"] == ["version_label_unreadable"]
