"""Pure release intake tests: no Django, database, provider or inference setup."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from core.product_release_intake import (
    FraudDecision,
    SavedLabel,
    SourceRecord,
    TextEvidence,
    URLReference,
    detect,
)


def source(text="", **kwargs):
    return SourceRecord(
        "x", "post-1", (TextEvidence("posts/post-1/text", "raw", text),), **kwargs
    )


class ProductReleaseIntakeTests(unittest.TestCase):
    def test_unknown_product_and_publisher_need_no_catalogue(self):
        candidate = detect(source("I've released ObscureHarness v0.1 today."))
        self.assertEqual(candidate.disposition, "pending")
        self.assertEqual(candidate.references, ())
        self.assertTrue(candidate.signals)

    def test_ordinary_product_mentions_are_not_release_signals(self):
        self.assertIsNone(
            detect(
                source(
                    "I use Qwen and Gemma daily. https://huggingface.co/Qwen/Qwen3-4B"
                )
            )
        )

    def test_open_weights_and_multilingual_announcements(self):
        for text in (
            "Open-Weights: Music 3.0",
            "New agent available now",
            "新模型上线",
            "モデルを公開",
        ):
            with self.subTest(text=text):
                self.assertIsNotNone(detect(source(text)))

    def test_saved_classification_without_raw_keyword(self):
        row = source(
            "Aster 1.2", labels=(SavedLabel("releases_updates", "classification/7"),)
        )
        candidate = detect(row)
        self.assertEqual(candidate.signals[0].locator, "classification/7")
        self.assertEqual(candidate.signals[0].kind, "saved_label")
        self.assertIn("saved_evidence_only", candidate.cautions)

    def test_saved_commentary_keeps_its_own_locator_and_offsets(self):
        row = replace(
            source("Aster"),
            texts=(
                TextEvidence("post/text", "raw", "Aster"),
                TextEvidence(
                    "synthesis/43/text", "commentary", "The new harness was released."
                ),
            ),
        )
        candidate = detect(row)
        signal = candidate.signals[0]
        self.assertEqual(signal.locator, "synthesis/43/text")
        self.assertEqual(row.texts[1].text[signal.start : signal.end], signal.excerpt)
        self.assertIn("saved_evidence_only", candidate.cautions)

    def test_saved_release_extraction_is_reused_without_new_inference(self):
        row = replace(
            source(),
            texts=(
                TextEvidence("release-evidence/9", "release_extraction", "Aster v2"),
            ),
        )
        self.assertEqual(detect(row).signals[0].kind, "saved_extraction")

    def test_teacher_links_do_not_become_released_products_or_publishers(self):
        row = source(
            "Released Fusion, distilled from Qwen and Gemma. "
            "https://huggingface.co/Qwen/Qwen3-4B "
            "https://huggingface.co/google/gemma-test"
        )
        candidate = detect(row)
        self.assertEqual(
            {r.native_identifier for r in candidate.references},
            {"Qwen/Qwen3-4B", "google/gemma-test"},
        )
        self.assertEqual(candidate.disposition, "pending")
        self.assertEqual(candidate.source, row)
        self.assertFalse(hasattr(candidate, "publisher_id"))

    def test_source_candidate_is_not_an_event_group(self):
        first = source("Released Aster v1 and Aster v2")
        self.assertNotEqual(
            detect(first).key, detect(replace(first, source_id="post-2")).key
        )
        updated = replace(
            first,
            texts=first.texts + (TextEvidence("c/1", "commentary", "New release"),),
        )
        self.assertEqual(detect(first).key, detect(updated).key)
        self.assertEqual(detect(first), detect(first))

    def test_quoted_announcement_is_not_presented_as_authors_own_claim(self):
        row = replace(
            source("Interesting"),
            texts=(
                TextEvidence("post/text", "raw", "Interesting"),
                TextEvidence("quoted-post/2/text", "quote", "Released Aster"),
            ),
        )
        candidate = detect(row)
        self.assertIn("quoted_context", candidate.cautions)
        self.assertNotIn("saved_evidence_only", candidate.cautions)
        self.assertEqual(candidate.signals[0].locator, "quoted-post/2/text")

    def test_future_negation_questions_and_reshares_are_retained_as_unverified(self):
        for text in (
            "Rumor: Aster will launch tomorrow",
            "Aster has not been released",
            "Has Aster launched?",
        ):
            with self.subTest(text=text):
                candidate = detect(source(text, is_reshare=True))
                self.assertEqual(candidate.disposition, "pending")
                self.assertIn("reshare", candidate.cautions)
                self.assertTrue(
                    set(candidate.cautions)
                    & {"future_or_uncertain", "negated", "question"}
                )

    def test_scam_keyword_does_not_exclude_legitimate_discussion(self):
        self.assertEqual(
            detect(source("Released ScamShield, a scam detector")).disposition,
            "pending",
        )

    def test_only_explicit_evidenced_fraud_excludes(self):
        decision = FraudDecision(
            "scam", "review/18", "Impersonated publisher; original denial attached."
        )
        candidate = detect(source("Released Aster", fraud=decision))
        self.assertEqual(candidate.disposition, "excluded")
        self.assertEqual(candidate.source.fraud, decision)
        with self.assertRaises(ValueError):
            FraudDecision("scam", "", "Unsubstantiated")

    def test_expanded_entities_are_used_without_redirect_fetching(self):
        row = source(
            "Released Aster https://t.co/example",
            urls=(
                URLReference(
                    "https://github.com/small/aster/releases/tag/v1",
                    "post/entities/urls/0/expanded_url",
                ),
            ),
        )
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            candidate = detect(row)
        self.assertEqual(candidate.references[0].native_identifier, "small/aster")
        self.assertEqual(candidate.references[0].locator, row.urls[0].locator)

    def test_repository_reference_parser_rejects_lookalikes_and_non_repos(self):
        urls = (
            "https://huggingface.co.evil.test/Qwen/model",
            "https://github.com/login/oauth",
            "https://github.com/u/../x",
            "https://u:pw@github.com/u/model",
            "https://huggingface.co/docs/hub",
            "https://github.com/u/model%2fother",
        )
        row = source(
            "Released Aster",
            urls=tuple(URLReference(u, str(i)) for i, u in enumerate(urls)),
        )
        self.assertEqual(detect(row).references, ())

    def test_hf_spaces_datasets_and_github_git_urls_preserve_identity(self):
        row = source(
            "Released tools",
            urls=(
                URLReference("https://huggingface.co/spaces/small/tool", "u/1"),
                URLReference("https://huggingface.co/datasets/small/training", "u/2"),
                URLReference("https://github.com/small/Agent.git", "u/3"),
            ),
        )
        self.assertEqual(
            {(r.repository_type, r.native_identifier) for r in detect(row).references},
            {
                ("space", "small/tool"),
                ("dataset", "small/training"),
                ("repository", "small/Agent"),
            },
        )

    def test_input_evidence_requires_nonempty_identity_and_unique_locators(self):
        with self.assertRaises(ValueError):
            replace(source(), source_id="")
        with self.assertRaises(ValueError):
            replace(
                source(),
                texts=(
                    TextEvidence("x", "raw", "one"),
                    TextEvidence("x", "raw", "two"),
                ),
            )


if __name__ == "__main__":
    unittest.main()
