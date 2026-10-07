import pytest

from scripts.benchmark_download_collector.history import date_chunks, reconstruct_counts


def test_chunks_cover_all_history_without_overlap():
    chunks = list(date_chunks("2025-01-01", "2026-10-06", size=366))
    assert chunks == [("2025-01-01", "2026-01-01"), ("2026-01-02", "2026-10-06")]


def test_reconstruction_is_daily_utc_and_explicitly_not_observed_stock():
    result = reconstruct_counts(
        ["2026-09-10T23:00:00Z", "2026-09-11T02:00:00+03:00", "2026-09-12T00:00:00Z"],
        retrieved_at="2026-09-13T00:00:00Z",
    )
    assert result["counts"] == {"2026-09-10": 2, "2026-09-11": 2, "2026-09-12": 3}
    assert result["history_basis"] == "reconstructed_current_relationships"
    assert result["includes_removed_relationships"] is False
    with pytest.raises(ValueError):
        reconstruct_counts(["2026-09-10T23:00:00"], retrieved_at="2026-09-13T00:00:00Z")


def test_archive_range_selects_tracked_rows_and_validates_redirects():
    import io
    import re

    import httpx
    import pyarrow as pa
    import pyarrow.parquet as pq

    from scripts.benchmark_download_collector.hf_archive import (
        ArchiveBudget,
        select_snapshot,
    )

    out = io.BytesIO()
    pq.write_table(
        pa.Table.from_pylist(
            [
                {"_id": "1", "id": "lab/model", "downloads": 10, "likes": 2},
                {"_id": "2", "id": "other/model", "downloads": 30, "likes": 5},
            ]
        ),
        out,
    )
    binary = out.getvalue()

    def response(request):
        start, end = map(
            int, re.fullmatch(r"bytes=(\d+)-(\d+)", request.headers["range"]).groups()
        )
        return httpx.Response(
            206,
            content=binary[start : end + 1],
            headers={"content-range": f"bytes {start}-{end}/{len(binary)}"},
        )

    budget = ArchiveBudget(
        httpx.Client(transport=httpx.MockTransport(response)),
        requests=30,
        max_bytes=100000,
        seconds=10,
    )
    result = select_snapshot(
        budget,
        {"id": "a" * 40, "date": "2026-10-01T00:00:00Z"},
        [{"identifier": "lab/model", "_id": "1"}],
    )
    assert result["rows"] == [{"id": "lab/model", "downloads": 10, "likes": 2}]
    assert result["missing_identifiers"] == []
    assert all(len(r["sha256"]) == 64 for r in result["selected_ranges"])
    with pytest.raises(ValueError, match="untrusted"):
        budget.get("https://example.com/file", 0, 4)


def test_archive_rejects_full_file_when_range_ignored():
    import httpx

    from scripts.benchmark_download_collector.hf_archive import ArchiveBudget

    budget = ArchiveBudget(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, content=b"PAR1")
            )
        )
    )
    with pytest.raises(ValueError, match="range unavailable"):
        budget.get("https://huggingface.co/file", 0, 4)


def test_relationship_pagination_preserves_failure_and_discards_profiles():
    import httpx

    from core.hf_metadata_client import HFMetadataClient
    from scripts.benchmark_download_collector.history import hf_relationship_history

    calls = []

    def respond(request):
        calls.append(request)
        if "cursor" not in request.url.params:
            return httpx.Response(
                200,
                json=[
                    {
                        "_id": "one",
                        "name": "private-profile-not-retained",
                        "followedAt": "2026-10-01T00:00:00Z",
                    }
                ],
                headers={
                    "link": '<https://huggingface.co/api/organizations/lab/followers?cursor=next>; rel="next"'
                },
            )
        return httpx.Response(
            200, json=[{"_id": "two", "followedAt": "2026-10-02T00:00:00Z"}]
        )

    client = HFMetadataClient(
        httpx.Client(transport=httpx.MockTransport(respond)),
        max_requests=3,
        max_seconds=10,
    )
    result = hf_relationship_history(client, "lab", kind="organization")
    assert result["relationship_count"] == 2 and result["pages"] == 2
    assert "private-profile-not-retained" not in str(result)
    assert calls[1].url.params["cursor"] == "next"
    assert result["counts"]["2026-10-01"] == 1 and result["counts"]["2026-10-02"] == 2


@pytest.mark.parametrize(
    "link",
    [
        '<https://example.com/api/organizations/lab/followers?cursor=x>; rel="next"',
        '<https://huggingface.co/api/users/lab/followers?cursor=x>; rel="next"',
    ],
)
def test_relationship_history_rejects_foreign_continuation(link):
    import httpx

    from core.hf_metadata_client import HFMetadataClient
    from scripts.benchmark_download_collector.history import hf_relationship_history

    client = HFMetadataClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=[], headers={"link": link})
            )
        ),
        max_requests=2,
        max_seconds=10,
    )
    with pytest.raises(ValueError, match="foreign"):
        hf_relationship_history(client, "lab", kind="organization")
    assert client.requests == 1
