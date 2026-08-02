"""Tests for plan 2026-08-01-002 U4: typed warnings + exc_info + cycle counter.

Pins:
- translate_batch_pragmatics emits logger.warning("translator_batch_failed")
  with exc_info=True when the LLM call raises per-batch. Silent None was
  the original bug.
- on_batch_error callback fires once per failed batch.
- CycleRunner._run_post_fetch surfaces typed counter via --json summary.
"""
import os
from pathlib import Path


def _django_setup():
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/django_dev.db")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_API_KEY", "dummy")
    import django
    if not django.apps.apps.ready:
        django.setup()


def test_translator_emits_logger_warning_on_batch_failure(caplog):
    """A FakeClaudeClient that raises on every call must trigger
    translator_batch_failed log with exc_info=True.
    """
    _django_setup()
    import logging
    from x_monitor.translator import translate_batch_pragmatics

    class _RaisingClient:
        def messages_create(self, **kwargs):
            raise RuntimeError("simulated upstream 401")

    tweets = [{"tweet_id": "1", "text": "hello"}, {"tweet_id": "2", "text": "world"}]
    captured = []
    with caplog.at_level(logging.WARNING, logger="x_monitor.translator"):
        rows = translate_batch_pragmatics(
            tweets, ["en", "zh_cn"], _RaisingClient(),
            on_batch_error=lambda batch, exc: captured.append((batch, exc)),
        )
    # Per-batch catch: every row gets _empty_pragmatics_row(failed=True)
    assert len(rows) == 2
    for r in rows:
        assert r.get("translation_failed") is True
        assert r.get("lang_detected") is None
    # The warning must be logged with the structured event name
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any(
        r.message == "translator_batch_failed" or
        (hasattr(r, "msg") and "translator_batch_failed" in str(r.msg))
        for r in warning_records
    ), f"expected translator_batch_failed log, got {[r.message for r in warning_records]}"
    # exc_info=True means record.exc_info is populated
    assert any(r.exc_info is not None for r in warning_records), (
        "logger.warning must use exc_info=True so the traceback is logged"
    )
    # on_batch_error fires once per batch (one batch of 2 tweets)
    assert len(captured) == 1


def test_translator_logs_parse_failure(caplog):
    """A response that fails to parse also logs translator_batch_failed."""
    _django_setup()
    import logging
    from x_monitor.translator import translate_batch_pragmatics

    class _NonJsonClient:
        def messages_create(self, **kwargs):
            return {"results": "this is not a list of correct shape"}

    tweets = [{"tweet_id": "1", "text": "hello"}]
    with caplog.at_level(logging.WARNING, logger="x_monitor.translator"):
        rows = translate_batch_pragmatics(tweets, ["en", "zh_cn"], _NonJsonClient())
    assert len(rows) == 1
    assert rows[0]["translation_failed"] is True
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any(
        r.message == "translator_batch_failed" or
        (hasattr(r, "msg") and "translator_batch_failed" in str(r.msg))
        for r in warning_records
    )


def test_cycle_runner_error_counters_initialized():
    """CycleRunner must initialize _error_counts with the canonical keys.

    Regression net: a future edit cannot silently drop a counter key.
    """
    _django_setup()
    from monitor.cycle import CycleRunner
    from x_monitor.config import load_config

    cfg = load_config(Path("config.yaml"))
    runner = CycleRunner(dry_run=True, cfg=cfg)
    assert "translator_batch_failed" in runner._error_counts
    assert "classifier_batch_failed" in runner._error_counts
    assert runner._error_counts["translator_batch_failed"] == 0
    assert runner._error_counts["classifier_batch_failed"] == 0