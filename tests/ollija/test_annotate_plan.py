from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ollija.annotate_plan import (
    AnnotationError,
    parse_plan_metadata,
    render_annotated_plan,
)
from scripts.ollija.config import ConfigError, load_project_config


def _write_contract(root: Path) -> None:
    (root / ".ollija" / "templates").mkdir(parents=True)
    (root / ".ollija" / "project.yaml").write_text(
        f"""\
schema_version: 1
authority:
  canonical_host: fuchitalee
  repository_root: {root}
  repository_slug: allenwlee/pushin-weight-v2
  release_worktree_label: Ollija release worktree area
  release_worktree_path: .worktrees
plans:
  directory: docs/plans
git:
  remote: origin
  staging_branch: staging
  production_branch: main
environments:
  staging:
    blueprint: render-staging.yaml
    url: https://pushinweight-staging-web.onrender.com
    service: pushinweight-staging-web
  production:
    blueprint: render.yaml
    url: https://pushinweight-web.onrender.com
    service: pushinweight-web
delivery:
  template: .ollija/templates/delivery-guide.md
  test_commands: [pytest tests/ollija]
  code_failure_route: parent LFG workflow
  infra_failure_route: infra/multi-machine skill
""",
        encoding="utf-8",
    )
    (root / ".ollija" / "templates" / "delivery-guide.md").write_text(
        (Path(__file__).resolve().parents[2] / ".ollija" / "templates" / "delivery-guide.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _plan(*, target: str = "on-request", selected: bool = False) -> str:
    return f"""\
---
title: Example
ollija:
  change_id: example-1
  branch: feat/example
  workflow: lfg
  delivery_target: {target}
  delivery_selected_by_user: {str(selected).lower()}
---

# Example

Plan body.\n"""


def _configured(tmp_path: Path):
    _write_contract(tmp_path)
    return load_project_config(tmp_path)


def _render(content: str, *, config, plan_path: Path, active_worktree: Path) -> str:
    return render_annotated_plan(
        content,
        config=config,
        plan_path=plan_path,
        active_worktree=active_worktree,
    )[0]


def test_inserts_markerless_guide_after_frontmatter_before_first_heading(tmp_path: Path) -> None:
    config = _configured(tmp_path)
    plan_path = tmp_path / "docs" / "plans" / "example.md"

    annotated = _render(
        _plan(),
        config=config,
        plan_path=plan_path,
        active_worktree=tmp_path / ".worktrees" / "feat" / "example",
    )

    assert annotated.index("<!-- BEGIN OLLIJA DELIVERY GUIDE -->") < annotated.index("# Example")
    assert annotated.index("<!-- END OLLIJA DELIVERY GUIDE -->") < annotated.index("## Delivery Exceptions")
    assert annotated.endswith("# Example\n\nPlan body.\n")


def test_replaces_only_existing_generated_span_and_preserves_exception_bytes(tmp_path: Path) -> None:
    config = _configured(tmp_path)
    plan_path = tmp_path / "docs" / "plans" / "example.md"
    original = _plan(target="staging", selected=True).replace(
        "# Example",
        "<!-- BEGIN OLLIJA DELIVERY GUIDE -->\nold guide\n<!-- END OLLIJA DELIVERY GUIDE -->\n\n## Delivery Exceptions\n\nKeep  two spaces.\n\n# Example",
    )

    annotated = _render(
        original,
        config=config,
        plan_path=plan_path,
        active_worktree=tmp_path / ".worktrees" / "feat" / "example",
    )

    old_start = original.index("<!-- BEGIN OLLIJA DELIVERY GUIDE -->")
    old_end = original.index("<!-- END OLLIJA DELIVERY GUIDE -->") + len("<!-- END OLLIJA DELIVERY GUIDE -->")
    new_start = annotated.index("<!-- BEGIN OLLIJA DELIVERY GUIDE -->")
    new_end = annotated.index("<!-- END OLLIJA DELIVERY GUIDE -->") + len("<!-- END OLLIJA DELIVERY GUIDE -->")
    assert annotated[:new_start] == original[:old_start]
    assert annotated[new_end:] == original[old_end:]


def test_replacement_preserves_crlf_bytes_outside_the_marker_span(tmp_path: Path) -> None:
    config = _configured(tmp_path)
    plan_path = tmp_path / "docs" / "plans" / "example.md"
    original = _plan().replace(
        "# Example",
        "<!-- BEGIN OLLIJA DELIVERY GUIDE -->\nold\n<!-- END OLLIJA DELIVERY GUIDE -->\n\n## Delivery Exceptions\n\nDo not normalize this.\n\n# Example",
    ).replace("\n", "\r\n")

    annotated = _render(
        original,
        config=config,
        plan_path=plan_path,
        active_worktree=tmp_path / ".worktrees" / "feat" / "example",
    )

    old_start = original.index("<!-- BEGIN OLLIJA DELIVERY GUIDE -->")
    old_end = original.index("<!-- END OLLIJA DELIVERY GUIDE -->") + len("<!-- END OLLIJA DELIVERY GUIDE -->")
    new_start = annotated.index("<!-- BEGIN OLLIJA DELIVERY GUIDE -->")
    new_end = annotated.index("<!-- END OLLIJA DELIVERY GUIDE -->") + len("<!-- END OLLIJA DELIVERY GUIDE -->")
    assert annotated.encode("utf-8")[:new_start] == original.encode("utf-8")[:old_start]
    assert annotated.encode("utf-8")[new_end:] == original.encode("utf-8")[old_end:]


def test_identical_inputs_are_byte_identical_and_relocation_replaces_paths(tmp_path: Path) -> None:
    config = _configured(tmp_path)
    plan_path = tmp_path / "docs" / "plans" / "example.md"
    initial_worktree = tmp_path / "elsewhere" / "example"

    first = _render(_plan(target="production", selected=True), config=config, plan_path=plan_path, active_worktree=initial_worktree)
    assert _render(first, config=config, plan_path=plan_path, active_worktree=initial_worktree).encode() == first.encode()
    assert str(initial_worktree.resolve()).encode() in first.encode()

    relocated = tmp_path / ".worktrees" / "feat" / "example"
    moved = _render(first, config=config, plan_path=plan_path, active_worktree=relocated)
    assert str(relocated.resolve()).encode() in moved.encode()
    assert str(initial_worktree.resolve()).encode() not in moved.encode()


def test_canonical_and_noncanonical_guidance_show_resolved_paths(tmp_path: Path) -> None:
    config = _configured(tmp_path)
    plan_path = tmp_path / "docs" / "plans" / "example.md"
    outside = tmp_path / "outside" / "example"
    required = tmp_path / ".worktrees" / "feat" / "example"

    outside_guide = _render(_plan(), config=config, plan_path=plan_path, active_worktree=outside)
    assert f"`{outside.resolve()}`" in outside_guide
    assert f"`{required.resolve()}`" in outside_guide
    assert "Rerun `./bin/ollija annotate-plan` after the move" in outside_guide

    canonical_guide = _render(outside_guide, config=config, plan_path=plan_path, active_worktree=required)
    assert "This worktree is inside the Ollija release worktree area" in canonical_guide
    assert "Move this worktree" not in canonical_guide

    nested_guide = _render(canonical_guide, config=config, plan_path=plan_path, active_worktree=required / "nested")
    assert "Move this worktree" in nested_guide


@pytest.mark.parametrize(
    ("target", "selected", "expected", "unexpected"),
    [
        ("on-request", False, "Wait for a later explicit release request", "push the exact candidate SHA"),
        ("staging", True, "push the exact candidate SHA to `refs/heads/staging`", "git push origin <candidate-sha>:refs/heads/main"),
        ("production", True, "push the exact candidate SHA to `refs/heads/main`", "Delivery target: `on-request`"),
        ("production", False, "Target is not authorized until the owner selects it", "refs/heads/main"),
    ],
)
def test_delivery_target_never_upgrades_plan_authority(tmp_path: Path, target: str, selected: bool, expected: str, unexpected: str) -> None:
    config = _configured(tmp_path)
    guide = _render(
        _plan(target=target, selected=selected),
        config=config,
        plan_path=tmp_path / "docs" / "plans" / "example.md",
        active_worktree=tmp_path / ".worktrees" / "feat" / "example",
    )

    assert expected in guide
    assert unexpected not in guide
    assert f"Owner selection recorded: `{str(selected).lower()}`" in guide


@pytest.mark.parametrize(
    "content",
    [
        "<!-- BEGIN OLLIJA DELIVERY GUIDE -->\n# body\n",
        "<!-- END OLLIJA DELIVERY GUIDE -->\n# body\n",
        "<!-- BEGIN OLLIJA DELIVERY GUIDE -->\n<!-- BEGIN OLLIJA DELIVERY GUIDE -->\n<!-- END OLLIJA DELIVERY GUIDE -->\n",
    ],
)
def test_malformed_markers_fail_without_mutating_source(tmp_path: Path, content: str) -> None:
    config = _configured(tmp_path)
    original = _plan().replace("# Example", content + "# Example")

    with pytest.raises(AnnotationError, match="marker"):
        _render(
            original,
            config=config,
            plan_path=tmp_path / "docs" / "plans" / "example.md",
            active_worktree=tmp_path / ".worktrees" / "feat" / "example",
        )

    assert original == _plan().replace("# Example", content + "# Example")


def test_safe_frontmatter_and_strict_paths_are_required(tmp_path: Path) -> None:
    unsafe = "---\nollija: !!python/object/apply:os.system ['false']\n---\n# Unsafe\n"
    with pytest.raises(AnnotationError, match="valid YAML"):
        parse_plan_metadata(unsafe)

    _write_contract(tmp_path)
    config_path = tmp_path / ".ollija" / "project.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("docs/plans", "../plans"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="repository-relative"):
        load_project_config(tmp_path)
