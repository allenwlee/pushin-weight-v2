from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass

from .config import ProjectConfig


@dataclass(frozen=True, slots=True)
class ImpactAssessment:
    ui_required: bool
    matched_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]
    required_approvals: tuple[str, ...]
    required_evidence: tuple[str, ...]
    surface_fingerprint: str


def assess_ui_impact(
    config: ProjectConfig,
    changed_paths: list[str] | tuple[str, ...],
) -> ImpactAssessment:
    patterns = config.ui_impact.get("path_patterns")
    if not isinstance(patterns, list) or not all(
        isinstance(pattern, str) and pattern for pattern in patterns
    ):
        raise ValueError("ui_impact_patterns_invalid")
    changed = tuple(sorted(set(changed_paths)))
    matched = tuple(
        path
        for path in changed
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
    )
    ui_required = bool(matched)
    approvals = ("desktop", "iphone") if ui_required else ("desktop",)
    evidence = ("bridgewright",) if ui_required else ()
    body = {
        "changed_paths": changed,
        "matched_paths": matched,
        "required_approvals": approvals,
        "required_evidence": evidence,
    }
    fingerprint = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ImpactAssessment(
        ui_required=ui_required,
        matched_paths=matched,
        changed_paths=changed,
        required_approvals=approvals,
        required_evidence=evidence,
        surface_fingerprint=fingerprint,
    )
