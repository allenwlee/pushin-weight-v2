"""Measure the real Each GET route against existing data, with read-only sessions.

Run as a bounded operator job from the candidate image. This starts only a local
HTTP listener; it never runs a test runner, fixture writer, provider or scheduler.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path
from threading import Thread
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from wsgiref.simple_server import WSGIRequestHandler, make_server
from zoneinfo import ZoneInfo

TABS = ("sentiment", "post_types", "lang", "role", "audience_topics",
        "geopolitical_modes", "product_labels", "untracked_brand_promotions")


def prepare_materialization():
    """Use the normal publication path, then compare bounded raw-fact pages."""
    from importlib import import_module
    from django.db import connection, transaction
    from core.materializations import refresh_materialization
    from monitor.each_chart_facts import EACH_FACTS

    if os.environ.get("PW_DATABASE_ACCESS_MODE") == "serving":
        raise RuntimeError("Preparation requires the existing owner maintenance image")
    for label, force, cap in (("initial", False, 120), ("concurrent", True, 90)):
        start = monotonic()
        result = refresh_materialization(EACH_FACTS, force=force)
        elapsed = monotonic()-start
        print(json.dumps({"event": "refresh", "kind": label, "seconds": elapsed, **result}), flush=True)
        if result["status"] not in ({"refreshed", "skipped"} if not force else {"refreshed"}) or elapsed > cap:
            raise RuntimeError("Materialization publication/refresh gate failed")
    module = import_module("core.migrations.0235_each_chart_facts")
    columns = [name.strip() for name in module.COLUMNS.split(",")]
    assert len(columns) == 20
    collated = set(columns)-{"created_at", "author_account_key", "state_present"}
    # Identifiers come only from the frozen migration, never arguments or data.
    mismatch = " OR ".join(
        f'(actual."{name}" COLLATE "C") IS DISTINCT FROM (saved."{name}" COLLATE "C")'
        if name in collated else f'actual."{name}" IS DISTINCT FROM saved."{name}"'
        for name in columns
    )
    checked, last = 0, None
    started = monotonic()
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cursor.execute("SET LOCAL statement_timeout='3s'")
        cursor.execute("SET LOCAL lock_timeout='250ms'")
        cursor.execute("SET LOCAL work_mem='8MB'")
        cursor.execute("SELECT cutoff,source_generation,published_generation FROM materialization_state WHERE dataset_key=%s", [EACH_FACTS.dataset_key])
        cutoff, generation, published = cursor.fetchone()
        if generation != published or generation != result["generation"]:
            raise RuntimeError("History changed before parity snapshot; do not call this a mismatch")
        cursor.execute("SELECT count(*),count(*) FILTER(WHERE created_at >= %s) FROM each_brand_post_facts", [cutoff])
        saved_count, outside = cursor.fetchone()
        cursor.execute("SELECT count(*) FROM each_brand_post_facts_source WHERE created_at < %s", [cutoff])
        source_count = cursor.fetchone()[0]
        assert saved_count == source_count and not outside
        while True:
            if monotonic()-started > 300:
                raise RuntimeError("Bounded parity observation expired")
            where = "WHERE (brand_id,post_id) > (%s,%s)" if last else ""
            cursor.execute(f"""WITH page AS MATERIALIZED (
                SELECT {module.COLUMNS} FROM each_brand_post_facts {where}
                ORDER BY brand_id,post_id LIMIT 256
            ) SELECT count(*),count(*) FILTER(WHERE actual.post_id IS NULL OR {mismatch}),
                (SELECT brand_id FROM page ORDER BY brand_id DESC,post_id DESC LIMIT 1),
                (SELECT post_id FROM page ORDER BY brand_id DESC,post_id DESC LIMIT 1)
            FROM page saved LEFT JOIN LATERAL (
                SELECT {module.COLUMNS} FROM each_brand_post_facts_source
                WHERE brand_id=saved.brand_id AND post_id=saved.post_id OFFSET 0
            ) actual ON TRUE""", list(last) if last else [])
            count, differences, brand, post = cursor.fetchone()
            if not count:
                break
            if differences:
                raise RuntimeError("Typed raw-fact parity mismatch")
            checked += count
            last = (brand, post)
        assert checked == saved_count
    print(json.dumps({"event": "parity", "rows_checked": checked, "seconds": monotonic()-started,
        "generation": generation, "passed": True}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, choices=(1, 3), default=3)
    parser.add_argument("--brands", nargs="+", choices=("llama", "deepseek"), default=("llama", "deepseek"))
    parser.add_argument("--windows", nargs="+", type=int, choices=(1, 7, 30, 365), default=(7, 30, 365))
    parser.add_argument("--prepare", action="store_true", help="Explicit owner cache initialization/verification before read-only route measurement")
    parser.add_argument("--expected-revision")
    args = parser.parse_args()
    if args.prepare and (not args.expected_revision or os.environ.get("RENDER_GIT_COMMIT") != args.expected_revision):
        parser.error("Preparation requires the exact expected deployed revision")
    if len(set(args.brands)) != len(args.brands) or len(set(args.windows)) != len(args.windows):
        parser.error("Repeated brands/windows are not allowed")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ["POSTHOG_ENABLED"] = "false"
    import django
    django.setup()
    from django.conf import settings
    from django.core.wsgi import get_wsgi_application
    from django.db import connection, connections

    if args.prepare:
        try:
            prepare_materialization()
        except Exception as error:
            print(json.dumps({"event": "preparation_failed", "error": type(error).__name__}), flush=True)
            return 1

    # The ordinary locale resolver saves a session. This isolated operator uses
    # signed-cookie sessions, preserving view execution without production
    # session writes. Public verification still uses normal DB-backed sessions.
    settings.SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
    # Only this operator process changes its connection options. The PostgreSQL
    # server enforces read-only transactions even if application code regresses.
    options = settings.DATABASES["default"].setdefault("OPTIONS", {})
    options["options"] = (options.get("options", "") +
        " -c default_transaction_read_only=on -c statement_timeout=4500ms -c lock_timeout=250ms")
    connections.close_all()
    with connection.cursor() as cursor:
        cursor.execute("SHOW default_transaction_read_only")
        assert cursor.fetchone()[0] == "on"
        cursor.execute("SELECT current_user, current_database()")
        role, database = cursor.fetchone()
    connections.close_all()
    print(json.dumps({"event": "identity", "revision": os.environ.get("RENDER_GIT_COMMIT"),
        "role": role, "database": database, "read_only": True, "session_scope": "isolated operator signed cookies; final public sessions remain separately required",
        "started_jst": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()}), flush=True)

    configured_host = next(iter(settings.ALLOWED_HOSTS), "localhost")
    host = "localhost" if configured_host == "*" else "probe"+configured_host if configured_host.startswith(".") else configured_host
    phases = []
    application = get_wsgi_application()

    def measure(execute, sql, params, many, context):
        start = monotonic()
        try:
            return execute(sql, params, many, context)
        finally:
            phase = "publication_health" if "FROM materialization_state" in sql else "fact_groups" if "WITH facts AS" in sql else "other"
            brand = next((p for p in (params or ()) if isinstance(p, str) and p in {"llama", "deepseek"}), None)
            phases.append({"phase": phase, "brand": brand, "ms": round((monotonic()-start)*1000, 3)})

    def bounded_application(environ, start_response):
        if environ["REQUEST_METHOD"] != "GET" or environ["PATH_INFO"] != "/dashboard/each/chart/":
            raise RuntimeError("Operator probe only permits the chart GET route")
        with connection.execute_wrapper(measure):
            response = application(environ, start_response)
            try:
                yield from response
            finally:
                response.close()
                connections.close_all()

    class Quiet(WSGIRequestHandler):
        def log_message(self, *_args):
            pass

    server = make_server("127.0.0.1", 0, bounded_application, handler_class=Quiet)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    rows = []
    try:
        for round_number in range(args.rounds):
            for brand in args.brands:
                for window in args.windows:
                    for tab in TABS:
                        phases.clear()
                        query = urlencode({"brand": brand, "window": window, "tab": tab, "locale": "en", "tz": "Asia/Tokyo"})
                        request = Request(f"http://127.0.0.1:{server.server_port}/dashboard/each/chart/?{query}", headers={"Host": host, "X-Forwarded-Proto": "https"})
                        start = monotonic()
                        try:
                            with urlopen(request, timeout=6) as response:
                                status, payload = response.status, json.load(response)
                        except HTTPError as error:
                            status, payload = error.code, {}
                        except Exception as error:
                            status, payload = 0, {"error": type(error).__name__}
                        seconds = monotonic()-start
                        row = {"round": round_number+1, "brand": brand, "window": window, "tab": tab,
                            "status": status, "seconds": round(seconds, 6), "database_phases": list(phases),
                            "total": sum(payload.get("totals", []))}
                        rows.append(row)
                        print(json.dumps(row), flush=True)
                        if status != 200 or seconds >= 5 or payload.get("brand") != brand or payload.get("tab") != tab:
                            print(json.dumps({"event": "failed", "reason": "chart_latency_or_response", "completed": len(rows)}), flush=True)
                            return 1
        values = sorted(row["seconds"] for row in rows)
        p95 = statistics.quantiles(values, n=100, method="inclusive")[94]
        passed = p95 <= 1.5 and max(values) < 5
        print(json.dumps({"event": "summary", "count": len(rows), "p95_seconds": p95,
            "max_seconds": max(values), "passed": passed,
            "scope": "Candidate local HTTP route against existing data; final public web/browser validation remains required"}), flush=True)
        return 0 if passed else 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=6)
        connections.close_all()


if __name__ == "__main__":
    raise SystemExit(main())
