from __future__ import annotations

import pytest

from scripts.ollija.versioning import VersionError, parse_beta_version


def test_package_beta_maps_to_human_release_tag() -> None:
    version = parse_beta_version("0.2.0b1")

    assert version.base_version == "0.2.0"
    assert version.ordinal == 1
    assert version.release_tag == "v0.2.0-beta.1"


@pytest.mark.parametrize("value", ["0.2.0", "v0.2.0b1", "0.2.0b0", "0.2.0-beta.1"])
def test_noncanonical_beta_versions_are_rejected(value: str) -> None:
    with pytest.raises(VersionError, match="not_beta"):
        parse_beta_version(value)
