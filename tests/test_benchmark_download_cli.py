import json
import subprocess
import sys

import httpx
import pytest

from scripts.benchmark_download_collector.collect import collect, load_snapshots
from scripts.benchmark_download_collector.identity import write_new
from scripts.benchmark_download_collector.report import render_report
from scripts.benchmark_download_collector.series import build_report
from scripts.benchmark_download_collector.sources import Budget
from tests.test_benchmark_download_identity import inputs
from tests.test_benchmark_download_sources import arena_page, arena_row, or_payload


def test_real_collection_persistence_and_report_chain(tmp_path):
    catalog, mapping = inputs()
    mapping["mappings"].append(
        {
            "source": "openrouter",
            "source_id": "maker/alpha-1",
            "product_key": catalog["products"][0]["product_key"],
            "evidence": "https://example.com/alpha",
        }
    )

    def respond(request):
        if request.url.host == "datasets-server.huggingface.co":
            return httpx.Response(200, json=arena_page([arena_row("alpha-1-thinking")]))
        if request.url.host == "openrouter.ai":
            assert request.headers["authorization"] == "Bearer private-test-key"
            return httpx.Response(200, json=or_payload())
        assert "authorization" not in request.headers
        return httpx.Response(
            200, json={"id": "maker/Alpha-1", "downloads": 20, "downloadsAllTime": 99}
        )

    directory = tmp_path / "observations"
    for _ in range(2):
        path, snapshot = collect(
            catalog,
            mapping,
            directory,
            Budget(httpx.Client(transport=httpx.MockTransport(respond))),
            start_date="2026-10-01",
            end_date="2026-10-01",
            openrouter_key="private-test-key",
            arena_history=True,
        )
        assert all(s["status"] == "ok" for s in snapshot["sources"].values())
        assert "private-test-key" not in path.read_text()
    report = build_report(load_snapshots(directory), "2026-10-01", "2026-10-01")
    point = report["series"][0]["points"][0]
    assert point["arena"]["value"] == 1400
    assert point["openrouter"]["value"] == "9007199254740993"
    assert point["posts"] == 0
    output = tmp_path / "report.html"
    render_report(report, output)
    assert output.exists()


def test_partial_failure_persists_safe_outcomes_and_contract_refuses_drift(tmp_path):
    catalog, mapping = inputs()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(401, text="secret-server-body")
        )
    )
    path, snapshot = collect(
        catalog,
        mapping,
        tmp_path,
        Budget(client),
        start_date="2026-10-01",
        end_date="2026-10-01",
    )
    assert snapshot["sources"]["arena"]["status"] == "error"
    assert snapshot["sources"]["openrouter"]["error"] == "missing_openrouter_key"
    assert snapshot["sources"]["hf"]["status"] == "partial"
    assert "secret-server-body" not in path.read_text()
    mapping["mappings"].pop()
    with pytest.raises(ValueError, match="new collection directory"):
        collect(
            catalog,
            mapping,
            tmp_path,
            Budget(client),
            start_date="2026-10-01",
            end_date="2026-10-01",
        )
    assert len(load_snapshots(tmp_path)) == 1


def test_atomic_write_never_overwrites(tmp_path):
    path = tmp_path / "snapshot.json"
    write_new(path, {"first": True})
    with pytest.raises(FileExistsError):
        write_new(path, {"first": False})
    assert json.loads(path.read_text()) == {"first": True}
    assert list(tmp_path.glob(".collector-*")) == []


def test_actual_offline_cli_demo_report_and_mapping_template(tmp_path):
    module = [sys.executable, "-m", "scripts.benchmark_download_collector"]
    directory, output = tmp_path / "demo", tmp_path / "demo.html"
    run = subprocess.run(
        [*module, "demo", "--directory", str(directory), "--output", str(output)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert "SYNTHETIC DEMO" in output.read_text()
    catalog, _ = inputs()
    catalog_path = tmp_path / "catalog.json"
    write_new(catalog_path, catalog)
    mapping_path = tmp_path / "mapping.json"
    run = subprocess.run(
        [
            *module,
            "mapping-template",
            "--catalog",
            str(catalog_path),
            "--output",
            str(mapping_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(mapping_path.read_text())["mappings"] == []
    run = subprocess.run(
        [
            *module,
            "validate",
            "--catalog",
            str(catalog_path),
            "--mapping",
            str(mapping_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    run = subprocess.run(
        [
            *module,
            "report",
            "--directory",
            str(directory),
            "--start-date",
            "2026-09-21",
            "--end-date",
            "2026-10-04",
            "--output",
            str(tmp_path / "second.html"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
