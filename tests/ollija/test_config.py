from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ollija.config import ConfigError, load_project_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_config(root: Path, *, schema_version: int = 1) -> Path:
    config_dir = root / ".ollija"
    (config_dir / "templates").mkdir(parents=True)
    config_path = config_dir / "project.yaml"
    config_path.write_text(
        f"""\
schema_version: {schema_version}
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
  code_failure_route: parent workflow
  infra_failure_route: infra/multi-machine skill
""",
        encoding="utf-8",
    )
    (config_dir / "templates" / "delivery-guide.md").write_text("guide\n", encoding="utf-8")
    return config_path


def test_real_project_contract_loads_annotation_facts_from_nested_directory() -> None:
    config = load_project_config(REPO_ROOT / "tests" / "ollija")

    assert config.root == REPO_ROOT
    assert config.schema_version == 1
    assert config.authority.canonical_host == "fuchitalee"
    assert config.authority.release_worktree_label == "Ollija release worktree area"
    assert config.authority.release_worktree_path == Path(".worktrees")
    assert config.plans.directory == Path("docs/plans")
    assert config.git.remote == "origin"
    assert config.git.production_branch == "main"
    assert config.git.staging_branch == "staging"
    assert config.environments["staging"].url == "https://pushinweight-staging-web.onrender.com"
    assert config.template_path == REPO_ROOT / ".ollija" / "templates" / "delivery-guide.md"


def test_missing_project_contract_is_actionable_and_read_only(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"No \.ollija/project\.yaml"):
        load_project_config(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_malformed_unknown_and_unsafe_contracts_fail_actionably(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    config_dir = malformed / ".ollija"
    config_dir.mkdir()
    (config_dir / "project.yaml").write_text("schema_version: [", encoding="utf-8")
    with pytest.raises(ConfigError, match="valid YAML"):
        load_project_config(malformed)

    unknown = tmp_path / "unknown"
    unknown.mkdir()
    _write_config(unknown, schema_version=99)
    with pytest.raises(ConfigError, match="Unsupported project contract version 99"):
        load_project_config(unknown)

    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    unsafe_path = _write_config(unsafe)
    unsafe_path.write_text(
        unsafe_path.read_text(encoding="utf-8").replace("schema_version: 1", "schema_version: !!python/object/apply:os.system ['false']"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="valid YAML"):
        load_project_config(unsafe)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("directory: docs/plans", "directory: ../plans", "repository-relative"),
        ("release_worktree_path: .worktrees", "release_worktree_path: /tmp/worktrees", "repository-relative"),
        ("blueprint: render-staging.yaml", "blueprint: ../render.yaml", "repository-relative"),
        ("url: https://pushinweight-staging-web.onrender.com", "url: http://staging.example.com", "HTTPS base URL"),
    ],
)
def test_contract_rejects_paths_or_urls_outside_annotation_authority(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8"
    )

    with pytest.raises(ConfigError, match=message):
        load_project_config(tmp_path)


def test_contract_rejects_legacy_stateful_fields(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    with config_path.open("a", encoding="utf-8") as handle:
        handle.write("state: {directory: .ollija/state}\n")

    with pytest.raises(ConfigError, match="unknown fields: state"):
        load_project_config(tmp_path)
