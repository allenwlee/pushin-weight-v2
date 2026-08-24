"""Build-time proof for the installed headline-worker provider boundary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verify_headline_worker_boundary import (
    BoundaryVerificationError,
    assert_installed_version,
    bind_request,
    direct_anthropic_pin,
)

ROOT = Path(__file__).resolve().parents[1]


def test_worker_boundary_proof_executes_without_transport():
    result = subprocess.run(
        [sys.executable, "scripts/verify_headline_worker_boundary.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("headline_worker_boundary_ok ")
    assert f"anthropic={direct_anthropic_pin()}" in result.stdout


def test_worker_boundary_rejects_installed_version_drift():
    expected = direct_anthropic_pin()
    with pytest.raises(
        BoundaryVerificationError,
        match="installed anthropic version does not match direct pin",
    ):
        assert_installed_version(expected=expected, installed=f"{expected}.drift")


def test_worker_boundary_rejects_request_signature_drift():
    def incompatible_create(*, model, max_tokens, messages, system):
        raise AssertionError("binding must never invoke transport")

    with pytest.raises(
        BoundaryVerificationError,
        match="request is incompatible with installed anthropic SDK",
    ):
        bind_request(
            incompatible_create,
            {
                "model": "deepseek-v4-pro",
                "max_tokens": 1_600,
                "messages": [],
                "system": "closed prompt",
                "thinking": {"type": "disabled"},
            },
        )


def test_build_runs_worker_boundary_proof_after_dependency_install():
    build = (ROOT / "build.sh").read_text(encoding="utf-8")

    install_offset = build.index('pip install -e ".[dev]"')
    proof_offset = build.index("python scripts/verify_headline_worker_boundary.py")

    assert install_offset < proof_offset
