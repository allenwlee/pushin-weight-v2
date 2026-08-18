from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ollija.adapters.pushinweight import PushinWeightAdapter
from scripts.ollija.config import ConfigError, load_project_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_config(root: Path, *, schema_version: int = 1) -> Path:
    config_dir = root / ".ollija"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "project.yaml"
    config_path.write_text(
        f"""\
schema_version: {schema_version}
adapter: pushinweight
authority:
  canonical_host: fuchitalee
  forbidden_hosts: [allenwlee]
  repository_root: {root}
  repository_slug: allenwlee/pushin-weight-v2
git:
  staging_branch: staging
  production_branch: main
versioning:
  source: pyproject.toml
  field: project.version
  prerelease: beta
state:
  directory: .ollija/state
  retention_days: 30
environments:
  local:
    database_name: pushinweight_local_staging
  staging:
    blueprint: render-staging.yaml
    web_service_name: pushinweight-staging-web
    database_name: pushinweight_staging
  production:
    blueprint: render.yaml
    web_service_name: pushinweight-web
    database_name: pushinweight_shadow
database_safety:
  production_resource_ids: [dpg-production]
  production_database_names: [pushinweight_shadow]
  staging_name_prefix: pushinweight_staging
  marker_table: ollija_environment_marker
verification:
  health_path: /accounts/login/
  smoke_path: /accounts/login/
ui_impact:
  path_patterns: [templates/**, static/**, bridgewright.yaml]
bridgewright:
  config_path: bridgewright.yaml
tooling:
  render:
    executable: render
    version_args: [--version]
    minimum_version: 2.22.0
""",
        encoding="utf-8",
    )
    return config_path


def test_real_project_contract_loads_from_a_nested_working_directory() -> None:
    config = load_project_config(REPO_ROOT / "tests" / "ollija")

    assert config.root == REPO_ROOT
    assert config.schema_version == 1
    assert config.adapter == "pushinweight"
    assert config.authority.canonical_host == "fuchitalee"
    assert config.authority.release_worktree_label == "Ollija release worktree area"
    assert config.authority.release_worktree_path == Path(".worktrees")
    assert config.git.production_branch == "main"
    assert config.git.staging_branch == "staging"
    assert config.state_root == config.authority.repository_root / ".ollija" / "state"


def test_missing_project_contract_is_actionable_and_read_only(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"No \.ollija/project\.yaml"):
        load_project_config(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_malformed_and_unknown_contract_versions_fail_actionably(tmp_path: Path) -> None:
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


def test_host_and_repository_mismatch_are_observed_without_writing_state(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_project_config(config_path)
    adapter = PushinWeightAdapter(config)

    observation = adapter.assess_authority(
        hostname="allenwlee",
        repository_root=tmp_path / "another-clone",
        repository_slug="someone/fork",
    )

    assert observation.mutation_allowed is False
    assert set(observation.reason_codes) == {
        "forbidden_host",
        "host_mismatch",
        "repository_root_mismatch",
        "repository_slug_mismatch",
    }
    assert not (tmp_path / ".ollija" / "state").exists()


def test_registered_repository_local_worktree_is_authorized(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_project_config(config_path)
    adapter = PushinWeightAdapter(config)
    worktree = tmp_path / ".worktrees" / "feat" / "example"
    worktree.mkdir(parents=True)

    observation = adapter.assess_authority(
        hostname="fuchitalee",
        repository_root=worktree,
        repository_slug="allenwlee/pushin-weight-v2",
        registered_worktree=True,
        common_git_directory=tmp_path / ".git",
    )

    assert observation.mutation_allowed is True
    assert observation.reason_codes == ()
    assert config.state_root == tmp_path / ".ollija" / "state"


def test_foreign_or_unregistered_worktree_is_rejected(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_project_config(config_path)
    adapter = PushinWeightAdapter(config)
    allowed_shape = tmp_path / ".worktrees" / "feat" / "example"
    allowed_shape.mkdir(parents=True)

    cases = (
        (allowed_shape, False, tmp_path / ".git"),
        (tmp_path / "worktrees" / "feat" / "example", True, tmp_path / ".git"),
        (allowed_shape, True, tmp_path / "other.git"),
    )
    for root, registered, common_git in cases:
        observation = adapter.assess_authority(
            hostname="fuchitalee",
            repository_root=root,
            repository_slug="allenwlee/pushin-weight-v2",
            registered_worktree=registered,
            common_git_directory=common_git,
        )
        assert observation.mutation_allowed is False
        assert "repository_root_mismatch" in observation.reason_codes


def test_contract_rejects_secret_shaped_fields(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    with config_path.open("a", encoding="utf-8") as handle:
        handle.write("database_password: should-not-be-here\n")

    with pytest.raises(ConfigError, match="secret-shaped field"):
        load_project_config(config_path)
