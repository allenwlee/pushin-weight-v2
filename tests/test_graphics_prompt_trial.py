"""Local-only regression net. Fake provider replies; no credentials, DB or network."""

import base64
import json
import tempfile
import threading
import unittest
from io import BytesIO
from unittest.mock import patch

from jsonschema import Draft202012Validator

from scripts import graphics_prompt_trial as trial
from scripts import graphics_reference_fetch as references

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jTioAAAAASUVORK5CYII="
)


class Reply(BytesIO):
    status = 200

    def __init__(self, value):
        super().__init__(
            value if isinstance(value, bytes) else json.dumps(value).encode()
        )


class GraphicsTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        trial.configure(self.temp.name)
        trial.KEYS = {"OPENROUTER_API_KEY": "fake", "XAI_API_KEY_PW": "fake"}
        image = trial.P / "identity.png"
        image.write_bytes(PNG)
        self.identity = [
            {
                "asset_ref": "person:1",
                "role": "identity_reference",
                "credit": "Fixture source",
                "file": str(image),
                "sha256": trial.sha(image),
            }
        ]
        self.handoff = {
            "fact_items": [{"fact_id": "F01", "claim": "A display name changed."}]
        }
        trial.initialize(self.handoff, self.identity)
        self.c1 = {
            "schema_version": "copy-proposals/v3",
            "locale": "en",
            "candidates": [
                {
                    "id": label,
                    "headline": text,
                    "byline": "Supported development.",
                    "wordplay_meaning": "A name pun.",
                    "cultural_reference": None,
                    "used_fact_ids": ["F01"],
                }
                for label, text in [("A", "Ram I Am"), ("B", "Memory Lane")]
            ],
            "article": "Complete shared article.",
            "used_fact_ids": ["F01"],
            "evidence_gaps": [],
        }
        self.g0 = {
            "schema_version": "graphics-discovery/v3",
            "approaches": [
                {
                    "candidate_id": "A",
                    "approach": "cultural_reference",
                    "reason": "The model recognizes the book allusion despite the null C1 hint.",
                    "reference_target": "Green Eggs and Ham",
                },
                {
                    "candidate_id": "B",
                    "approach": "original_visual_concept",
                    "reason": "An ordinary expression supports an original metaphor.",
                    "reference_target": None,
                },
            ],
            "queries": ["fresh artwork query"],
            "preferred_sites": ["publisher.test"],
            "reuse_asset_refs": ["person:1"],
        }
        self.g1 = {
            "schema_version": "graphics-treatments/v2",
            "treatments": [
                {
                    "candidate_id": label,
                    "idea": "A visual idea.",
                    "why_it_bites": "Name pun.",
                    "input_asset_refs": [
                        {"asset_ref": "person:1", "role": "identity_reference"}
                    ],
                    "aspect_ratio": ratio,
                    "still_prompt": f"Draw the exact headline in a locked {ratio} frame.",
                    "motion_prompt": f"Hold the locked {ratio} frame and lettering.",
                }
                for label, ratio in [("A", "4:5"), ("B", "16:9")]
            ],
            "source_gaps": [],
        }

    def test_full_test_chain_renders_both_stills_but_publishes_primary(self):
        attempt = trial.read("attempt")
        attempt["render_reserve"] = True
        trial.save("attempt", attempt)
        captures = []
        image_barrier = threading.Barrier(2, timeout=3)
        phase = iter(["C1", "G0", "G1", "E1"])

        def provider(request, **kwargs):
            url = request if isinstance(request, str) else request.full_url
            if url == "https://video.test/result.mp4":
                return Reply(b"fake-video")
            if url.endswith("/videos/job-1"):
                return Reply(
                    {
                        "status": "done",
                        "video": {"url": "https://video.test/result.mp4"},
                        "usage": {"cost_in_usd_ticks": 1600000000},
                    }
                )
            body = json.loads(request.data)
            captures.append((url, body))
            if "/images/" in url:
                self.assertIn(body["aspect_ratio"], ["3:4", "16:9"])
                self.assertNotIn("4:5", body["prompt"])
                image_barrier.wait()  # Fails if the implementation serializes A/B.
                return Reply(
                    {
                        "data": [{"b64_json": base64.b64encode(PNG).decode()}],
                        "usage": {"cost_in_usd_ticks": 700000000},
                    }
                )
            if url.endswith("/videos/generations"):
                self.assertTrue((trial.P / "published-copy.json").exists())
                return Reply({"request_id": "job-1"})
            cid = next(phase)
            if cid == "E1":
                self.assertTrue((trial.P / "published-copy.json").exists())
                self.assertIn("not an author name", body["messages"][0]["content"])
                value = {
                    "schema_version": "eic-scorecard/v1",
                    "text_id": 1,
                    "content_revision": trial.read("publication-receipt")[
                        "content_revision"
                    ],
                    "summary": "Fixture review.",
                    "scores": {
                        key: 4
                        for key in [
                            "factual_support",
                            "attribution_uncertainty",
                            "headline_craft",
                            "clarity_context",
                            "image_claim_fit",
                            "likeness",
                            "lettering",
                        ]
                    },
                    "findings": [],
                    "reviewed_asset_refs": ["candidate:A"],
                    "not_reviewed": ["Motion"],
                    "suggested_admin_follow_up": [],
                }
            else:
                if cid == "G1":
                    task = body["messages"][1]["content"][0]["text"]
                    supplied = json.loads(
                        task.split("SUPPLIED INPUTS:\n", 1)[1].split(
                            "\n\nOUTPUT JSON SCHEMA", 1
                        )[0]
                    )
                    self.assertEqual(
                        supplied["visual_approaches"], self.g0["approaches"]
                    )
                    self.assertIn("original concept", body["messages"][0]["content"])
                value = {
                    "C1": self.c1,
                    "G0": self.g0,
                    "G1": self.g1,
                }[cid]
            return Reply(
                {
                    "model": trial.MODEL,
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": json.dumps(value)},
                        }
                    ],
                    "usage": {"cost": 0.01},
                }
            )

        def search(plan):
            self.assertEqual(plan["queries"], self.g0["queries"])
            g0_request = trial.read("request-G0")["messages"][1]["content"]
            self.assertIn('"prior_searches": []', g0_request)
            self.assertNotIn("source_artwork", g0_request)
            return {
                "provider": "fixture",
                "queries": [{"query": self.g0["queries"][0], "results": []}],
            }

        with patch.object(trial.urllib.request, "urlopen", side_effect=provider):
            trial.run_pipeline(search)
        self.assertEqual(len(captures), 7)
        self.assertEqual(trial.read("published-copy")["article"], self.c1["article"])
        self.assertIsNone(trial.read("publication-receipt")["selection_call"])
        self.assertEqual(
            trial.read("publication-receipt")["selected_candidate_id"], "A"
        )
        self.assertFalse((trial.P / "call-V-B.json").exists())
        self.assertEqual(trial.read("call-V1")["state"], "completed")
        self.assertEqual(
            trial.read("output-G1")["treatments"][0]["aspect_ratio"], "4:5"
        )
        self.assertEqual(trial.read("parameter-adjustments")[0]["submitted"], "3:4")
        self.assertFalse(list(trial.P.glob("stage-failure-*.json")))
        # Re-entry cannot silently replace a saved edition.
        before = trial.sha(trial.P / "published-copy.json")
        with (
            patch.object(trial, "llm", side_effect=AssertionError("No late call")),
            self.assertRaisesRegex(RuntimeError, "already saved"),
        ):
            trial.choose_and_save()
        self.assertEqual(before, trial.sha(trial.P / "published-copy.json"))

    def test_transport_timeout_is_not_resubmitted(self):
        with patch.object(
            trial.urllib.request, "urlopen", side_effect=TimeoutError
        ) as network:
            with self.assertRaises(TimeoutError):
                trial.post(
                    "I-A",
                    "https://api.x.ai/v1/images/edits",
                    "XAI_API_KEY_PW",
                    {"model": "grok-imagine-image-2.0"},
                    0.15,
                )
            with self.assertRaises(FileExistsError):
                trial.post(
                    "I-A",
                    "https://api.x.ai/v1/images/edits",
                    "XAI_API_KEY_PW",
                    {"model": "grok-imagine-image-2.0"},
                    0.15,
                )
        self.assertEqual(network.call_count, 1)
        self.assertEqual(trial.read("call-I-A")["state"], "ambiguous")

    def test_graphics_can_choose_original_ideas_without_search_or_new_copy(self):
        self.g0["queries"] = []
        self.g0["preferred_sites"] = []
        for approach in self.g0["approaches"]:
            approach.update(approach="original_visual_concept", reference_target=None)
        reply = {
            "model": trial.MODEL,
            "choices": [
                {"finish_reason": "stop", "message": {"content": json.dumps(self.g0)}}
            ],
            "usage": {"cost": 0.01},
        }
        with patch.object(
            trial.urllib.request, "urlopen", return_value=Reply(reply)
        ) as provider:
            result = trial.discover(self.c1)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(result["queries"], [])
        self.assertFalse((trial.P / "call-C1.json").exists())
        task = trial.read("messages-G0")["task"]
        self.assertIn('"claim": "A display name changed."', task)
        self.assertEqual(result["approaches"], self.g0["approaches"])

    def test_missing_discovery_does_not_prevent_graphics_determination(self):
        trial.save("output-C1", self.c1)
        trial.save("search-evidence", {"queries": [], "images_downloaded": 0})
        with patch.object(trial, "llm", return_value=self.g1) as model:
            trial.prepare()
        self.assertEqual(model.call_args.args[2]["visual_approaches"], [])
        self.assertIn("make the determination above", trial.CALLS["G1"]["system"])

    def test_one_or_no_still_preserves_preferred_headline_without_chooser(self):
        for count in [1, 0]:
            with self.subTest(stills=count):
                for name in ["published-copy", "publication-receipt"]:
                    (trial.P / (name + ".json")).unlink(missing_ok=True)
                trial.save("output-C1", self.c1)
                assets = (
                    [
                        {
                            "candidate_id": "B",
                            "asset_ref": "candidate:B",
                            "input_asset_refs": ["person:1"],
                        }
                    ]
                    if count
                    else []
                )
                trial.save("candidate-assets", assets)
                with patch.object(
                    trial, "llm", side_effect=AssertionError("C2 must not run")
                ):
                    trial.choose_and_save()
                self.assertEqual(
                    trial.read("published-copy")["article"], self.c1["article"]
                )
                self.assertIsNone(trial.read("publication-receipt")["selection_call"])
                self.assertEqual(
                    trial.read("published-copy")["used_asset_refs"],
                    [],
                )

    def media_setup(self):
        trial.save("output-C1", self.c1)
        trial.save("validated-output-G1", trial.normalize_treatments(self.g1))
        trial.save("candidate-assets", [])

    def fake_asset(self, label):
        return {
            **self.identity[0],
            "candidate_id": label,
            "asset_ref": "candidate:" + label,
            "role": "candidate_still",
            "input_asset_refs": ["person:1"],
        }

    def test_better_looking_reserve_never_changes_primary(self):
        self.media_setup()
        trial.save("candidate-assets", [self.fake_asset("A"), self.fake_asset("B")])
        with patch.object(
            trial, "llm", side_effect=AssertionError("No visual chooser")
        ):
            trial.choose_and_save()
        self.assertEqual(
            trial.read("published-copy")["headline"],
            self.c1["candidates"][0]["headline"],
        )
        with self.assertRaisesRegex(RuntimeError, "definite media failure"):
            trial.choose_and_save("B")

    def run_media_case(
        self,
        image_state="completed",
        video_state="completed",
        reserve_state="completed",
        render_reserve=False,
    ):
        self.media_setup()
        attempt = trial.read("attempt")
        attempt["render_reserve"] = render_reserve
        trial.save("attempt", attempt)
        images, videos = [], []

        def render(treatment, assets):
            label = treatment["candidate_id"]
            images.append(label)
            state = image_state if label == "A" else reserve_state
            trial.save("call-I-" + label, {"state": state})
            return self.fake_asset(label) if state == "completed" else None

        def video(stage="V1"):
            videos.append(stage)
            self.assertTrue((trial.P / "published-copy.json").exists())
            state = (
                video_state
                if stage == "V1" and image_state == "completed"
                else "completed"
            )
            trial.save("call-" + stage, {"state": state})

        with (
            patch.object(trial, "render_still", side_effect=render),
            patch.object(trial, "submit_video", side_effect=video),
            patch.object(trial, "video_until_complete"),
            patch.object(trial, "review"),
        ):
            trial.finish_creation()
        return images, videos

    def test_production_success_does_not_spend_on_reserve(self):
        images, videos = self.run_media_case()
        self.assertEqual(images, ["A"])
        self.assertEqual(videos, ["V1"])
        self.assertEqual(
            trial.read("publication-receipt")["selected_candidate_id"], "A"
        )

    def test_image_failure_uses_reserve_and_preserves_a_edition(self):
        images, videos = self.run_media_case(image_state="failed")
        self.assertEqual(images, ["A", "B"])
        self.assertEqual(videos, ["V1"])
        self.assertEqual(trial.read("fallback")["failure_stage"], "I-A")
        self.assertEqual(
            trial.read("edition-A-copy")["headline"],
            self.c1["candidates"][0]["headline"],
        )
        self.assertEqual(
            trial.read("published-copy")["headline"],
            self.c1["candidates"][1]["headline"],
        )

    def test_video_failure_uses_existing_test_reserve_once(self):
        images, videos = self.run_media_case(video_state="failed", render_reserve=True)
        self.assertCountEqual(images, ["A", "B"])
        self.assertEqual(videos, ["V1", "V-B"])
        self.assertEqual(trial.read("fallback")["failure_stage"], "V1")
        self.assertEqual(
            trial.read("publication-receipt")["selected_candidate_id"], "B"
        )
        self.assertEqual(trial.read("published-copy")["article"], self.c1["article"])

    def test_ambiguous_image_never_promotes_available_b(self):
        images, videos = self.run_media_case(
            image_state="ambiguous", render_reserve=True
        )
        self.assertCountEqual(images, ["A", "B"])
        self.assertEqual(videos, [])
        self.assertEqual(
            trial.read("publication-receipt")["selected_candidate_id"], "A"
        )
        self.assertEqual(trial.read("published-copy")["used_asset_refs"], [])

    def test_pending_video_does_not_trigger_backup(self):
        images, videos = self.run_media_case(video_state="pending")
        self.assertEqual(images, ["A"])
        self.assertEqual(videos, ["V1"])
        self.assertFalse((trial.P / "fallback.json").exists())

    def test_both_images_fail_preserves_primary_text_without_reroll(self):
        images, videos = self.run_media_case(
            image_state="failed", reserve_state="failed"
        )
        self.assertEqual(images, ["A", "B"])
        self.assertEqual(videos, [])
        self.assertEqual(
            trial.read("publication-receipt")["selected_candidate_id"], "A"
        )

    def test_pending_video_polls_accepted_id_only(self):
        trial.save("call-V1", {"state": "pending", "provider_request_id": "job-1"})
        results = iter(["pending", "pending", "completed"])

        def poll(stage="V1"):
            row = trial.read("call-V1")
            row["state"] = next(results)
            trial.save("call-V1", row)

        waits = []
        with (
            patch.object(trial, "poll_video_once", side_effect=poll) as poller,
            patch.object(
                trial, "post", side_effect=AssertionError("No new generation")
            ),
        ):
            trial.video_until_complete(sleep=waits.append)
        self.assertEqual(poller.call_count, 3)
        self.assertEqual(waits, [2, 2])

    def test_contracts_keep_one_display_string_and_supported_geometry(self):
        for call in trial.CALLS.values():
            if "response_schema" in call:
                Draft202012Validator.check_schema(call["response_schema"])
        c1 = trial.CALLS["C1"]["response_schema"]["properties"]["candidates"]["items"][
            "properties"
        ]
        self.assertNotIn("intended_capitalization", c1)
        self.assertNotIn(
            "fallback_notes", trial.CALLS["G0"]["response_schema"]["properties"]
        )
        self.assertNotIn("C2", trial.CALLS)
        for cid in ["C1"]:
            self.assertNotRegex(
                trial.CALLS[cid]["system"], r"(?i)copyright|fair.use|clearance|rights"
            )
        normalized = trial.normalize_treatments(self.g1)
        Draft202012Validator(trial.CALLS["G1"]["response_schema"]).validate(normalized)
        self.assertEqual(normalized["treatments"][0]["aspect_ratio"], "3:4")
        self.assertEqual(self.g1["treatments"][0]["aspect_ratio"], "4:5")

    def test_geometry_repair_preserves_headline_and_factual_ratios(self):
        self.g1["treatments"][0]["still_prompt"] = (
            'Headline exactly "4:5". The source comparison was 4:5. Use a locked 4:5 frame.'
        )
        result = trial.normalize_treatments(self.g1)
        self.assertEqual(
            result["treatments"][0]["still_prompt"],
            'Headline exactly "4:5". The source comparison was 4:5. Use a locked 3:4 frame.',
        )

    def test_parallel_requests_share_one_spending_reservation(self):
        from concurrent.futures import ThreadPoolExecutor

        barrier = threading.Barrier(2, timeout=3)

        def submit(stage):
            barrier.wait()
            try:
                trial.post(
                    stage,
                    "https://api.x.ai/v1/images/edits",
                    "XAI_API_KEY_PW",
                    {"model": "grok-imagine-image-2.0"},
                    1.1,
                )
                return "submitted"
            except RuntimeError:
                return "budget held"

        with (
            patch.object(
                trial.urllib.request,
                "urlopen",
                side_effect=lambda *args, **kwargs: Reply({"data": []}),
            ) as network,
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            outcomes = list(executor.map(submit, ["I-A", "I-B"]))
        self.assertCountEqual(outcomes, ["submitted", "budget held"])
        self.assertEqual(network.call_count, 1)

    def test_continue_cannot_overwrite_existing_run_evidence(self):
        trial.save("call-G1", {"state": "completed"})
        with (
            patch.object(
                trial, "fetch_sources", side_effect=AssertionError("No refetch")
            ),
            self.assertRaisesRegex(RuntimeError, "already advanced"),
        ):
            trial.continue_creation({})

    def test_redirected_index_is_not_mislabeled_as_playset(self):
        html = '<title>Activities | Dr Seuss</title><meta property="og:image" content="/collage.jpg">'
        image, title, reason = references.select_image(
            html,
            "https://publisher.test/activity/sam-i-am-playset/",
            "https://publisher.test/activities",
            "Sam-I-Am Playset",
        )
        self.assertIsNone(image)
        self.assertIn("generic index", reason)
        self.assertEqual(title, "Activities | Dr Seuss")

    def test_named_cover_beats_generic_social_preview(self):
        html = '<title>Green Eggs and Ham</title><meta property="og:image" content="/collage.jpg"><main><img alt="Green Eggs and Ham cover" src="/cover.jpg"></main>'
        image, _, basis = references.select_image(
            html,
            "https://publisher.test/book/123",
            "https://publisher.test/books/green-eggs-and-ham",
            "Green Eggs and Ham",
        )
        self.assertEqual(image, "https://publisher.test/cover.jpg")
        self.assertIn("named page image", basis)

    def test_footer_logo_url_is_not_a_book_cover(self):
        html = '<title>Brave New World</title><footer><img src="/brave/footer_logo.png"></footer>'
        image, _, _ = references.select_image(
            html, "https://publisher.test/brave", "https://publisher.test/brave", "Brave New World"
        )
        self.assertIsNone(image)

    def test_source_download_retains_actual_title_and_missing_results(self):
        discovery = {"queries": ["named cover", "missing source"]}
        results = {
            "provider": "fixture",
            "queries": [
                {
                    "query": "named cover",
                    "results": [
                        {
                            "url": "https://publisher.test/old",
                            "title": "Green Eggs and Ham wrong edition",
                        }
                    ],
                },
                {"query": "missing source", "results": []},
            ],
        }

        def fetch(url, limit, deadline):
            if url.endswith("/old"):
                return (
                    b'<title>Green Eggs and Ham</title><img alt="Green Eggs and Ham cover" src="/cover.png">',
                    "https://publisher.test/books/green-eggs-and-ham",
                    "text/html",
                )
            return PNG, url, "image/png"

        assets = references.fetch_sources(trial.P, discovery, results, fetch=fetch)
        self.assertEqual(assets[0]["title"], "Green Eggs and Ham")
        self.assertEqual(assets[0]["search_title"], "Green Eggs and Ham wrong edition")
        self.assertEqual(
            trial.read("search-evidence")["empty_queries"], ["missing source"]
        )
        self.assertEqual(assets[0]["credit_status"], "incomplete")
        with self.assertRaises(ValueError):
            references.fetch_sources(
                trial.P, {"queries": ["different run"]}, results, fetch=fetch
            )


if __name__ == "__main__":
    unittest.main()
