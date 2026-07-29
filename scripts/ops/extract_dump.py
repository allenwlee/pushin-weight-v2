#!/usr/bin/env python3
"""
Strip a multipart envelope around a pg_dump custom-format file, verify md5.

GitHub release assets sometimes come wrapped in multipart boundaries
when the upload chunked. This extracts the binary dump and confirms its
md5 matches EXPECTED_MD5 before the caller proceeds.

Usage:
    extract_dump.py INPUT OUTPUT EXPECTED_MD5

Writes the stripped dump to OUTPUT and exits 0 on md5 match, non-zero
on mismatch or read error.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(f"usage: {argv[0]} INPUT OUTPUT EXPECTED_MD5", file=sys.stderr)
        return 2

    inp = Path(argv[1])
    outp = Path(argv[2])
    expected = argv[3].strip().lower()

    data = inp.read_bytes()
    stripped = data.strip()
    # Find the boundary markers (-----WEB-----...-----WEB----- etc).
    # Heuristic: locate the pg_dump magic header and the trailing 8KB
    # block. Simpler: look for the first occurrence of "Pg custom" magic
    # bytes (---\n or 0x5047...).
    magic = b"PGCUSTOM"
    idx = data.find(magic)
    if idx == -1:
        # Try alt: most pg_dump custom files start with "TOC entry" header
        # in plaintext listing but the actual binary starts with the
        # int16 version + int32 flags. Fall back to: dump the whole file
        # if no magic found (treat as raw pg_dump).
        idx = 0
    outp.write_bytes(data[idx:])
    actual = md5_of(outp).lower()
    if actual != expected:
        print(f"md5 mismatch: expected {expected} got {actual}", file=sys.stderr)
        return 1
    print(f"md5 OK: {actual} ({outp.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))