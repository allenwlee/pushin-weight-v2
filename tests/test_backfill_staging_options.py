"""Saved staging instructions cannot silently enter ordinary enrichment."""
import pytest

from scripts.backfill_month import RUNTIME_MODULES, execution_options, selected_runtime
from tests.test_backfill_month import recipe


@pytest.mark.parametrize("phase", ["enrich", "all"])
def test_saved_staging_recipe_refuses_ordinary_enrichment(phase):
    frozen = recipe()
    frozen["template"]["windows"][0]["collection_definition"]["scope"]["response_storage"] = "staging"
    with pytest.raises(ValueError, match="promote before enrichment"):
        execution_options(frozen, phase=phase)
    assert execution_options(frozen, phase="collect")["phase"] == "collect"


def test_staging_runtime_pins_the_new_transport_module():
    frozen = recipe()
    frozen["template"]["windows"][0]["collection_definition"]["scope"]["response_storage"] = "staging"
    runtime = {"runtime_revision": "b" * 40, "source_sha256": {p: "c" * 64 for p in RUNTIME_MODULES}}
    with pytest.raises(ValueError, match="sources_invalid"):
        selected_runtime(frozen, runtime)
    runtime["source_sha256"].update({p: "c" * 64 for p in ["monitor/backfill_staging.py", "monitor/backfill_collection.py", "monitor/run_lock.py"]})
    assert selected_runtime(frozen, runtime)["runtime_revision"] == "b" * 40
