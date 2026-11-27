from types import SimpleNamespace

from core.classified_product_releases import targeted_release_findings
from core.official_company_accounts import build_evidence


def extract(text, model, *, handle="southbrief", profile=None, org=None, **fields):
    record = {"source_excerpt": text, "model_name": model, "categories": ["model-other"],
              "publisher_relation": "source_author", "organization_name": org,
              "novelty": "new_release", **fields}
    post = SimpleNamespace(pk="case", is_retweet=False, author_handle=handle)
    return targeted_release_findings(post=post, tweet={"text": text, "author_profile_evidence": profile},
                                    records=[record])[0]


def test_ace_saved_profile_stands_without_repeated_name_in_bio():
    account = SimpleNamespace(author_id="2027273500218830848", handle="ace_robotics",
                              display_name="ACE ROBOTICS", bio="Robotics research",
                              last_seen_at="2026-11-27T01:00:00Z", verified_type=None)
    evidence = build_evidence(account, [], include_release_display_name=True)
    profile = {k: evidence[k] for k in ("display_name", "sources", "handle", "domains")}
    finding = extract("Introducing ACE-ViDiHand2", "ACE-ViDiHand2", handle=account.handle,
                      org=account.display_name, profile=profile)
    assert finding["issuer_evidence"]["observed_name"] == "ACE ROBOTICS"
    assert {"id": "account:2027273500218830848:display_name", "text": "ACE ROBOTICS",
            "observed_at": account.last_seen_at} in finding["publisher_profile"]["sources"]


def test_reporter_is_distinct_from_explicit_publisher():
    text = "Amini (@AminiTech) released Soma-1X Lite this week."
    finding = extract(text, "Soma-1X Lite")
    assert finding["issuer_evidence"] == {"relation": "attributed_party", "observed_name": "Amini",
                                         "source_locator": "post", "source_excerpt": text,
                                         "observed_handle": "aminitech"}


def test_reported_launch_does_not_bind_other_product():
    text = "Amini (@AminiTech) released Soma-1X Lite. We released Newsbot."
    finding = extract(text, "Newsbot")
    assert finding["issuer_evidence"]["relation"] == "source_author"


def test_ordinary_mention_does_not_make_recipient_the_publisher():
    text = "We released Newsbot for @AminiTech."
    finding = extract(text, "Newsbot")
    assert finding["issuer_evidence"]["relation"] == "source_author"


def test_omitted_reporter_vote_recovers_only_literal_issuer_of_this_offering():
    excerpt = ("Amini (@AminiTech) released Soma-1X Lite this week, a small open model "
               "that turns scanned documents into structured text and tables.")
    for relation in (None, "unknown", "attributed_party"):
        finding = extract(excerpt, "Soma-1X Lite", publisher_relation=relation)
        assert finding["issuer_evidence"]["observed_handle"] == "aminitech"
        assert finding["issuer_evidence"]["observed_name"] == "Amini"


def test_official_launch_without_repeated_org_uses_cited_source_display_name():
    text = "Introducing ACE-ViDiHand2: more than tracking hands in first-person video, it reconstructs their true 3D positions and continuous motion."
    profile = {"handle":"ace_robotics", "display_name":"ACE ROBOTICS","domains":[],
               "sources":[{"id":"account:2027273500218830848:display_name","text":"ACE ROBOTICS"},
                          {"id":"account:bio","text":"Empowering every robot with a super-brain."}]}
    got = extract(text, "ACE-ViDiHand2", handle="ace_robotics", profile=profile)
    assert got["issuer_evidence"]["observed_name"] == "ACE ROBOTICS"
    assert got["publisher_profile"] == profile
    assert not extract(text.replace("Introducing","Covering"), "ACE-ViDiHand2", handle="ace_robotics", profile=profile).get("publisher_profile")


def test_saved_publisher_replay_binds_observed_profile_or_named_party_and_preserves_packets():
    from copy import deepcopy

    from core.classified_product_releases import replay_saved_publisher

    def replay(name, text, handle, display, native, issuer, expected):
        post = SimpleNamespace(pk="123", text=text, tweet_url=f"https://x.com/{handle}/status/123",
                               tweet_twitter_url=None, author_handle=handle, author_name=display, is_retweet=False,
                               native_author_id=native, author=SimpleNamespace(author_id=native), author_id=1,
                               author_description="Empowering every robot with a super-brain.")
        assertion = {"source_excerpt": text, "source_locator": post.tweet_url}
        saved = {"observed_name": name, "assertions": [assertion]}
        if issuer:
            saved["issuer_evidence"] = {**assertion, "relation": issuer, "observed_name": None}
        before = deepcopy(saved)
        projected = replay_saved_publisher(saved, post)
        assert projected["issuer_evidence"]["observed_name"] == expected
        assert saved == before
        assert projected["assertions"] == saved["assertions"]
        return post, saved

    replay("Soma-1X Lite", "Amini (@AminiTech) released Soma-1X Lite this week.", "southbrief",
           "Southbrief", "1868991360755539968", None, "Amini")
    post, saved = replay("ACE-ViDiHand2", "Introducing ACE-ViDiHand2: more than tracking hands in first-person video.",
                         "ace_robotics", "ACE ROBOTICS", "2027273500218830848", "source_author", "ACE ROBOTICS")
    post.author.author_id = "987"
    assert replay_saved_publisher(saved, post) is saved
    post.text = "A corrected, unrelated post"
    assert replay_saved_publisher(saved, post) is saved
