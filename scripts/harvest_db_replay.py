"""Offline Boolean replay of saved harvest queries against a frozen DB snapshot.

This module uses only the Python standard library. It has no provider client,
credentials, network requests, Django connection or write path to the database.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

EAST_ASIAN = r"\u2460-\u24ff\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u1100-\u11ff\u3130-\u318f\uac00-\ud7af\U00020000-\U0002fa1f"


def normalize(value):
    # Preserve the boundary after a circled list number before NFKC turns it
    # into an ordinary digit (④Muse must not become the word 4Muse).
    value = re.sub(r"([\u2460-\u2473\u24ea\u24f5-\u24fe])", r"\1 ", value)
    return re.sub(r"(?<=\w)-(?=\w)", " ", unicodedata.normalize("NFKC", value).casefold())


def parse(query):
    """Parse parentheses, OR and implicit AND; reject unsupported operators."""
    tokens = re.findall(r'"[^"]*"|\(|\)|[^\s()]+', query)
    position = 0

    def either():
        nonlocal position
        children = [both()]
        while position < len(tokens) and tokens[position] == "OR":
            position += 1
            children.append(both())
        return ("or", children)

    def both():
        nonlocal position
        children = []
        while position < len(tokens) and tokens[position] not in ("OR", ")"):
            token = tokens[position]
            position += 1
            if token == "(":
                node = either()
                if position >= len(tokens) or tokens[position] != ")":
                    raise ValueError("unbalanced query")
                position += 1
                children.append(node)
            else:
                if ":" in token and not token.startswith(("-from:", "from:", "min_faves:")):
                    raise ValueError(f"cannot replay operator: {token}")
                children.append(("term", token))
        if not children:
            raise ValueError("empty query branch")
        return ("and", children)

    result = either()
    if position != len(tokens):
        raise ValueError("unconsumed query tokens")
    return result


def literal_pattern(term):
    # Match Latin words without matching embedded words. CJK/Korean/Japanese
    # text may adjoin an English model name, consistent with the app matcher.
    text = normalize(term)
    escaped = r"\s+".join(re.escape(word) for word in text.split())
    if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text):
        return re.compile(escaped)
    return re.compile(rf"(?<![^\W{EAST_ASIAN}]){escaped}(?![^\W{EAST_ASIAN}])")


class Matcher:
    def __init__(self, queries):
        self.trees = {q["call_id"]: parse(q["query"]) for q in queries}
        self.patterns = {}

    def calls(self, text, author):
        text, author = normalize(text), normalize(author or "").lstrip("@")
        cache = {}

        def term(token):
            if token in cache:
                return cache[token]
            if token.startswith("-from:"):
                found = author != normalize(token[6:]).lstrip("@")
            elif token.startswith("from:"):
                found = author == normalize(token[5:]).lstrip("@")
            elif token.startswith("min_faves:"):
                if token != "min_faves:0":
                    raise ValueError("positive engagement floor needs a metrics snapshot")
                found = True
            else:
                # An unquoted hyphen separates AND words. Quoted phrases retain
                # adjacency/order after the same punctuation normalization.
                quoted = token.startswith('"') and token.endswith('"')
                words = [token[1:-1]] if quoted else normalize(token).split()
                found = True
                for word in words:
                    if word not in self.patterns:
                        self.patterns[word] = literal_pattern(word)
                    if not self.patterns[word].search(text):
                        found = False
                        break
            cache[token] = found
            return found

        def evaluate(node):
            kind, value = node
            if kind == "term":
                return term(value)
            return (all if kind == "and" else any)(evaluate(child) for child in value)

        return [call for call, tree in self.trees.items() if evaluate(tree)]


def searchable_content(post):
    """Stored content only; observed URL paths and mentions, never fetched pages."""
    parts = [post.get("text") or "", post.get("quoted_text") or ""]
    entities = post.get("entities") or {}
    if isinstance(entities, str):
        entities = json.loads(entities)
    for mention in entities.get("user_mentions", []):
        handle = mention.get("screen_name") or mention.get("username")
        if handle:
            parts.append("@" + handle.lstrip("@"))
    for entry in entities.get("urls", []):
        address = entry.get("unwound_url") or entry.get("expanded_url")
        if not address:
            continue
        try:
            parsed = urlsplit(address)
            if parsed.scheme in ("http", "https"):
                parts.append(unquote((parsed.hostname or "") + parsed.path))
        except ValueError:
            continue
    return "\n".join(parts)


def replay(snapshot, manifest):
    queries = [q for q in manifest["queries"] if q["call_id"] != "A"]
    matcher = Matcher(queries)
    tracked = {name.split("/", 1)[0] for q in queries for name in q["components"]}
    names = {b["nickname"]: b.get("display_name_en") or b["display_name"] for b in snapshot["brands"]}
    lower = datetime.fromisoformat(snapshot["window_start_utc"])
    upper = datetime.fromisoformat(snapshot["window_end_utc"])
    if (upper - lower).total_seconds() != 43200:
        raise ValueError("exact twelve-hour cohort required")
    rows, seen = [], set()
    for post in snapshot["posts"]:
        tid = str(post["tweet_id"])
        if tid in seen:
            raise ValueError(f"duplicate snapshot ID: {tid}")
        seen.add(tid)
        created = datetime.fromisoformat(post["created_at"])
        if not lower <= created < upper:
            raise ValueError(f"post outside frozen interval: {tid}")
        author = post.get("author_handle") or ""
        body = matcher.calls(post.get("text") or "", author)
        full = matcher.calls(searchable_content(post), author)
        rows.append({"tweet_id": tid, "brand_ids": sorted(set(post["brand_ids"])),
            "body_call_ids": body, "matched_call_ids": full,
            "caught": bool(full), "relies_on_quote_or_entities": bool(full) and not body,
            "author_handle": author, "created_at": post["created_at"]})
    brand_rows = []
    for brand in sorted(tracked | {b for p in rows for b in p["brand_ids"]}):
        owned = [p for p in rows if brand in p["brand_ids"]]
        caught = sum(p["caught"] for p in owned)
        body = sum(bool(p["body_call_ids"]) for p in owned)
        brand_rows.append({"brand": brand, "name": names.get(brand, brand),
            "targeted_by_new_queries": brand in tracked, "db_posts": len(owned),
            "caught_posts": caught, "caught_pct": 100*caught/len(owned) if owned else None,
            "body_only_caught": body, "quote_or_entities_only": caught-body,
            "missed_posts": len(owned)-caught,
            "missed_ids": [p["tweet_id"] for p in owned if not p["caught"]]})
    return {"mode": "offline_database_only", "provider_requests": 0,
        "window_start_utc": snapshot["window_start_utc"], "window_end_utc": snapshot["window_end_utc"],
        "snapshot_at": snapshot["snapshot_at"], "unique_db_posts": len(rows),
        "unique_caught_posts": sum(p["caught"] for p in rows),
        "unique_body_only_caught": sum(bool(p["body_call_ids"]) for p in rows),
        "evaluated_call_ids": [q["call_id"] for q in queries],
        "unevaluated_calls": {"A": "Historical list membership is absent from this snapshot; not counted."},
        "method": "Case-insensitive Boolean OR/implicit AND/parentheses; phrase adjacency; internal hyphens split words; literal model terms with East Asian adjacency; exact author exclusions. Text + stored quote + observed expanded URL hostname/path + explicit mention entities.",
        "limitations": "Local matching approximation, not X search/indexing/pagination behavior. No stemming, image OCR, linked-page fetch, author-name search or inferred list membership. Existing DB brand labels define denominators and never influence matching.",
        "brands": brand_rows, "posts": rows, "queries": queries}


def add_list_call(result, membership, manifest):
    """Replay the proposed list query using current persisted active members."""
    import copy
    result = copy.deepcopy(result)
    query = next(q["query"] for q in manifest["queries"] if q["call_id"] == "A")
    match = re.search(r"list:(\d+)", query)
    if not match or "min_faves:0" not in query:
        raise ValueError("expected list call with zero engagement floor")
    list_id = int(match.group(1))
    members = [m for m in membership["members"] if m["active"] and int(m["list_id"]) == list_id]
    handles = {normalize(m["handle"]).lstrip("@") for m in members if m.get("handle")}
    excluded = {normalize(h).lstrip("@") for h in re.findall(r"-from:([^\s()]+)", query)}
    for post in result["posts"]:
        post["keyword_call_ids"] = list(post["matched_call_ids"])
        post["list_call_matched"] = normalize(post["author_handle"]).lstrip("@") in handles and normalize(post["author_handle"]).lstrip("@") not in excluded
        if post["list_call_matched"]:
            post["matched_call_ids"].append("A")
        post["caught"] = bool(post["matched_call_ids"])
    for brand in result["brands"]:
        rows = [p for p in result["posts"] if brand["brand"] in p["brand_ids"]]
        brand["keyword_caught_posts"] = brand["caught_posts"]
        brand["call_a_matches"] = sum(p["list_call_matched"] for p in rows)
        brand["additional_from_call_a"] = sum(p["list_call_matched"] and not p["keyword_call_ids"] for p in rows)
        brand["caught_posts"] = sum(p["caught"] for p in rows)
        brand["caught_pct"] = 100*brand["caught_posts"]/len(rows) if rows else None
        brand["missed_posts"] = len(rows)-brand["caught_posts"]
        brand["missed_ids"] = [p["tweet_id"] for p in rows if not p["caught"]]
    result["keyword_unique_caught_posts"] = result["unique_caught_posts"]
    result["unique_caught_posts"] = sum(p["caught"] for p in result["posts"])
    result["call_a_additional_unique_posts"] = result["unique_caught_posts"]-result["keyword_unique_caught_posts"]
    result["call_a_membership"] = {"list_id":list_id,"active_members":len(members),"members_with_handles":sum(bool(m.get("handle")) for m in members),"snapshot_at":membership["snapshot_at"],"basis":"Current persisted active membership, matched to stored author handles; counterfactual coverage, not reconstructed historical membership."}
    result["evaluated_call_ids"].append("A")
    result["unevaluated_calls"] = {}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("queries", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--membership", type=Path)
    args = parser.parse_args()
    data = replay(json.loads(args.snapshot.read_text()), json.loads(args.queries.read_text()))
    if args.membership:
        data = add_list_call(data, json.loads(args.membership.read_text()), json.loads(args.queries.read_text()))
    data["provenance"] = {"generated_at": datetime.now(UTC).isoformat(),
        "snapshot_path": str(args.snapshot.resolve()), "snapshot_sha256": hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
        "queries_path": str(args.queries.resolve()), "queries_sha256": hashlib.sha256(args.queries.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")
    fields = ["brand", "name", "targeted_by_new_queries", "db_posts", "caught_posts", "caught_pct", "body_only_caught", "quote_or_entities_only", "missed_posts"]
    with (args.output / "by-brand.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data["brands"])
    print(json.dumps({k: data[k] for k in ["mode", "provider_requests", "unique_db_posts", "unique_caught_posts"]}))
    for row in data["brands"]:
        if row["targeted_by_new_queries"]:
            print(f"{row['brand']}: {row['caught_posts']}/{row['db_posts']} ({row['caught_pct']})")


if __name__ == "__main__":
    main()
