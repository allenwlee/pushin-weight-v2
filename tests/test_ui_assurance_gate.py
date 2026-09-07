from __future__ import annotations

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
