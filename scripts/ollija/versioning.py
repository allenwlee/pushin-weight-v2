from __future__ import annotations

import re
from dataclasses import dataclass


class VersionError(ValueError):
    """Package version and beta tag do not form a release identity."""


_BETA = re.compile(r"^(?P<base>\d+\.\d+\.\d+)b(?P<ordinal>[1-9]\d*)$")


@dataclass(frozen=True, slots=True)
class BetaVersion:
    package_version: str
    release_tag: str
    base_version: str
    ordinal: int


def parse_beta_version(package_version: str) -> BetaVersion:
    match = _BETA.fullmatch(package_version)
    if not match:
        raise VersionError("package_version_not_beta")
    base = match.group("base")
    ordinal = int(match.group("ordinal"))
    return BetaVersion(
        package_version=package_version,
        release_tag=f"v{base}-beta.{ordinal}",
        base_version=base,
        ordinal=ordinal,
    )
