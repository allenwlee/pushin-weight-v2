"""General's separate assurance declaration preserves the existing Pro model."""

import hashlib
import json
from pathlib import Path

from bridgewright.assurance.contracts import AssuranceDeclaration, AssuranceEvidence
from bridgewright.assurance.engine import control_model_digest

ROOT = Path(__file__).resolve().parents[2]
DECLARATION_PATH = ROOT / "tests/fixtures/ui_assurance/general-declaration.json"


def product_identity():
    paths = [
        ROOT / "core/models.py",
        ROOT / "core/classification_contract.py",
        ROOT / "core/intelligence_readers.py",
        ROOT / "monitor/post_artifacts.py",
        ROOT / "monitor/views.py",
        ROOT / "monitor/templates/monitor/_cyber_quan_sprite.html",
        ROOT / "project/settings.py",
        ROOT / "project/locale_cookie.py",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
        ROOT / "monitor/general_readers.py",
        ROOT / "monitor/general_views.py",
        ROOT / "monitor/original_content.py",
        ROOT / "monitor/original_content_readers.py",
        ROOT / "monitor/editorial/config.py",
        ROOT / "monitor/editorial/readers.py",
        ROOT / "monitor/editorial/views.py",
        ROOT / "config/editorial.yaml",
        ROOT / "monitor/content_readers.py",
        ROOT / "monitor/content_views.py",
        ROOT / "monitor/urls.py",
        ROOT / "monitor/templates/monitor/general.html",
        *sorted((ROOT / "monitor/templates/monitor/general").glob("*.html")),
        *sorted((ROOT / "monitor/templates/monitor/content").glob("*.html")),
        ROOT / "monitor/static/monitor/general.css",
        ROOT / "monitor/static/monitor/general.js",
        ROOT / "monitor/static/monitor/content.js",
        ROOT / "locale/ja/LC_MESSAGES/django.mo",
        ROOT / "locale/zh_Hans/LC_MESSAGES/django.mo",
    ]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(
            str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes() + b"\0"
        )
    return "worktree-sha256:" + digest.hexdigest()


def load_general_declaration():
    declaration = AssuranceDeclaration.model_validate_json(DECLARATION_PATH.read_text())
    assert declaration.source_revision == product_identity(), (
        "General product source changed; refresh and review the declared identity before verification"
    )
    fixture = ROOT / declaration.fixture.path
    assert (
        hashlib.sha256(fixture.read_bytes()).hexdigest() == declaration.fixture.sha256
    )
    return declaration


def write_general_evidence(declaration, results, path):
    evidence = AssuranceEvidence.model_validate(
        {
            "schema_version": "bridgewright.assurance.evidence/v1",
            "profile": "stateful-ui-assurance/v1",
            "identity": {
                "source_revision": declaration.source_revision,
                "candidate_revision": product_identity(),
                "fixture_digest": declaration.fixture.sha256,
                "control_model_digest": control_model_digest(declaration),
                "generator": declaration.generator.label(),
                "environments": [
                    {"id": "desktop-chromium", "browser_runtime": "playwright-chromium"}
                ],
            },
            "results": results,
        }
    )
    path.write_text(json.dumps(evidence.model_dump(mode="json"), indent=2) + "\n")
    return evidence
