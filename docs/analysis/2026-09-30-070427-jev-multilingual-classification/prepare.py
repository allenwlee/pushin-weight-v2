"""Select a bounded diagnostic cohort and expose source-only review packets."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
LANGS = ("ja", "zh-cn", "ko", "en", "es", "tr")


def read_result(name):
    value = json.loads((HERE / (name + "-render-result.json")).read_text())["output"]
    # JSON may contain literal Unicode line separators inside a source string.
    # splitlines() treats those as record boundaries; PostgreSQL uses LF only.
    return next(json.loads(line) for line in value.split("\n") if line.startswith("{"))


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def stable(value):
    return hashlib.sha256((str(value) + "jev-review-v1").encode()).hexdigest()


def labels(post):
    return {e["label"] for e in post["sampling_labels_not_gold"]}


def main():
    source = read_result("cohort-candidates-v2")
    posts = source["posts"]
    assert len({p["tweet_id"] for p in posts}) == len(posts)
    exclusions = []
    safe = []
    for post in posts:
        if re.search(r"\b(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{25,}|gh[pousr]_[A-Za-z0-9]{25,})", post["text"]):
            exclusions.append({"post_id": post["tweet_id"], "reason": "credential_like_source_not_sent_to_model"})
        else:
            safe.append(post)
    selected = [p for p in safe if p["natural_rank"] is not None]
    covered = set().union(*(labels(p) for p in selected))
    selected_ids = {p["tweet_id"] for p in selected}
    frequency = Counter(k for p in safe for k in labels(p))
    for _round in range(8):
        for lang in LANGS:
            candidates = [p for p in safe if p["language"] == lang and p["tweet_id"] not in selected_ids]
            if not candidates:
                continue
            lang_covered = set().union(*(labels(p) for p in selected if p["language"] == lang))
            def rank(p):
                ls = labels(p)
                new_global = ls - covered
                new_local = ls - lang_covered
                return (-100 * len(new_global) - 10 * len(new_local)
                        - sum(1 / frequency[k] for k in ls), stable(p["tweet_id"]))
            chosen = min(candidates, key=rank)
            selected.append(chosen)
            selected_ids.add(chosen["tweet_id"])
            covered.update(labels(chosen))
    cases = []
    hints = []
    for lang in LANGS:
        group = sorted([p for p in selected if p["language"] == lang],
                       key=lambda p: (p["natural_rank"] is None, p["natural_rank"] or 0, stable(p["tweet_id"])))
        for index, post in enumerate(group, 1):
            case_id = lang.replace("-", "_") + f"_{index:02d}"
            brands = post["brand_ids"]
            assert brands
            if post["natural_rank"] is not None:
                target = min(brands, key=stable)
            else:
                target = min(brands, key=lambda b: (-sum(1 / frequency[e["label"]] for e in post["sampling_labels_not_gold"] if e["brand_id"] == b), stable(b)))
            translation = post["normalized_english"] or post["text_en"] or ""
            if translation == post["text"]:
                translation = ""
            cases.append({
                "case_id": case_id, "post_id": post["tweet_id"], "language": lang,
                "stratum": "natural" if post["natural_rank"] is not None else "coverage",
                "source_text": post["text"], "source_language_raw": post["lang"],
                "source_language_detected": post["lang_detected"],
                "english_translation": translation,
                "translation_source": "normalized" if post["normalized_english"] else "legacy" if post["text_en"] else "missing",
                "translation_provenance": post["translation_provenance"],
                "target_brand": target, "candidate_brands": brands,
                "author_handle": post["author_handle"], "author_affiliations": post["author_affiliations"],
                "created_at": post["created_at"],
                "context": {"stored_quote": post["quoted_text"] or "", "quoted_author": post["quoted_author_handle"] or "",
                            "local_parent": post["local_parent_text"] or ""},
            })
            hints.append({"case_id": case_id, "post_id": post["tweet_id"], "sampling_labels_not_gold": post["sampling_labels_not_gold"]})
    save("cohort.json", {"observed_at": source["observed_at"], "cases": cases, "tracked_brands": source["tracked_brands"]})
    save("selection.json", {"frozen_selection_at": datetime.now(timezone.utc).isoformat(),
         "eligible_counts": source["eligible_counts"], "candidate_counts": dict(Counter(p["language"] for p in posts)),
         "selected_counts": dict(Counter(p["language"] for p in cases)), "sampling_hints": hints,
         "exclusions": exclusions, "covered_sampling_labels_not_gold": sorted(covered)})
    for lang in LANGS:
        lines = [f"# Source-only reference review: {lang}", "", "Stored classifier assignments and Jev results are deliberately absent.", ""]
        for c in cases:
            if c["language"] != lang:
                continue
            lines += [f"## {c['case_id']} — target {c['target_brand']} — {c['stratum']}",
                      f"Post: {c['post_id']} | @{c['author_handle']} | other candidates: {', '.join(c['candidate_brands'])}",
                      f"Affiliations: {json.dumps(c['author_affiliations'], ensure_ascii=False)}", "", c["source_text"], ""]
            if any(c["context"].values()):
                lines += ["Stored context:", json.dumps(c["context"], ensure_ascii=False), ""]
            if c["english_translation"]:
                lines += ["Stored English translation:", c["english_translation"], ""]
        with (HERE / ("review-" + lang + ".md")).open("x") as stream:
            stream.write("\n".join(lines))
    print(json.dumps({"cases": len(cases), "languages": dict(Counter(c["language"] for c in cases)),
                     "translations": sum(bool(c["english_translation"]) for c in cases), "excluded": exclusions}))


if __name__ == "__main__":
    main()
