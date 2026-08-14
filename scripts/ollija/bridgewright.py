from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from .config import ProjectConfig
from .git import CommandRunner, SubprocessRunner


class BridgewrightError(ValueError):
    """Bridgewright cannot provide current, clean candidate evidence."""


@dataclass(frozen=True, slots=True)
class BridgewrightEvidence:
    status: str
    source_revision: str
    version: str
    capability_schema: str
    skill_digest: str
    manifest_path: str
    evidence_id: str

    def to_payload(self) -> dict[str, str]:
        return {
            "status": self.status,
            "source_revision": self.source_revision,
            "version": self.version,
            "capability_schema": self.capability_schema,
            "skill_digest": self.skill_digest,
            "manifest_path": self.manifest_path,
            "evidence_id": self.evidence_id,
        }


def _json(stdout: str, *, code: str) -> Mapping[str, object]:
    try:
        body = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BridgewrightError(code) from exc
    if not isinstance(body, Mapping):
        raise BridgewrightError(code)
    return body


def collect_bridgewright_evidence(
    config: ProjectConfig,
    *,
    runner: CommandRunner | None = None,
) -> BridgewrightEvidence:
    specification = config.tooling.get("bridgewright")
    if not isinstance(specification, Mapping):
        raise BridgewrightError("bridgewright_tool_invalid")
    executable = specification.get("executable")
    if not isinstance(executable, str) or not executable:
        raise BridgewrightError("bridgewright_tool_invalid")
    active = runner or SubprocessRunner()
    capabilities_result = active.run(
        (executable, "capabilities"),
        cwd=config.root,
        timeout=30,
    )
    if capabilities_result.returncode != 0:
        raise BridgewrightError("bridgewright_capabilities_unavailable")
    capabilities = _json(
        capabilities_result.stdout,
        code="bridgewright_capabilities_invalid",
    )
    contract = capabilities.get("capability_contract")
    if not isinstance(contract, Mapping) or capabilities.get("status") != "clean":
        raise BridgewrightError("bridgewright_capabilities_not_clean")
    build = contract.get("build_identity")
    if not isinstance(build, Mapping) or build.get("clean") is not True:
        raise BridgewrightError("bridgewright_build_not_clean")

    validation_result = active.run(
        (executable, "validate", "--project-root", str(config.root)),
        cwd=config.root,
        timeout=30,
    )
    if validation_result.returncode != 0:
        raise BridgewrightError("bridgewright_project_invalid")
    validation = _json(
        validation_result.stdout,
        code="bridgewright_validation_invalid",
    )
    if validation.get("status") != "clean" or validation.get("findings") != []:
        raise BridgewrightError("bridgewright_project_not_clean")
    manifest_path = validation.get("manifest_path")
    expected_manifest = str(config.root / str(config.bridgewright.get("config_path")))
    if manifest_path != expected_manifest:
        raise BridgewrightError("bridgewright_manifest_identity_mismatch")

    safe = {
        "status": "clean",
        "source_revision": str(build.get("source_revision", "")),
        "version": str(build.get("version", "")),
        "capability_schema": str(build.get("capability_schema", "")),
        "skill_digest": str(build.get("skill_digest", "")),
        "manifest_path": str(manifest_path),
    }
    if not all(safe.values()):
        raise BridgewrightError("bridgewright_evidence_incomplete")
    evidence_id = hashlib.sha256(
        json.dumps(safe, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return BridgewrightEvidence(**safe, evidence_id=evidence_id)
