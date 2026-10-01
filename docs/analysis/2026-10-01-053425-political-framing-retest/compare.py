"""Read-only reconciliation of the frozen political prompt rerun, then append reports."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import prepare

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OLD = {
    "jev": REPO / "docs/analysis/2026-09-30-070427-jev-multilingual-classification",
    "0731": REPO / "docs/analysis/2026-09-30-074728-0731-multilingual-comparison",
}
GEO = ("geo:reporting", "geo:framework", "geo:nationalism")


def read(path):
    return json.loads(path.read_text())


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def key(row):
    return row["case_id"], row["field"]


def summarize(rows):
    valid = [r for r in rows if r["valid"]]
    binary = [r for r in rows if isinstance(r["expected"], bool)]
    tp = sum(r["valid"] and r["assigned"] is True and r["expected"] for r in binary)
    fp = sum(r["valid"] and r["assigned"] is True and not r["expected"] for r in binary)
    fn_valid = sum(r["valid"] and r["assigned"] is False and r["expected"] for r in binary)
    invalid_positive = sum(not r["valid"] and r["expected"] for r in binary)
    fn = fn_valid + invalid_positive
    tn = sum(r["valid"] and r["assigned"] is False and not r["expected"] for r in binary)
    cases = {r["case_id"] for r in rows}
    correct = sum(r["correct"] for r in rows)
    return {
        "fields": len(rows), "cases": len(cases), "correct": correct,
        "unsuccessful": len(rows) - correct, "valid": len(valid),
        "invalid": len(rows) - len(valid),
        "valid_wrong": sum(not r["correct"] for r in valid),
        "accuracy": ratio(correct, len(rows)),
        "valid_only_accuracy": ratio(correct, len(valid)),
        "exact_posts": sum(all(r["correct"] for r in rows if r["case_id"] == c) for c in cases),
        "posts_with_false_positives": len({r["case_id"] for r in binary
            if r["valid"] and r["assigned"] is True and not r["expected"]}),
        "posts_with_invalid_fields": len({r["case_id"] for r in rows if not r["valid"]}),
        "tp": tp, "fp": fp, "fn_including_invalid": fn, "fn_valid_only": fn_valid,
        "invalid_positive": invalid_positive, "tn": tn,
        "positive_reference_fields": tp + fn,
        "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
    }


def sensitivity_keep(row):
    # Exact predeclared rules from the historical Jev runner, without additions.
    if row["case_id"] == "es_14" and not row["field"].startswith("promotion:"):
        return False
    if row["case_id"] == "zh_cn_08" and row["field"] == "china_national_stance":
        return False
    if row["case_id"] == "tr_19" and (
        row["field"].startswith("geo:") or row["field"].endswith("national_stance")
    ):
        return False
    return True


def paired(before, after):
    left, right = {key(r): r for r in before}, {key(r): r for r in after}
    assert left.keys() == right.keys()
    transitions = Counter()
    changed = []
    for pair_key in sorted(left):
        old, new = left[pair_key], right[pair_key]
        assert old["expected"] == new["expected"]
        old_state = "invalid" if not old["valid"] else "correct" if old["correct"] else "wrong"
        new_state = "invalid" if not new["valid"] else "correct" if new["correct"] else "wrong"
        transitions[f"{old_state}_to_{new_state}"] += 1
        if (old["assigned"], old["valid"]) != (new["assigned"], new["valid"]):
            changed.append({"case_id": pair_key[0], "field": pair_key[1],
                "expected": old["expected"], "old": old, "new": new})
    both_valid = {k for k in left if left[k]["valid"] and right[k]["valid"]}
    return {
        "old": summarize(before), "new": summarize(after),
        "errors_corrected": sum(not left[k]["correct"] and right[k]["correct"] for k in left),
        "correct_answers_broken": sum(left[k]["correct"] and not right[k]["correct"] for k in left),
        "net_correct_change": sum(right[k]["correct"] - left[k]["correct"] for k in left),
        "transitions": dict(sorted(transitions.items())), "changed_labels_or_validity": changed,
        "matched_valid_only": {
            "old": summarize([left[k] for k in both_valid]),
            "new": summarize([right[k] for k in both_valid]),
            "excluded_fields": len(left) - len(both_valid),
        },
    }


def analyze(provider, references):
    old_score = read(OLD[provider] / "scores.json")
    new_score = read(HERE / provider / "scores.json")
    old = [r for r in old_score["rows"] if r["arm"] == "raw"]
    new = new_score["rows"]
    assert len(old) == len(new) == 117 * 38
    for rows in (old, new):
        assert len({key(r) for r in rows}) == 117 * 38
        for row in rows:
            assert row["expected"] == references[row["case_id"]]["expected"][row["field"]]
            assert row["correct"] == (row["valid"] and row["assigned"] == row["expected"])
    def section(predicate):
        return paired([r for r in old if predicate(r)], [r for r in new if predicate(r)])
    result = {
        "overall": paired(old, new),
        "geo": section(lambda r: r["field"] in GEO),
        "geo_fields": {field: section(lambda r, f=field: r["field"] == f) for field in GEO},
        "unchanged_questions": section(lambda r: r["field"] not in GEO),
        "families": {family: section(lambda r, f=family: r["family"] == f)
            for family in sorted({r["family"] for r in new})},
        "geo_languages": {lang: section(lambda r, l=lang: r["language"] == l and r["field"] in GEO)
            for lang in sorted({r["language"] for r in new})},
        "geo_strata": {stratum: section(lambda r, s=stratum: r["stratum"] == s and r["field"] in GEO)
            for stratum in ("natural", "coverage")},
        "sensitivity": section(sensitivity_keep),
        "geo_sensitivity": section(lambda r: r["field"] in GEO and sensitivity_keep(r)),
        "new_usage": (read(HERE / provider / "complete.json") if provider == "jev" else new_score["usage"]),
        "new_audit": new_score["audit"],
    }
    if provider == "jev":
        assert result["geo"]["old"]["fp"] == 136
        assert result["geo"]["old"]["tp"] == 24
        assert result["geo"]["old"]["exact_posts"] == 32
    else:
        assert result["geo"]["old"]["fp"] == 14
        assert result["geo"]["old"]["tp"] == 10
        assert result["geo"]["old"]["invalid"] == 39
        assert result["geo"]["old"]["exact_posts"] == 88
    return result, old, new


def pct(number):
    return "—" if number is None else f"{number:.1%}"


def metric_table(arms, title, section):
    lines = [f"## {title}", "", "| Measure | Jev old | Jev new | 0731 old | 0731 new |",
        "|---|---:|---:|---:|---:|"]
    columns = [arms[provider][section][era] for provider in ("jev", "0731") for era in ("old", "new")]
    metrics = (
        ("Correct fields / total", lambda r: f"{r['correct']}/{r['fields']} ({pct(r['accuracy'])})"),
        ("All fields correct per post", lambda r: f"{r['exact_posts']}/{r['cases']}"),
        ("True positive labels", lambda r: r["tp"]),
        ("False positive labels", lambda r: r["fp"]),
        ("Missed positive labels (including invalid)", lambda r: r["fn_including_invalid"]),
        ("Invalid fields", lambda r: r["invalid"]),
        ("Valid but wrong fields", lambda r: r["valid_wrong"]),
        ("Posts with false positives", lambda r: r["posts_with_false_positives"]),
        ("Positive-label precision", lambda r: pct(r["precision"])),
        ("Positive-label recall", lambda r: pct(r["recall"])),
    )
    for label, getter in metrics:
        lines.append("| " + label + " | " + " | ".join(str(getter(c)) for c in columns) + " |")
    return lines


def make_report(arms):
    lines = ["# Political wording retest — Jev and 0731", "",
        "117 identical original-text posts; 38 questions per post; the same frozen reference judgments. "
        "Only the three political-mode prompts changed. Both arms ran once with no model retries.", "",
        "These are agreements with frozen agent-written reference labels, not independently human-verified accuracy. "
        "This known-cohort, post-feedback rerun has no simultaneous old-prompt control. The category rename and "
        "framework rewrite were tested together, so their separate effects are not measured.", ""]
    lines += metric_table(arms, "Primary result: three political modes", "geo")
    lines += ["", "False negatives include invalid answers on reference-positive fields. Invalid negative fields "
        "are also unsuccessful, so TP/FP/FN/TN alone do not cover every invalid field. "
        "There are 27 reference-positive political labels (13 reporting, 9 framework, 5 nationalism).", "",
        "## Paired changes", "",
        "| Provider | Previously wrong/invalid, now correct | Previously correct, now wrong/invalid | Net correct change |",
        "|---|---:|---:|---:|"]
    for provider in ("jev", "0731"):
        result = arms[provider]["geo"]
        lines.append(f"| {provider} | {result['errors_corrected']} | {result['correct_answers_broken']} | {result['net_correct_change']:+d} |")
    lines += ["", "The complete correct/wrong/invalid transition matrices and paired valid-only views are in "
        "[comparison.json](comparison.json); valid-only views omit the same fields on both sides and do not predict "
        "what a repaired response would have said.", "", "## Political subtype results", "",
        "Each cell is `true positives / false positives / missed positives / invalid fields`.", "",
        "| Subtype | Jev old | Jev new | 0731 old | 0731 new |", "|---|---:|---:|---:|---:|"]
    for field in GEO:
        cells = []
        for provider in ("jev", "0731"):
            for era in ("old", "new"):
                r = arms[provider]["geo_fields"][field][era]
                cells.append(f"{r['tp']} / {r['fp']} / {r['fn_including_invalid']} / {r['invalid']}")
        lines.append(f"| {field.removeprefix('geo:')} | " + " | ".join(cells) + " |")
    lines += ["", "## What the Jev change did", "",
        "Most of Jev's improvement came from the rewritten framework question: false positives fell from 74 "
        "to 5, but true positives also fell from 8 to 4. Reporting remained the main source of false tags "
        "(38), despite detecting all 13 reference-positive reporting labels. Nationalism's aggregate "
        "TP/FP/FN counts were unchanged, although some individual answers changed.", "",
        "The four newly missed framework positives are `ja_16` (Europe versus US/China AI capability), "
        "`ko_01` (China's computing-resource limitation), `es_12` (Chinese AI price pressure on US firms), "
        "and `es_13` (politically triggered insecure code and open-model origin/security risk). These remain "
        "misses against the frozen references. Several illustrate a genuine scope question: wording centered "
        "on governments or relationships between countries can exclude national-technology and market "
        "framing that the old definition intended to include. This run does not relabel them after seeing answers.", "",
        "A simple remaining error is `en_07`: “@NousResearch when are we getting deepseek flash 4.1?” "
        "Jev's framework score fell from 50% to 8%, but its political-reporting score stayed positive "
        "(51% to 52%). That shows the framework improvement did not repair reporting's boundary."]
    lines += [""] + metric_table(arms, "All 38 fields (secondary)", "overall")
    lines += ["", "In this all-field table, accuracy and exact-post counts cover all 38 questions. "
        "TP/FP/FN, precision, and recall cover only the 34 binary questions, excluding the four "
        "categorical choices (outcome, sentiment, and two country stances)."]
    lines += ["", "## Unchanged questions and other class families", "",
        "The other 35 questions were not rewritten. Changes in them can reflect different sampled outputs or "
        "interactions among questions; this design cannot attribute all differences to the prompt edit.", "",
        "| Family | Jev old correct | Jev new correct | 0731 old correct | 0731 new correct |",
        "|---|---:|---:|---:|---:|"]
    for family in arms["jev"]["families"]:
        cells = []
        for provider in ("jev", "0731"):
            for era in ("old", "new"):
                r = arms[provider]["families"][family][era]
                cells.append(f"{r['correct']}/{r['fields']} (invalid {r['invalid']})")
        lines.append(f"| {family} | " + " | ".join(cells) + " |")
    lines += ["", "## Political results by source language", "",
        "Each cell is correct political fields / total; invalid fields count as unsuccessful.", "",
        "| Language | Jev old | Jev new | 0731 old | 0731 new |", "|---|---:|---:|---:|---:|"]
    for lang in arms["jev"]["geo_languages"]:
        cells = []
        for provider in ("jev", "0731"):
            for era in ("old", "new"):
                r = arms[provider]["geo_languages"][lang][era]
                cells.append(f"{r['correct']}/{r['fields']}")
        lines.append(f"| {lang} | " + " | ".join(cells) + " |")
    lines += ["", "## Predeclared reference sensitivity", "",
        "Exactly the prior exclusions are retained: `es_14` except promotion, `zh_cn_08` China stance, "
        "and `tr_19` political modes/national stances. No new exclusions or reference edits were made.", ""]
    for provider in ("jev", "0731"):
        r = arms[provider]["geo_sensitivity"]
        lines.append(f"- {provider}: political correct fields {r['old']['correct']}/{r['old']['fields']} "
            f"→ {r['new']['correct']}/{r['new']['fields']}.")
    lines += ["", "## Cost, timing, and audit", ""]
    for provider in ("jev", "0731"):
        usage = arms[provider]["new_usage"]
        cost = usage.get("estimated_input_cost_usd", usage.get("estimated_usd"))
        lines.append(f"- {provider}: {usage['calls']} calls, model estimate US${cost}, "
            f"median request {usage['median_seconds']:.3f}s; 0 retries.")
    lines += ["", "Model estimates are not invoices and exclude Render compute. Jev ran locally and 0731 on "
        "Render, so timing is observed end-to-end latency, not a controlled throughput benchmark. "
        "Caps were US$0.25 and 117 calls per provider; no probes or format-repair calls.", "",
        "Frozen common input, reference, historical baseline, and protected application/test hashes were verified "
        "before reconciliation. No production prompt, application, database, translation/commentary configuration, "
        "scheduler, or deployment was changed for this experiment.", "",
        "## Evidence", "",
        "[Frozen contract](contract.md), [exact prompt diff](prompt-diff.json), [shared hashes](frozen.json), "
        "[full numerical comparison](comparison.json), [per-post political review](geo-cases.md), "
        "[Jev receipts and scores](jev/scores.json), [0731 receipts and scores](0731/scores.json).", ""]
    return "\n".join(lines)


def display(row):
    if not row["valid"]:
        return "INVALID"
    p = row.get("probabilities", {}).get("true")
    if p is None and isinstance(row.get("selected_probability"), (int, float)):
        p = row["selected_probability"] if row["assigned"] else 1 - row["selected_probability"]
    return f"{str(row['assigned']).lower()}" + (f" ({p:.0%} yes)" if p is not None else "")


def case_report(all_rows, requests, references):
    indexed = {(provider, era): {key(r): r for r in rows}
        for provider, eras in all_rows.items() for era, rows in eras.items()}
    translations = {r["case_id"]: r["request"]["state"].get("english_translation")
        for r in read(OLD["jev"] / "requests.json") if r["arm"] == "translated"}
    lines = ["# Per-post political review", "",
        "Original saved text and unchanged source context; English translations below are stored historical "
        "translations, not new model output. The new test itself used original text only.", ""]
    for item in requests:
        case, state = item["case_id"], item["request"]["state"]
        lines += [f"## {case} — {item['language']} — {item['stratum']}", "",
            f"Target brand: `{state['target_brand']}`. Author: `@{state['author_handle']}`.", "",
            "```text", state["source_text"], "```", ""]
        if translations.get(case):
            lines += ["Stored English translation:", "", "```text", translations[case], "```", ""]
        context = state.get("context", {})
        for field in ("stored_quote", "local_parent"):
            if context.get(field):
                lines += [f"{field}:", "", "```text", context[field], "```", ""]
        lines += ["| Mode | Frozen reference | Jev old | Jev new | 0731 old | 0731 new |",
            "|---|---|---|---|---|---|"]
        for field in GEO:
            cells = [display(indexed[provider, era][case, field])
                for provider in ("jev", "0731") for era in ("old", "new")]
            expected = references[case]["expected"][field]
            lines.append(f"| {field.removeprefix('geo:')} | {str(expected).lower()} | " + " | ".join(cells) + " |")
        lines += ["", "Original reference note: " + references[case].get("note", ""), ""]
    return "\n".join(lines)


def main():
    prepare.verify()
    refs = read(HERE / "references.json")["references"]
    arms, rows = {}, {}
    for provider in ("jev", "0731"):
        arms[provider], old, new = analyze(provider, refs)
        rows[provider] = {"old": old, "new": new}
    paths = [HERE / provider / "scores.json" for provider in ("jev", "0731")]
    output = {"at": datetime.now(timezone.utc).isoformat(), "arms": arms,
        "audit": {"shared_frozen_sha256": prepare.file_digest(HERE / "frozen.json"),
            "compare_source_sha256": prepare.file_digest(Path(__file__)),
            "score_hashes": {str(p.relative_to(HERE)): prepare.file_digest(p) for p in paths},
            "common_baseline_and_protected_hashes_verified": True}}
    report = make_report(arms)
    cases = case_report(rows, prepare.load_requests(), refs)
    for name, value in (("comparison.json", json.dumps(output, ensure_ascii=False, indent=2) + "\n"),
                        ("report.md", report), ("geo-cases.md", cases)):
        with (HERE / name).open("x", encoding="utf-8") as stream:
            stream.write(value)
    print(json.dumps({p: {"old_geo": arms[p]["geo"]["old"], "new_geo": arms[p]["geo"]["new"],
        "paired": {k: arms[p]["geo"][k] for k in ("errors_corrected", "correct_answers_broken", "net_correct_change")}}
        for p in arms}, indent=2))


if __name__ == "__main__":
    main()
