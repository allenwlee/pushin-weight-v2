"""Bounded Render CLI read-only collector; no application imports."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
DATABASE = "dpg-d9koekqjobas73fvjqng-a"


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    args = parser.parse_args()
    assert args.query in {"language-census", "cohort-candidates", "cohort-candidates-v2", "coverage-candidates", "cohort-context", "catalog"}
    sql = (HERE / (args.query + ".sql")).read_text()
    assert sql.startswith("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
    assert "statement_timeout='45s'" in sql
    assert not any(word in sql.upper().split() for word in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"))
    assert len(list(HERE.glob("*-db-started.json"))) < 8
    stem = args.query
    save(HERE / (stem + "-db-started.json"), {
        "issued_at": datetime.now(timezone.utc).isoformat(), "database_service": DATABASE,
        "query_file": stem + ".sql", "query_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        "provider": "Production PostgreSQL via Render CLI on authoritative fuchitalee",
        "read_only": True, "timeout_seconds": 45,
    })
    result = subprocess.run(
        ["render", "psql", DATABASE, "--command", sql, "-o", "json", "--", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
        capture_output=True, text=True, timeout=65, check=False,
    )
    save(HERE / (stem + "-db-receipt.json"), {
        "completed_at": datetime.now(timezone.utc).isoformat(), "returncode": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr,
    })
    if result.returncode:
        raise SystemExit("database_query_failed_see_saved_receipt")
    envelope = json.loads(result.stdout)
    save(HERE / (stem + "-render-result.json"), envelope)
    print(json.dumps({"query": stem, "status": "captured", "envelope_type": type(envelope).__name__,
                      "envelope_keys": list(envelope) if isinstance(envelope, dict) else None}))


if __name__ == "__main__":
    main()
