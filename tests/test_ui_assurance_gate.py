from __future__ import annotations

import argparse

import pytest

from tests.ui_assurance import gate


def test_candidate_gate_rejects_missing_performance_inputs_before_running_checks() -> None:
    with pytest.raises(SystemExit) as error:
        gate.main(
            [
                "--scope",
                "candidate",
                "--candidate-revision",
                "d" * 40,
            ]
        )

    assert error.value.code == 2


def test_candidate_gate_allows_distinct_product_and_performance_revisions() -> None:
    args = argparse.Namespace(
        scope="candidate",
        candidate_revision="a" * 40,
        performance_state_home="/private/tmp/state",
        performance_runtime="/private/tmp/runtime",
        performance_target_revision="b" * 40,
        performance_installed_package_commit="c" * 40,
        performance_data_source_identity="environment:https://example.test",
        performance_data_source_kind="environment",
        performance_declaration="tests/fixtures/performance_assurance/declaration.json",
        performance_fixture_digest=None,
    )
    gate._require_candidate_performance_args(args, argparse.ArgumentParser())
