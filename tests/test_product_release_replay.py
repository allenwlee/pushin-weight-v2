import unittest
from dataclasses import replace
from datetime import datetime

from core.product_release_intake import SavedLabel, SourceRecord, TextEvidence
from core.product_release_replay import (
    CollectionAppearance,
    FirstStorage,
    ReplayWindow,
    replay,
)


def at(value):
    return datetime.fromisoformat(value)


def post(key, text="Released Aster"):
    return SourceRecord("x", key, (TextEvidence(f"post/{key}/text", "raw", text),))


def appearance(key, time, receipt="request-1", **kwargs):
    return CollectionAppearance("x", key, receipt, at(time), **kwargs)


class ProductReleaseReplayTests(unittest.TestCase):
    def setUp(self):
        self.window = ReplayWindow.parse(
            "2026-10-21T10:00", "2026-10-21T17:00", timezone="Asia/Tokyo"
        )

    def test_explicit_timezone_and_half_open_boundaries(self):
        rows = [post(key) for key in ("before", "start", "end")]
        receipts = [
            appearance("before", "2026-10-21T00:59:59+00:00", "r0"),
            appearance("start", "2026-10-21T01:00:00+00:00", "r1"),
            appearance("end", "2026-10-21T08:00:00+00:00", "r2"),
        ]
        result = replay(rows, receipts, self.window)
        self.assertEqual(result.source_ids, (("x", "start"),))
        self.assertEqual(result.window.start.isoformat(), "2026-10-21T01:00:00+00:00")

    def test_requires_explicit_timezone_or_offset_and_ordered_window(self):
        for start, end in (
            ("2026-10-21T10:00", "2026-10-21T17:00"),
            ("2026-10-21T17:00Z", "2026-10-21T10:00Z"),
        ):
            with self.subTest(start=start), self.assertRaises(ValueError):
                ReplayWindow.parse(start, end)
        self.assertEqual(
            ReplayWindow.parse("2026-10-21T10:00+09:00", "2026-10-21T17:00+09:00"),
            self.window,
        )

    def test_dst_ambiguity_nonexistent_time_and_conflicting_zone_fail(self):
        for start, end in (
            ("2026-11-01T01:30", "2026-11-01T03:00"),
            ("2026-03-08T02:30", "2026-03-08T04:00"),
            ("2026-10-21T10:00+09:00", "2026-10-21T17:00+09:00"),
        ):
            with self.subTest(start=start), self.assertRaises(ValueError):
                ReplayWindow.parse(start, end, timezone="America/New_York")
        ReplayWindow.parse(
            "2026-11-01T01:30-04:00",
            "2026-11-01T03:00-05:00",
            timezone="America/New_York",
        )

    def test_refetched_old_post_is_selected_and_first_storage_is_not_needed(self):
        rows = [post("old")]
        receipts = [
            appearance("old", "2026-08-01T01:00Z", "original"),
            appearance("old", "2026-10-21T02:00Z", "refetch"),
        ]
        result = replay(rows, receipts, self.window)
        self.assertEqual(result.source_ids, (("x", "old"),))
        self.assertEqual(result.appearances[0].physical_request_id, "refetch")

    def test_cached_page_reprocessing_does_not_change_collection_clock(self):
        cached = appearance(
            "old", "2026-08-01T01:00Z", processed_at=at("2026-10-21T02:00Z")
        )
        self.assertEqual(replay([post("old")], [cached], self.window).source_ids, ())

    def test_same_physical_receipt_reprocessed_is_deduplicated(self):
        first = appearance("one", "2026-10-21T02:00Z")
        cached = replace(first, processed_at=at("2026-10-22T02:00Z"))
        result = replay([post("one")], [first, cached], self.window)
        self.assertEqual(len(result.appearances), 1)
        self.assertEqual(
            result.input_digest,
            replay([post("one")], [first], self.window).input_digest,
        )

    def test_first_storage_fallback_is_explicit_and_limited(self):
        fallback = FirstStorage(
            "x", "one", at("2026-10-21T02:00Z"), "posts/one/fetched_at"
        )
        self.assertEqual(replay([post("one")], [], self.window).source_ids, ())
        result = replay([post("one")], [], self.window, first_storage=(fallback,))
        self.assertEqual(result.coverage, "first_storage_only")
        self.assertIn("first_storage_does_not_cover_refetches", result.limitations)
        self.assertEqual(result.first_storage, (fallback,))

    def test_mixed_coverage_and_missing_source_are_reported(self):
        receipts = [
            appearance("present", "2026-10-21T02:00Z"),
            appearance("missing", "2026-10-21T02:00Z"),
        ]
        fallback = FirstStorage(
            "x", "legacy", at("2026-10-21T02:00Z"), "posts/legacy/fetched_at"
        )
        result = replay(
            [post("present"), post("legacy")],
            receipts,
            self.window,
            first_storage=(fallback,),
        )
        self.assertEqual(result.coverage, "mixed")
        self.assertEqual(result.missing_source_ids, (("x", "missing"),))
        self.assertEqual(len(result.candidates), 2)
        self.assertIn("source_content_missing", result.limitations)

    def test_exact_inputs_include_non_candidates_and_digest_changes_with_enrichment(
        self,
    ):
        row = post("one", "Aster")
        receipt = appearance("one", "2026-10-21T02:00Z")
        result = replay([row], [receipt], self.window)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.source_ids, (("x", "one"),))
        self.assertEqual(result.source_records, (row,))
        self.assertEqual(
            result,
            replay(result.source_records, result.appearances, result.window),
        )
        enriched = replace(
            row, labels=(SavedLabel("product_release", "classification/1"),)
        )
        updated = replay([enriched], [receipt], self.window)
        self.assertNotEqual(updated.input_digest, result.input_digest)
        self.assertEqual(len(updated.candidates), 1)

    def test_repeat_and_input_order_do_not_change_manifest(self):
        rows = [post("one"), post("two")]
        receipts = [appearance(key, "2026-10-21T02:00Z") for key in ("one", "two")]
        self.assertEqual(
            replay(rows, receipts, self.window),
            replay(rows[::-1], receipts[::-1], self.window),
        )

    def test_conflicting_source_or_receipt_is_not_silently_overwritten(self):
        receipt = appearance("one", "2026-10-21T02:00Z")
        with self.assertRaises(ValueError):
            replay([post("one"), post("one", "different")], [receipt], self.window)
        with self.assertRaises(ValueError):
            replay(
                [post("one")],
                [receipt, replace(receipt, collected_at=at("2026-10-21T03:00Z"))],
                self.window,
            )

    def test_different_posts_on_same_receipt_must_share_physical_clock(self):
        with self.assertRaises(ValueError):
            replay(
                [post("one"), post("two")],
                [
                    appearance("one", "2026-10-21T02:00Z"),
                    appearance("two", "2026-10-21T03:00Z"),
                ],
                self.window,
            )

    def test_naive_collection_time_is_rejected(self):
        with self.assertRaises(ValueError):
            appearance("one", "2026-10-21T02:00")


if __name__ == "__main__":
    unittest.main()
