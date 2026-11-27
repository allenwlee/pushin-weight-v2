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
