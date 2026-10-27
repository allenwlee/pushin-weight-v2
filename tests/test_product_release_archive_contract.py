"""Strict packet checks preserve accepted historical source shapes."""

import pytest

from core.product_release_dossiers import _validate_record


@pytest.mark.parametrize("confidence", [0.4, "0.4", "low", "medium", "high"])
def test_archived_release_confidence_accepts_saved_source_shapes(confidence):
    record = {"model_name": "Model", "confidence": confidence}
    assert _validate_record(record) is record


@pytest.mark.parametrize(
    "record",
    [
        {"model_name": "Model", "new_unreviewed_key": "value"},
        {"model_name": ""},
        {"model_name": "Model", "categories": "llm-model"},
        {"model_name": "Model", "confidence": "very high"},
        {"model_name": "Model", "confidence": 1.1},
        {"model_name": "Model", "confidence": float("nan")},
    ],
)
def test_archived_release_rejects_unreviewed_shapes(record):
    with pytest.raises(ValueError):
        _validate_record(record)
