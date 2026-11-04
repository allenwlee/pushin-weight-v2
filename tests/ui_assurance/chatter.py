"""Declare Chatter's independent source, group and reading-language controls."""

import hashlib
from pathlib import Path

from bridgewright.assurance.contracts import AssuranceDeclaration

from .general import product_identity as general_identity

ROOT = Path(__file__).resolve().parents[2]
DECLARATION = ROOT / "tests/fixtures/ui_assurance/chatter-declaration.json"


def product_identity():
    digest = hashlib.sha256(general_identity().encode())
    for name in (
        "monitor/templates/monitor/editorial/pools.html",
        "monitor/templates/monitor/editorial/archive.html",
        "monitor/editorial/chatter_status.py",
        "monitor/static/monitor/editorial/editorial.css",
    ):
        digest.update(name.encode() + b"\0" + (ROOT / name).read_bytes())
    return "worktree-sha256:" + digest.hexdigest()


def load_declaration():
    declaration = AssuranceDeclaration.model_validate_json(DECLARATION.read_text())
    assert declaration.source_revision == product_identity(), (
        "Chatter UI source identity needs review and refresh"
    )
    assert (
        hashlib.sha256((ROOT / declaration.fixture.path).read_bytes()).hexdigest()
        == declaration.fixture.sha256
    )
    return declaration
