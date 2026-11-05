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


@pytest.mark.parametrize('trending_score', [None, 0.0, 1.75])
def test_archive_range_selects_tracked_rows_and_validates_redirects(trending_score):
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
                {"_id": "1", "id": "lab/model", "downloads": 10, "likes": 2,
                 **({'trendingScore': trending_score} if trending_score is not None else {})},
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
    expected = {"id": "lab/model", "downloads": 10, "likes": 2}
    if trending_score is not None:
        expected['trendingScore'] = trending_score
    assert result["rows"] == [expected]
    assert ('trendingScore' in result['columns']) == (trending_score is not None)
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


def test_native_archive_row_identity_skips_unrelated_row_groups():
    import io
    import re

    import httpx
    import pyarrow as pa
    import pyarrow.parquet as pq

    from scripts.benchmark_download_collector.hf_archive import (
        ArchiveBudget,
        select_snapshot,
    )

    output = io.BytesIO()
    pq.write_table(pa.Table.from_pylist([
        {'_id': '1' * 24, 'id': 'other/model', 'downloads': 999},
        {'_id': '2' * 24, 'id': 'selected/model', 'downloads': 0},
    ]), output, row_group_size=1)
    binary = output.getvalue()
    ranges = []
    def send(request):
        start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', request.headers['range']).groups())
        ranges.append((start, end - start + 1))
        return httpx.Response(206, content=binary[start:end + 1],
            headers={'content-range': f'bytes {start}-{end}/{len(binary)}'})
    reader = ArchiveBudget(httpx.Client(transport=httpx.MockTransport(send)), workers=1)
    result = select_snapshot(reader, {'id': 'a' * 40, 'date': '2026-08-20T01:00:00Z'},
        [{'identifier': 'selected/model', '_id': '2' * 24}])
    assert result['rows'] == [{'id': 'selected/model', 'downloads': 0}]
    group = pq.ParquetFile(io.BytesIO(binary)).metadata.row_group(0)
    for i in range(group.num_columns):
        column = group.column(i)
        if column.path_in_schema in result['columns']:
            offset = column.dictionary_page_offset if column.has_dictionary_page else column.data_page_offset
            assert (offset, column.total_compressed_size) not in ranges


def test_legacy_and_database_archive_selection_use_latest_actual_utc_publication():
    from scripts.benchmark_download_collector.hf_archive import select_model_revisions

    commits = [
        {'id': 'a' * 40, 'date': '2026-08-13T03:00:00Z', 'title': 'Update models.parquet'},
        {'id': 'b' * 40, 'date': '2026-08-14T01:00:00+02:00', 'title': 'Update models.parquet'},
        {'id': 'c' * 40, 'date': '2026-08-14T00:00:00Z', 'title': 'Update models.parquet'},
    ]
    all_days = select_model_revisions(commits)
    assert {day: row['id'] for day, row in all_days.items()} == {
        '2026-08-13': 'b' * 40, '2026-08-14': 'c' * 40}
    assert select_model_revisions(commits, start_date='2026-08-13', end_date='2026-08-14') == {
        '2026-08-13': all_days['2026-08-13']}
    with pytest.raises(ValueError):
        select_model_revisions(commits, start_date='0813')


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


def test_revision_planning_does_not_require_optional_parquet_decoder():
    import subprocess
    import sys
    from pathlib import Path

    from scripts.benchmark_download_collector import hf_archive
    program = """
import builtins
original = builtins.__import__
def without_arrow(name, *args, **kwargs):
    if name == 'pyarrow' or name.startswith('pyarrow.'):
        raise ModuleNotFoundError('optional decoder intentionally absent')
    return original(name, *args, **kwargs)
builtins.__import__ = without_arrow
from scripts.benchmark_download_collector.hf_archive import select_model_revisions
rows = select_model_revisions([{'id': 'a' * 40, 'date': '2026-08-13T01:00:00Z', 'title': 'Update models.parquet'}])
assert list(rows) == ['2026-08-13']
"""
    subprocess.run([sys.executable, '-c', program],
        cwd=Path(hf_archive.__file__).resolve().parents[2], check=True)
