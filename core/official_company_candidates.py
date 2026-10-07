"""Cheap stored-evidence entrances; selection never proves official ownership."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

CANDIDATE_POLICY = "official-company-candidates-v1"
MANUAL_POLICY = "explicit-operator-candidate-v1"
AI = re.compile(
    r"\b(ai|llms?|models?|intelligence|inference|weights|diffusion|robotics|"
    r"embedding|generative|neural)\b|人工智能|大模型|语言模型|語言模型|生成AI|機械学習",
    re.IGNORECASE,
)
DEVELOPMENT = re.compile(
    r"\b(we|our|building|build|develop|creating|create|making|make)\b|我们|我們|当社",
    re.IGNORECASE,
)
ORGANIZATION = re.compile(
    r"\b(labs?|research|technologies|technology|inc|company|corporation|institute|"
    r"systems|official|team)\b|(?:^|[_\W])ai(?:$|[_\W])|人工智能|研究院|研究所",
    re.IGNORECASE,
)
RELEASE = re.compile(
    r"\b(introducing|announce[ds]?|launch(ed|ing)?|releas(e|ed|ing)|available|"
    r"open[- ]?sourc(e|ed)|weights|model card|download|now live)\b|发布|開源|开源|リリース",
    re.IGNORECASE,
)
MODEL = re.compile(
    r"\b(models?|llms?|weights|inference|diffusion|tokens?|parameters?|training|"
    r"speech|vision|robotics|embedding)\b|模型|モデル",
    re.IGNORECASE,
)
SOCIAL_DOMAINS = frozenset(
    {
        "x.com",
        "twitter.com",
        "t.co",
        "youtube.com",
        "youtu.be",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "linktr.ee",
        "beacons.ai",
        "github.com",
        "huggingface.co",
        "medium.com",
        "substack.com",
        "patreon.com",
        "bsky.app",
        "discord.gg",
        "t.me",
        "telegram.me",
        "about.me",
        "threads.net",
        "cal.com",
        "calendly.com",
        "notion.site",
        "notion.so",
        "stan.store",
        "ko-fi.com",
    }
)


def mapping(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def normalized_name(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


@dataclass
class CandidateSignals:
    account: object
    profile_ai: bool = False
    development: bool = False
    release: bool = False
    domains: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.add_bio(
            " ".join(
                getattr(self.account, name, None) or ""
                for name in (
                    "bio",
                    "description",
                    "profile_bio_text",
                    "bio_en",
                    "bio_zh_cn",
                )
            )
        )

    def add_bio(self, text):
        if isinstance(text, str):
            self.profile_ai |= bool(AI.search(text))
            self.development |= bool(DEVELOPMENT.search(text))

    def add_profile(self, value):
        profile = mapping(value)
        self.add_bio(
            profile.get("description")
            or profile.get("profile_bio_text")
            or profile.get("bio")
        )
        entity = mapping(mapping(profile.get("entities")).get("url"))
        urls = entity.get("urls", [])
        for item in urls if isinstance(urls, list) else []:
            url = mapping(item).get("expanded_url")
            if not isinstance(url, str):
                continue
            try:
                parsed = urlsplit(url)
                host = (parsed.hostname or "").lower().removeprefix("www.")
            except ValueError:
                continue
            if (
                parsed.scheme in {"http", "https"}
                and host
                and not any(
                    host == domain or host.endswith("." + domain)
                    for domain in SOCIAL_DOMAINS
                )
            ):
                self.domains.add(host)
        # Some historical snapshot envelopes contain the nested author bio.
        if isinstance(profile.get("profile_bio"), dict):
            nested = profile["profile_bio"]
            self.add_bio(nested.get("description"))
            self.add_profile({k: v for k, v in nested.items() if k != "profile_bio"})

    def add_post(self, row):
        self.add_profile(row.get("author_profile_bio"))
        self.add_bio(row.get("author_description"))
        text = row.get("text") or ""
        if not self.release:
            self.release = bool(RELEASE.search(text) and MODEL.search(text))

    def priority(self):
        if (
            getattr(self.account, "verified_type", None) or ""
        ).casefold() == "business":
            return 1
        website_ai = bool(self.domains) and self.profile_ai
        if website_ai and self.development:
            return 2
        names = [
            getattr(self.account, "handle", None),
            getattr(self.account, "display_name", None),
        ]
        organization = bool(ORGANIZATION.search(" ".join(n or "" for n in names)))
        normalized = {normalized_name(n) for n in names if len(normalized_name(n)) >= 4}
        domain_match = any(
            len(stem := normalized_name(domain.split(".")[0])) >= 4
            and any(name in stem or stem in name for name in normalized)
            for domain in self.domains
        )
        if (website_ai and (organization or domain_match)) or (
            self.release and organization
        ):
            return 3
        return None


def candidate_priorities(accounts):
    """Bulk reads all available history once per bounded account batch; no calls."""
    from core.models import AccountProfileSnapshot, Post

    signals = {account.pk: CandidateSignals(account) for account in accounts}
    # Gold is independently admitted; do not read its post history to qualify it.
    inspect_ids = [pk for pk, signal in signals.items() if signal.priority() != 1]
    for row in (
        Post.objects.filter(author_id__in=inspect_ids)
        .values("author_id", "text", "author_profile_bio", "author_description")
        .order_by()
        .iterator(chunk_size=500)
    ):
        signals[row["author_id"]].add_post(row)
    for row in (
        AccountProfileSnapshot.objects.filter(account_id__in=inspect_ids)
        .values(
            "account_id",
            "description",
            "profile_bio_text",
            "raw_profile_payload",
            "profile_data",
        )
        .order_by()
        .iterator(chunk_size=500)
    ):
        signal = signals[row["account_id"]]
        signal.add_bio(row["description"] or row["profile_bio_text"])
        signal.add_profile(row["raw_profile_payload"] or row["profile_data"])
    return {pk: signal.priority() for pk, signal in signals.items()}
