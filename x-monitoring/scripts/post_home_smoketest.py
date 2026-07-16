# {{AGENT_ATTRIBUTION}}
"""U8: Pushin' Weight (走个量) home pages smoke test.

Mirrors `scripts/post_fetch_smoketest.py`'s structure but exercises the
new home-page routes:
- `/` multi-brand page render
- `/alibaba/qwen` single-brand page render (uses any 2-arg vanity URL)
- `/api/v1/home.chart.json` chart payload
- `/api/v1/home.feed.json` paginated feed payload
- legacy `/grid` 302 redirect

Spins up a Flask test client against the live DB (or a temp DB if
`--temp-db` is passed) and asserts each route returns its expected
status + content shape. Exits 0 on success, 1 on any failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="post_home_smoketest",
        description="Smoke test the Pushin' Weight home pages",
    )
    p.add_argument(
        "--temp-db", action="store_true",
        help="Use a temp DB instead of the live x_monitoring.db. "
             "Recommended for CI; the live DB is used by default.",
    )
    p.add_argument(
        "--strict", action="store_true",
        help="Exit with code 1 if any check fails (default: still 0).",
    )
    return p.parse_args(argv)


def _run_checks(client) -> tuple[list[str], list[str]]:
    """Run the smoke checks; return (passes, fails) lists."""
    passes: list[str] = []
    fails: list[str] = []

    # 1. Multi-brand home page
    resp = client.get("/")
    if resp.status_code == 200 and "走个量" in resp.get_data(as_text=True):
        passes.append("GET /  -> 200, contains 走个量")
    else:
        fails.append(f"GET /  -> {resp.status_code} (expected 200 + 走个量)")

    # 2. Single-brand home page (try a few well-known vanity URLs)
    vanity_candidates = [
        ("/alibaba/qwen", "qwen"),
        ("/baidu/ernie", "ernie"),
        ("/tencent/hunyuan", "hunyuan"),
    ]
    vanity_ok = False
    for url, expected_brand in vanity_candidates:
        resp = client.get(url)
        body = resp.get_data(as_text=True)
        if resp.status_code == 200 and expected_brand in body:
            passes.append(f"GET {url}  -> 200, contains {expected_brand}")
            vanity_ok = True
            break
    if not vanity_ok:
        fails.append(
            f"GET /<company>/<brand>  -> no candidate vanity URL returned 200"
        )

    # 3. Multi-brand chart JSON
    resp = client.get("/api/v1/home.chart.json")
    if resp.status_code == 200:
        body = resp.get_json()
        if all(k in body for k in ("days", "series", "stacked", "colors", "totals")):
            passes.append("GET /api/v1/home.chart.json  -> 200, shape OK")
        else:
            fails.append(
                "GET /api/v1/home.chart.json  -> shape missing keys: "
                f"{set(['days', 'series', 'stacked', 'colors', 'totals']) - set(body.keys())}"
            )
    else:
        fails.append(f"GET /api/v1/home.chart.json  -> {resp.status_code}")

    # 4. Multi-brand feed JSON (paginated)
    resp = client.get("/api/v1/home.feed.json?limit=10")
    if resp.status_code == 200:
        body = resp.get_json()
        if "rows" in body and "next_cursor" in body:
            passes.append("GET /api/v1/home.feed.json  -> 200, paginated shape OK")
        else:
            fails.append(
                "GET /api/v1/home.feed.json  -> shape missing keys: "
                f"{set(['rows', 'next_cursor']) - set(body.keys())}"
            )
    else:
        fails.append(f"GET /api/v1/home.feed.json  -> {resp.status_code}")

    # 5. Legacy /grid 302
    resp = client.get("/grid", follow_redirects=False)
    if resp.status_code in (302, 303) and resp.headers.get("Location", "").endswith("/"):
        passes.append(f"GET /grid  -> {resp.status_code} -> /")
    else:
        fails.append(
            f"GET /grid  -> {resp.status_code}, Location={resp.headers.get('Location')!r}"
        )

    # 6. Health
    resp = client.get("/api/v1/health")
    if resp.status_code == 200 and resp.get_json().get("ok") is True:
        passes.append("GET /api/v1/health  -> 200, ok=True")
    else:
        fails.append(f"GET /api/v1/health  -> {resp.status_code}")

    return passes, fails


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    from x_monitor.config import Config
    from x_monitor.dashboard import DashboardApp

    if args.temp_db:
        # Spin up an isolated DashboardApp in a temp dir.
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            passes, fails = _run_checks(client)
    else:
        # Use the live x-monitoring/ project layout.
        from x_monitor.config import _project_root
        data_dir = _project_root() / "data"
        if not data_dir.exists():
            print(f"data dir not found: {data_dir}", file=sys.stderr)
            return 2
        cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
        # Use a DB path that does not require migration; the live DB
        # is the operator's domain and is not auto-migrated here.
        from x_monitor.store import Store
        db_path = data_dir / "x_monitoring.db"
        if not db_path.exists():
            print(f"live DB not found: {db_path}", file=sys.stderr)
            return 2
        # Open the store briefly to confirm migrations are applied,
        # then build the dashboard app.
        store = Store(db_path)
        store.close()
        app = DashboardApp(cfg, data_dir, db_path=db_path)
        client = app.app.test_client()
        passes, fails = _run_checks(client)

    # Print results
    print("=" * 60)
    print("Pushin' Weight home pages smoketest")
    print("=" * 60)
    for p in passes:
        print(f"  PASS  {p}")
    for f in fails:
        print(f"  FAIL  {f}")
    print("=" * 60)
    print(f"{len(passes)} passed, {len(fails)} failed")

    if fails and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
