"""Read only selected numeric columns from immutable public HF archive revisions."""

from __future__ import annotations

import hashlib
import io
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx
import pyarrow.parquet as pq

from .identity import require


class ArchiveBudget:
    """One physical request/byte/deadline budget shared by range-read workers."""

    def __init__(
        self, client, *, requests=150000, max_bytes=32 * 1024**3, seconds=7200
    ):
        self.client = client
        self.requests = self.bytes = 0
        self.max_requests, self.max_bytes = requests, max_bytes
        self.deadline = time.monotonic() + seconds
        self.lock = threading.Lock()
        self.not_before = 0.0

    def get(self, url, start, length):
        require(0 <= start and 0 < length <= 128 * 1024**2, "invalid range")
        for _ in range(8):
            host = urlsplit(url)
            require(
                host.scheme == "https"
                and not host.username
                and host.port in (None, 443)
                and (
                    host.hostname == "huggingface.co"
                    or (host.hostname or "").endswith(".hf.co")
                ),
                "untrusted archive redirect",
            )
            with self.lock:
                require(
                    self.requests < self.max_requests
                    and self.bytes < self.max_bytes
                    and time.monotonic() < self.deadline,
                    "archive budget exhausted",
                )
                self.requests += 1
                wait = max(0, self.not_before - time.monotonic())
            while wait > 0:
                require(time.monotonic() + wait < self.deadline, "archive deadline")
                time.sleep(min(30, wait))
                wait = max(0, self.not_before - time.monotonic())
            req = httpx.Request(
                "GET",
                url,
                headers={"Range": f"bytes={start}-{start + length - 1}"},
                extensions={
                    "timeout": httpx.Timeout(
                        min(40, max(0.01, self.deadline - time.monotonic()))
                    ).as_dict()
                },
            )
            with closing(
                self.client.send(req, stream=True, auth=None, follow_redirects=False)
            ) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code == 429:
                    reset = re.findall(
                        r"(?:^|;)\s*t=(\d+)", response.headers.get("ratelimit", "")
                    )
                    delay = max(
                        [
                            int(response.headers.get("retry-after", "0"))
                            if response.headers.get("retry-after", "0").isdigit()
                            else 0,
                            60,
                        ]
                        + [int(x) + 1 for x in reset]
                    )
                    with self.lock:
                        self.not_before = max(self.not_before, time.monotonic() + delay)
                    continue
                require(
                    response.status_code == 206,
                    "archive range unavailable: " + str(response.status_code),
                )
                match = re.fullmatch(
                    r"bytes (\d+)-(\d+)/(\d+)",
                    response.headers.get("content-range", ""),
                )
                require(
                    match is not None
                    and int(match[1]) == start
                    and int(match[2]) == start + length - 1,
                    "archive content range mismatch",
                )
                body = bytearray()
                for block in response.iter_bytes():
                    with self.lock:
                        self.bytes += len(block)
                        require(
                            self.bytes <= self.max_bytes
                            and time.monotonic() < self.deadline,
                            "archive budget exhausted",
                        )
                    require(len(body) + len(block) <= length, "oversized archive range")
                    body.extend(block)
                require(len(body) == length, "truncated archive range")
                return bytes(body), int(match[3]), url
        raise ValueError("archive redirect/retry cap")


class RangeFile(io.RawIOBase):
    def __init__(self, budget, url):
        self.budget, self.url = budget, url
        first, self.size, self.url = budget.get(url, 0, 4)
        require(first == b"PAR1", "not parquet")
        self.pos = 0
        self.cache = {0: first}
        self.range_hashes = []

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        pos = (
            offset
            if whence == 0
            else self.pos + offset
            if whence == 1
            else self.size + offset
        )
        require(0 <= pos <= self.size, "invalid parquet seek")
        self.pos = pos
        return pos

    def fetch(self, span):
        start, n = span
        data, size, _ = self.budget.get(self.url, start, n)
        require(size == self.size, "archive size changed")
        return start, data

    def prefetch(self, ranges):
        with ThreadPoolExecutor(max_workers=4) as pool:
            for start, data in pool.map(self.fetch, ranges):
                self.cache[start] = data
                self.range_hashes.append(
                    {
                        "offset": start,
                        "length": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )

    def read(self, n=-1):
        n = min(n if n >= 0 else self.size - self.pos, self.size - self.pos)
        if not n:
            return b""
        for start, data in self.cache.items():
            if start <= self.pos and self.pos + n <= start + len(data):
                result = data[self.pos - start : self.pos - start + n]
                self.pos += n
                return result
        self.prefetch([(self.pos, n)])
        return self.read(n)


def select_snapshot(budget, revision, cohort):
    """Missing source rows stay missing; no current counters fill past dates."""
    require(
        re.fullmatch("[0-9a-f]{40}", revision["id"]) is not None,
        "invalid archive revision",
    )
    url = f"https://huggingface.co/datasets/cfahlgren1/hub-stats/resolve/{revision['id']}/models.parquet"
    file = RangeFile(budget, url)
    parquet = pq.ParquetFile(file)
    require(parquet.metadata.num_rows <= 10000000, "archive row cap")
    columns = [
        c
        for c in ["id", "downloads", "downloadsAllTime", "likes"]
        if c in parquet.schema_arrow.names
    ]
    require("id" in columns and "downloads" in columns, "archive schema changed")
    ids = {r["identifier"].casefold() for r in cohort}
    keys = [r.get("_id") for r in cohort]
    groups = []
    ranges = []
    for i in range(parquet.num_row_groups):
        group = parquet.metadata.row_group(i)
        identifier_column = next(
            (
                group.column(j)
                for j in range(group.num_columns)
                if group.column(j).path_in_schema == "_id"
            ),
            None,
        )
        stats = identifier_column.statistics if identifier_column else None
        if (
            all(keys)
            and stats
            and stats.has_min_max
            and not any(stats.min <= k <= stats.max for k in keys)
        ):
            continue
        groups.append(i)
        for j in range(group.num_columns):
            column = group.column(j)
            if column.path_in_schema in columns:
                ranges.append(
                    (
                        column.dictionary_page_offset
                        if column.has_dictionary_page
                        else column.data_page_offset,
                        column.total_compressed_size,
                    )
                )
    require(sum(n for _, n in ranges) < 128 * 1024**2, "snapshot byte cap")
    file.prefetch(ranges)
    selected = {}
    duplicates = 0
    for i in groups:
        for row in parquet.read_row_group(
            i, columns=columns, use_threads=False
        ).to_pylist():
            key = row["id"].casefold()
            if key not in ids:
                continue
            row = {k: v for k, v in row.items() if v is not None}
            require(
                key not in selected or selected[key] == row,
                "conflicting archive duplicate",
            )
            duplicates += int(key in selected)
            selected[key] = row
    return {
        "revision": revision["id"],
        "archive_published_at": revision["date"],
        "retrieved_at": datetime.now(UTC).isoformat(),
        "rows": list(selected.values()),
        "missing_identifiers": sorted(ids - set(selected)),
        "identical_duplicates_collapsed": duplicates,
        "source_url": url,
        "file_path": "models.parquet",
        "upstream_file_size": file.size,
        "selected_ranges": file.range_hashes,
        "columns": columns,
    }
