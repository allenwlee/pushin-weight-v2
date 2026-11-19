"""Pure source-based language proposals for save-person-job.

A proposal is a heuristic, not verified language proficiency. The vocabulary is
loaded explicitly; importing this module performs no filesystem operations.
"""

import json
import re
import unicodedata
from pathlib import Path

HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]")
KANA = re.compile(
    r"[\u3041-\u3096\u309d-\u309e\u30a1-\u30fa\u30fc-\u30fe\u31f0-\u31ff\uff66-\uff9d]"
)
HANGUL = re.compile(r"[\u1100-\u11ff\u3131-\u318e\uac00-\ud7a3]")


def norm(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(c)
    )


def segments(value, syllables, excluded):
    """Reuse the audit's dynamic segmentation, now returning its exact syllables.

    Whole tokens only, at most four syllables. No arbitrary substring matching.
    This matches spelling; it does not establish a real personal name.
    """
    value = norm(value)
    if not re.fullmatch("[a-z]+", value) or value in excluded:
        return None
    found = {0: ()}
    for i in range(len(value)):
        if i not in found or len(found[i]) >= 4:
            continue
        for end in range(i + 1, min(len(value), i + 6) + 1):
            if value[i:end] in syllables:
                candidate = (*found[i], value[i:end])
                if end not in found or len(candidate) < len(found[end]):
                    found[end] = candidate
    return found.get(len(value))


def tokens(value, handle=False, excluded_words=()):
    value = value.lstrip("@")
    value = re.sub(r"^0x", "", value, flags=re.IGNORECASE)
    if handle:
        value = re.sub(r"\d+$", "", value)
    else:
        value = re.split(r"\s(?:@|\||｜)|[|｜]", value)[0]
    # Exclude a whole organization word before CamelCase can turn MiniMax into
    # Mini + Max. A company suffix is not a personal-name observation.
    value = " ".join(
        part
        for part in re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?", value)
        if norm(part) not in excluded_words
    )
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    return re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?", value)


def alternative_pair(value, lexicon):
    parts = [norm(t) for t in tokens(value)]
    if len(parts) != 2:
        return None
    first, last = parts
    if first in lexicon["japanese_given"] and last in lexicon["japanese_family"]:
        return "T06", " + ".join(parts)
    if first in lexicon["alternative_given"] and last in lexicon["alternative_family"]:
        return "T08", " + ".join(parts)
    return None


def _excerpt(value, start, end, padding=18):
    lo, hi = max(0, start - padding), min(len(value), end + padding)
    return value[lo:hi]


def _other_script(value):
    hits = []
    for m in re.finditer(r"[^\W\d_]+", value, re.UNICODE):
        word = m.group(0)
        for char in word:
            name = unicodedata.name(char, "")
            if not unicodedata.category(char).startswith("L"):
                continue
            if (
                any(
                    script in name
                    for script in ("LATIN", "HIRAGANA", "KATAKANA", "IDEOGRAPHIC")
                )
                or HAN.fullmatch(char)
                or KANA.fullmatch(char)
                or HANGUL.fullmatch(char)
            ):
                continue
            # An isolated decorative historical symbol is not a linguistic word.
            if len(word) == 1 and ("HIEROGLYPH" in name or "CUNEIFORM" in name):
                continue
            hits.append((m.start(), m.end(), word, name.split(" ")[0]))
            break
    return hits


# Source text aliases, not account identifiers or historical cohort membership.
CHINESE_ORGANIZATIONS = re.compile(
    r"(?i)(?<![a-z0-9])(?:alibaba|qwen|alipay|ant group|baidu|bytedance|tencent|huawei|deepseek|deepseek_ai|minimax|moonshot|kimi|zhipu|zhipuai|stepfun|sensetime|meituan|xiaomi|tiktok|tsinghua|peking university|fudan|zhejiang university|sjtu|pku|ustc)(?![a-z0-9])|阿里|腾讯|字节|百度|华为|清华|北大|复旦|浙大"
)


def assess_fresh(person, lexicon):
    """Assess one saved account without any previous per-person audit or roster."""
    handle = person["handle"]
    sources = [
        {
            "kind": "name",
            "text": name,
            "url": (person.get("name_source") or {}).get("source_reference")
            or f"https://x.com/{handle}",
        }
        for name in person.get("names", [])
    ]
    sources.append(
        {"kind": "handle", "text": "@" + handle, "url": f"https://x.com/{handle}"}
    )
    for source in person.get("sources", []):
        if source["kind"] in {"saved_bio", "own_post"}:
            post_id = (
                source.get("native_post_id")
                or source.get("post_id")
                or source.get("tweet_id")
            )
            url = source.get("url") or f"https://x.com/{handle}" + (
                f"/status/{post_id}" if source["kind"] == "own_post" and post_id else ""
            )
            sources.append({"kind": source["kind"], "text": source["text"], "url": url})
    evidence = []

    def add(rule, source, quote):
        assert quote in source["text"]
        item = {
            "rule": rule,
            "source_kind": source["kind"],
            "quote": quote,
            "source_url": source["url"],
        }
        if item not in evidence:
            evidence.append(item)

    surnames = {norm(x) for x in lexicon["SUR"]} | {norm(x) for x in lexicon["AMB"]}
    syllables = set(lexicon["SYLL"])
    excluded = (
        set(lexicon["alternative_given"])
        | set(lexicon["alternative_family"])
        | {"ai", "ml", "phd", "the", "now", "ex", "lab", "labs", "minimax"}
    )
    organizations = set(lexicon["organization_words"])
    for source in sources:
        value = source["text"]
        kind = source["kind"]
        if kind in {"name", "handle"}:
            pair = alternative_pair(value, lexicon)
            if pair:
                add(pair[0], source, value)
            for token in tokens(value, kind == "handle", organizations):
                t = norm(token.replace("-", ""))
                if t in surnames:
                    # Shared spelling is still a possible match; preserve its
                    # conflicting vocabulary match for review below.
                    add(
                        "shared_surname_form" if t in excluded else "surname_form",
                        source,
                        token,
                    )
                parsed = segments(t, syllables, excluded)
                if parsed and len(t) >= 4:
                    add("possible_pinyin", source, token)
            if kind == "handle":
                word = re.sub(r"\d+$", "", handle.casefold())
                repeated = re.fullmatch(r"([a-z]{2,5})(?:\1)+(?:[a-z]{0,3})", word)
                if repeated and repeated.group(1) in syllables:
                    add("possible_pinyin", source, value)
        m = HAN.search(value)
        if m:
            span = re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]+", value)
            add("han_text", source, span.group() if span else m.group())
        m = KANA.search(value) or HANGUL.search(value)
        if m:
            add("japanese_korean_text", source, m.group())
        for start, end, word, _ in _other_script(value):
            add("other_script", source, word)
        if "🇺🇦" in value:
            add("ukraine_flag", source, "🇺🇦")
        m = CHINESE_ORGANIZATIONS.search(value)
        if m:
            add("organization_mention", source, m.group())
    # Extract company roles separately from raw prose; a textual mention alone
    # remains a clue, not a confirmed employment relationship.
    roles = []
    for role in person.get("roles", []):
        match = CHINESE_ORGANIZATIONS.search(role.get("organization", ""))
        if match:
            roles.append(
                {
                    "organization": role["organization"],
                    "status": role.get("status"),
                    "source_keys": role.get("source_keys", []),
                }
            )
    rules = {e["rule"] for e in evidence}
    positive = bool(rules & {"han_text", "surname_form"})
    negative = bool(rules & {"T06", "T08", "other_script", "ukraine_flag"})
    ambiguous = bool(
        rules
        & {
            "japanese_korean_text",
            "possible_pinyin",
            "shared_surname_form",
            "organization_mention",
        }
    ) or bool(roles)
    # A name spelling/character is a proposal signal; conflict, loose syllable
    # matches and organization-only mentions need review. Existing values are
    # never cleared; 'outside' only means no signal recognized in these sources.
    if negative and positive:
        outcome = "review"
    elif negative:
        outcome = "do_not_assign"
    elif "japanese_korean_text" in rules:
        outcome = "review"
    elif positive:
        outcome = "assign"
    elif ambiguous:
        outcome = "review"
    else:
        outcome = "outside"
    return {
        "native_id": person.get("native_id"),
        "handle": handle,
        "outcome": outcome,
        "evidence": evidence,
        "chinese_organization_roles": roles,
    }


def load_lexicon():
    return json.loads((Path(__file__).parent / "job_history_lexicon.json").read_text())


def validate_review_exclusions(review, people):
    """Validate explicitly reviewed exclusions against the supplied source packet."""
    if (
        not isinstance(review, dict)
        or review.get("schema") != "record-job-history-language-review/v1"
    ):
        raise ValueError("Invalid language-review decision packet")
    entries = review.get("owner_exclusions")
    if not isinstance(entries, dict):
        raise TypeError("Language-review exclusions must be an object")
    by_id = {p.get("native_id"): p for p in people if p.get("native_id")}
    if len(by_id) != sum(bool(p.get("native_id")) for p in people):
        raise ValueError("Duplicate native identity in source packet")
    exclusions = {}
    for native_id, entry in entries.items():
        if not isinstance(native_id, str) or native_id not in by_id:
            raise ValueError("Review identity absent from source packet")
        if not isinstance(entry, dict) or set(entry) != {
            "handle",
            "evidence",
            "reason",
        }:
            raise ValueError("Invalid language-review exclusion")
        if not all(isinstance(entry[k], str) and entry[k].strip() for k in entry):
            raise ValueError("Language-review exclusion requires evidence and reason")
        person = by_id[native_id]
        sources = person.get("names", []) + [
            s.get("text", "") for s in person.get("sources", [])
        ]
        if not any(entry["evidence"] in source for source in sources):
            raise ValueError("Language-review evidence is absent from saved sources")
        exclusions[native_id] = entry["reason"]
    return exclusions


def validate_name_review(review, people):
    """Validate versioned owner decisions against exact supplied source evidence."""
    import hashlib
    from datetime import datetime

    required = {
        "schema",
        "source_digest",
        "rules_version",
        "reviewed_by",
        "reviewed_at",
        "decisions",
    }
    if not isinstance(review, dict) or set(review) != required:
        raise ValueError("Invalid name-review fields")
    if (
        review["schema"] != "record-job-history-name-review/v1"
        or review["rules_version"] != "save-person-job-fresh/v1"
    ):
        raise ValueError("Unsupported name-review version")
    reviewer, reviewed_at = review["reviewed_by"], review["reviewed_at"]
    if (
        not isinstance(reviewer, str)
        or not reviewer.strip()
        or not isinstance(reviewed_at, str)
    ):
        raise ValueError("Name-review reviewer and time are required")
    try:
        review_time = datetime.fromisoformat(reviewed_at)
    except ValueError as exc:
        raise ValueError("Invalid name-review review time") from exc
    if review_time.utcoffset() is None:
        raise ValueError("Name-review review time must include a timezone")
    if not isinstance(people, list) or any(
        not isinstance(person, dict) for person in people
    ):
        raise TypeError("Name-review people must be an array of objects")
    source_digest = hashlib.sha256(
        json.dumps(people, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    if review["source_digest"] != source_digest:
        raise ValueError("Stale name-review source digest")
    if not isinstance(review["decisions"], list):
        raise TypeError("Name-review decisions must be an array")
    identities = {
        person.get("native_id"): person for person in people if person.get("native_id")
    }
    if len(identities) != sum(bool(person.get("native_id")) for person in people):
        raise ValueError("Duplicate source identity")
    result = {}
    expected = {
        "native_id",
        "source_key",
        "quote",
        "evidence_sha256",
        "observed_at",
        "decision",
        "reason",
        "supersedes",
    }
    for decision in review["decisions"]:
        if not isinstance(decision, dict) or set(decision) != expected:
            raise ValueError("Invalid name-review decision fields")
        native_id = decision["native_id"]
        if (
            not isinstance(native_id, str)
            or native_id not in identities
            or native_id in result
        ):
            raise ValueError("Unknown or duplicate name-review identity")
        if (
            decision["decision"] != "exclude"
            or not isinstance(decision["reason"], str)
            or not decision["reason"].strip()
        ):
            raise ValueError("Invalid name-review decision")
        if decision["supersedes"] is not None and (
            not isinstance(decision["supersedes"], str)
            or not decision["supersedes"].strip()
        ):
            raise ValueError("Invalid name-review supersession")
        key = decision["source_key"]
        if not isinstance(key, str):
            raise TypeError("Invalid name-review source key")
        person = identities[native_id]
        if re.fullmatch(r"saved-name:\d+", key):
            index = int(key.split(":", 1)[1])
            if index >= len(person.get("names", [])):
                raise ValueError("Unknown name-review source key")
            source_text = person["names"][index]
            observed = [(person.get("name_source") or {}).get("observed_at")]
        else:
            sources = [
                source
                for source in person.get("sources", [])
                if source.get("key") == key
            ]
            if len(sources) != 1:
                raise ValueError("Unknown or duplicate name-review source key")
            source = sources[0]
            source_text = source.get("text")
            observed = [
                entry.get("observed") for entry in source.get("observations", [])
            ] or [source.get("observed_at")]
        quote, expected_hash, at = (
            decision["quote"],
            decision["evidence_sha256"],
            decision["observed_at"],
        )
        if (
            not isinstance(source_text, str)
            or not isinstance(quote, str)
            or not quote
            or quote not in source_text
        ):
            raise ValueError("Name-review quote is absent from source evidence")
        if (
            not isinstance(expected_hash, str)
            or hashlib.sha256(source_text.encode()).hexdigest() != expected_hash
        ):
            raise ValueError("Stale name-review evidence hash")
        if not isinstance(at, str) or at not in observed:
            raise ValueError("Name-review observation time is missing or stale")
        try:
            parsed = datetime.fromisoformat(at)
        except ValueError as exc:
            raise ValueError("Invalid name-review observation time") from exc
        if parsed.utcoffset() is None:
            raise ValueError("Name-review observation time must include a timezone")
        result[native_id] = decision["reason"]
    return result


def adapt_legacy_name_review(review, people):
    """Bind legacy explicit exclusions to versioned, source-hashed decisions."""
    import hashlib

    exclusions = validate_review_exclusions(review, people)
    identities = {
        person.get("native_id"): person for person in people if person.get("native_id")
    }
    decisions = []
    for native_id, reason in exclusions.items():
        person = identities[native_id]
        quote = review["owner_exclusions"][native_id]["evidence"]
        matches = []
        for index, name in enumerate(person.get("names", [])):
            if quote in name:
                matches.append(
                    (
                        f"saved-name:{index}",
                        name,
                        (person.get("name_source") or {}).get("observed_at"),
                    )
                )
        for source in person.get("sources", []):
            if quote in source.get("text", ""):
                times = [
                    entry.get("observed") for entry in source.get("observations", [])
                ] or [source.get("observed_at")]
                matches.extend((source["key"], source["text"], at) for at in times)
        match = next((value for value in matches if value[2]), None)
        if match is None:
            raise ValueError("Reviewed exclusion lacks a dated source")
        key, source_text, observed_at = match
        decisions.append(
            {
                "native_id": native_id,
                "source_key": key,
                "quote": quote,
                "evidence_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
                "observed_at": observed_at,
                "decision": "exclude",
                "reason": reason,
                "supersedes": review.get("supersedes_decision"),
            }
        )
    source_digest = hashlib.sha256(
        json.dumps(people, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    result = {
        "schema": "record-job-history-name-review/v1",
        "source_digest": source_digest,
        "rules_version": "save-person-job-fresh/v1",
        "reviewed_by": review.get("authorized_by"),
        "reviewed_at": review.get("created_at_jst"),
        "decisions": decisions,
    }
    validate_name_review(result, people)
    return result
