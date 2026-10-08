from datetime import UTC, datetime

import pytest

from monitor.packet_maker import PacketProfile, make_packet


def profile(**changes):
    return PacketProfile.create(
        "development-report",
        cutoff=datetime(2026, 10, 8, tzinfo=UTC),
        max_bytes=changes.pop("max_bytes", 4000),
        settings=changes,
    )


def test_packet_is_immutable_and_reuse_includes_all_enrichment_and_settings():
    source = {"posts": [{"id": "1", "text": "原文", "classification": "v3"}]}
    first = make_packet(profile(language="ja"), lambda: source)
    first.payload["posts"][0]["text"] = "changed"
    assert first.payload == source
    assert (
        make_packet(profile(language="ja"), lambda: source).reuse_key == first.reuse_key
    )
    source["posts"][0]["classification"] = "v4"
    assert (
        make_packet(profile(language="ja"), lambda: source).reuse_key != first.reuse_key
    )
    assert (
        make_packet(profile(language="en"), lambda: source).reuse_key != first.reuse_key
    )


def test_byte_cap_uses_utf8_and_never_slices_source_passages():
    source = {"posts": [{"text": "字" * 100}]}
    with pytest.raises(ValueError, match="packet byte limit"):
        make_packet(profile(max_bytes=200), lambda: source)
    prepared = make_packet(
        profile(max_bytes=200), lambda: source, transform=lambda packet: {"posts": []}
    )
    assert prepared.payload == {"posts": []}
    assert source["posts"][0]["text"] == "字" * 100


def test_hidden_revision_invalidates_reuse_even_if_projection_is_equal():
    rows = {"text": "same", "revision": 1}
    first = make_packet(profile(), lambda: rows, project=lambda p: {"text": p["text"]})
    rows["revision"] = 2
    second = make_packet(profile(), lambda: rows, project=lambda p: {"text": p["text"]})
    assert second.payload == first.payload and second.reuse_key != first.reuse_key


def test_profile_requires_an_explicit_timezone_cutoff():
    with pytest.raises(ValueError, match="timezone"):
        PacketProfile.create(
            "brand-window",
            cutoff=datetime(2026, 10, 8, tzinfo=None),  # noqa: DTZ001 - invalid input
            max_bytes=4000,
        )
