"""Prove the installed headline-worker SDK accepts the production request.

This verifier intentionally stops at ``inspect.signature(...).bind``.  It does
not send a provider request, read a provider credential, or touch the database.
"""

from __future__ import annotations

import importlib.metadata
import inspect
import os
import re
import sys
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIRECT_PIN_RE = re.compile(r"anthropic==([^;\s]+)", re.IGNORECASE)


class BoundaryVerificationError(RuntimeError):
    """A safe build-stopping headline-worker compatibility diagnostic."""


def direct_anthropic_pin(pyproject_path: Path = ROOT / "pyproject.toml") -> str:
    """Return the single exact direct Anthropic pin from project metadata."""
    with pyproject_path.open("rb") as source:
        dependencies = tomllib.load(source).get("project", {}).get(
            "dependencies", []
        )
    matches = []
    for dependency in dependencies:
        match = DIRECT_PIN_RE.fullmatch(str(dependency).strip())
        if match:
            matches.append(match.group(1))
    if len(matches) != 1:
        raise BoundaryVerificationError(
            "pyproject.toml must contain exactly one direct anthropic==VERSION pin"
        )
    return matches[0]


def assert_installed_version(*, expected: str, installed: str) -> None:
    """Fail when the build interpreter did not install the direct exact pin."""
    if installed != expected:
        raise BoundaryVerificationError(
            "installed anthropic version does not match direct pin "
            f"(expected {expected}, installed {installed})"
        )


def bind_request(
    create: Callable[..., Any],
    request: Mapping[str, Any],
) -> None:
    """Bind only; never invoke the provider method or transport."""
    try:
        inspect.signature(create).bind(**request)
    except (TypeError, ValueError) as exc:
        raise BoundaryVerificationError(
            "production headline request is incompatible with installed anthropic SDK"
        ) from exc


def verify_headline_worker_boundary() -> tuple[str, str]:
    """Verify compatibility without provider transport or database access."""
    expected = direct_anthropic_pin()
    try:
        installed = importlib.metadata.version("anthropic")
    except importlib.metadata.PackageNotFoundError as exc:
        raise BoundaryVerificationError(
            "anthropic distribution is not installed in the build interpreter"
        ) from exc
    assert_installed_version(expected=expected, installed=installed)

    # Import the same Django-backed module and config used by the queue worker.
    # Model registration is required at import time; setup opens no DB connection.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    import django

    django.setup()

    from monitor.trend_narrative_generation import (
        _anthropic_client,
        build_per_brand_critic_request,
        build_per_brand_editor_request,
        build_per_brand_rank_request,
    )
    from x_monitor.config import HeadlineNarrativeConfig

    config = HeadlineNarrativeConfig()
    packet = {
        "packet_schema_version": 3,
        "window_days": 1,
        "batch_key": "1d:boundary-proof",
        "manifest_brand_keys": ["boundary-proof"],
        "dossiers": [
            {
                "brand_key": "boundary-proof",
                "facts": [{"fact_id": "boundary-proof:volume"}],
                "evidence": [{"evidence_id": "ev:boundary-proof:01"}],
            }
        ],
    }
    _rank_envelope, rank_request = build_per_brand_rank_request(packet, config)
    editor_envelope, editor_request = build_per_brand_editor_request(packet, config)
    _critic_envelope, critic_request = build_per_brand_critic_request(
        editor_envelope,
        "{}",
        {"status": "invalid", "error_codes": ["boundary_proof"]},
        config,
    )
    requests = (rank_request, editor_request, critic_request)
    for request in requests:
        if request.get("model") != config.model:
            raise BoundaryVerificationError(
                "production headline request does not use the configured explicit model"
            )
        if request.get("thinking") != {"type": "disabled"}:
            raise BoundaryVerificationError(
                "production headline request must explicitly disable thinking"
            )
        if "temperature" in request:
            raise BoundaryVerificationError(
                "production headline request must omit temperature"
            )

    # The placeholder is supplied directly and is never read from environment or
    # sent anywhere.  Constructing and closing the client performs no transport.
    client = _anthropic_client(
        api_key="headline-boundary-proof-placeholder",
        base_url=config.base_url,
        timeout=float(config.timeout_seconds),
        max_retries=0,
    )
    try:
        for request in requests:
            bind_request(client.messages.create, request)
    finally:
        client.close()
    return installed, config.model


def main() -> int:
    try:
        version, model = verify_headline_worker_boundary()
    except BoundaryVerificationError as exc:
        print(f"headline_worker_boundary_failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - keep unexpected build failure safe
        print(
            "headline_worker_boundary_failed: unexpected verifier error "
            f"({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1
    print(f"headline_worker_boundary_ok anthropic={version} model={model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
