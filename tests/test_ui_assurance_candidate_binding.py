"""The real assurance assessor must accept the clean candidate, not an old SHA."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from bridgewright.assurance.engine import assess_evidence, compile_obligations

from tests.ui_assurance.evidence import build_evidence, load_documents
from tests.ui_assurance.gate import candidate_declaration


@pytest.fixture
def candidate_repo(tmp_path):
    fixture_dir = tmp_path / "tests/fixtures/ui_assurance"
    fixture_dir.mkdir(parents=True)
    for name in ("declaration.json", "data.json"):
        shutil.copyfile(Path("tests/fixtures/ui_assurance") / name, fixture_dir / name)
    for command in (
        ["git", "init", "-q"],
        ["git", "add", "tests"],
        [
            "git",
            "-c",
            "user.name=Assurance Test",
            "-c",
            "user.email=assurance@example.test",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(command, cwd=tmp_path, check=True)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    return tmp_path, revision


def test_bound_candidate_preserves_controls_and_passes_real_assessment(candidate_repo):
    root, revision = candidate_repo
    original, _ = load_documents(root)
    path = candidate_declaration(root, revision)
    bound, _ = load_documents(root, path)
    expected = original.model_dump(mode="json")
    expected["source_revision"] = revision
    assert bound.model_dump(mode="json") == expected
    assert [o.id for o in compile_obligations(bound)] == [
        o.id for o in compile_obligations(original)
    ]
    evidence = build_evidence(
        root,
        candidate_revision=revision,
        browser_runtime="playwright-chromium",
        declaration_path=path,
    )
    assert assess_evidence(bound, evidence).status == "clean"
    assert load_documents(root)[0] == original


def test_wrong_candidate_is_rejected(candidate_repo):
    root, _ = candidate_repo
    with pytest.raises(ValueError, match="checkout HEAD"):
        candidate_declaration(root, "a" * 40)


def test_dirty_candidate_is_rejected(candidate_repo):
    root, revision = candidate_repo
    path = root / "tests/fixtures/ui_assurance/declaration.json"
    data = json.loads(path.read_text())
    data["source_revision"] = revision
    path.write_text(json.dumps(data))
    with pytest.raises(subprocess.CalledProcessError):
        candidate_declaration(root, revision)
