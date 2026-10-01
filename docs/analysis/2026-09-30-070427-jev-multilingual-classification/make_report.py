"""Render saved diagnostic scores; performs no model or database calls."""
from collections import Counter
import json
from pathlib import Path

from run import summarize

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text())


def percent(value):
    return "unmeasured" if value is None else f"{100 * value:.1f}%"


def count(summary):
    return f"{summary['correct']}/{summary['total']} ({percent(summary['agreement'])})"


def clean(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def main():
    scores = read("scores.json")
    cohort = {c["case_id"]: c for c in read("cohort.json")["cases"]}
    refs = read("references.json")["references"]
    all_rows = scores["rows"]
    raw = scores["summary"]["raw"]
    trans = scores["summary"]["translated"]
    binary = raw["combined"]["positive_binary"]
    lines = [
        "# Jev multilingual full-taxonomy diagnostic", "",
        "Completed 2026-09-30. One frozen pass; no application/model-route changes.", "",
        "## Outcome", "",
        f"On 117 posts across six languages, original-text Jev agrees with the frozen agent reference on **{count(raw['combined'])}** categorical fields. "
        f"It agrees on **every field for {raw['combined']['all_fields_correct']}/117 posts**. "
        f"Positive-label precision is **{percent(binary['precision'])}**, recall **{percent(binary['recall'])}**, and F1 **{percent(binary['f1'])}**.", "",
        "These numbers are agreement with one agent's pre-written judgments, not independently adjudicated production accuracy. "
        "Negative labels are abundant; whole-post agreement and positive-label precision/recall must accompany field agreement. "
        "The balanced-language plus coverage-seeking selection is not a random sample of the whole database.", "",
        "## Language results, original text", "",
        "| Language | Posts | Field agreement | All fields right | Positive precision | Positive recall | Positive F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for lang, s in raw["languages"].items():
        p = s["positive_binary"]
        lines.append(f"| {lang} | {s['cases']} | {count(s)} | {s['all_fields_correct']}/{s['cases']} | {percent(p['precision'])} | {percent(p['recall'])} | {percent(p['f1'])} |")
    lines += ["", "Counts: database census 279,892 posts; next three language buckets EN 197,854, ES 4,503, TR 2,226. "
              "Source review excluded one Indonesian post stored as ZH-CN, one Portuguese post stored as ES, and one non-Turkish interjection stored as TR. "
              "Mixed-language source/quote context remains in eligible cases. See the frozen contract for eligibility and limits.", "",
              "## By classification family, original text", "",
              "| Family | Field agreement | Exact family per post | Positive precision | Positive recall |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for family, s in raw["families"].items():
        p = s["positive_binary"]
        lines.append(f"| {family} | {count(s)} | {s['all_fields_correct']}/{s['cases']} | {percent(p['precision'])} | {percent(p['recall'])} |")
    lines += ["", "## Natural versus coverage sample", "",
              "| Stratum | Posts | Field agreement | Entire post | Positive precision | Positive recall |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, s in raw["strata"].items():
        p = s["positive_binary"]
        lines.append(f"| {name} | {s['cases']} | {count(s)} | {s['all_fields_correct']}/{s['cases']} | {percent(p['precision'])} | {percent(p['recall'])} |")
    lines += ["", "## Does adding the stored English translation help?", "",
              "Only 68 non-English posts have a distinct stored English translation. The table compares identical posts; it does not compare the translated subset with all 117 originals. "
              "Translations are unchanged saved outputs, sometimes summaries. Original source/quote/parent text remains, and no new translation or extractor call was made.", "",
              "| Paired population | Original field agreement | With English | Original positive F1 | With English positive F1 |",
              "| --- | ---: | ---: | ---: | ---: |"]
    paired_ids = {r["case_id"] for r in all_rows if r["arm"] == "translated"}
    for lang in ["all"] + sorted({cohort[c]["language"] for c in paired_ids}):
        variants = {}
        for arm in ("raw", "translated"):
            variants[arm] = summarize([r for r in all_rows if r["arm"] == arm and r["case_id"] in paired_ids and (lang == "all" or r["language"] == lang)])
        a, b = variants["raw"], variants["translated"]
        lines.append(f"| {lang}, {a['cases']} posts | {count(a)} | {count(b)} | {percent(a['positive_binary']['f1'])} | {percent(b['positive_binary']['f1'])} |")
    lines += ["", "A single call per arm does not separate translation effects from model variability. There is no English duplicate-call control and no language-wide calibration claim.", "",
              "## Per-label support and errors, original text", "",
              "Zero positive support means recall is unmeasured, not perfect. Scant positives are coverage evidence, not reliability estimates.", "",
              "| Binary label | Reference positives | TP | FP | FN incl. invalid | Precision | Recall |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    unsupported = []
    for field, s in scores["label_results"]["raw"].items():
        if ":" not in field:
            continue
        p = s["positive_binary"]
        support = p["tp"] + p["fn"]
        if not support:
            unsupported.append(field)
        lines.append(f"| {field} | {support} | {p['tp']} | {p['fp']} | {p['fn']} | {percent(p['precision'])} | {percent(p['recall'])} |")
    lines += ["", "Unmeasured positive recall: " + ", ".join(f"`{v}`" for v in unsupported) + ".", "",
              "## Output validity and cross-answer consistency", "",
              f"Invalid fields: raw {raw['combined']['invalid']}, translated {trans['combined']['invalid']}. "
              "Invalid fields count as incorrect; valid siblings remain scored. No choice was changed to match its probabilities.", "",
              f"Responses with a consistency issue or extra output field: {len(scores['consistency_issues'])}/{scores['usage']['calls']}.", ""]
    issue_counts = Counter(issue for r in scores["consistency_issues"] for issue in r["issues"])
    for issue, n in issue_counts.most_common():
        lines.append(f"- `{issue}`: {n} responses.")
    lines += ["", "Raw answers remain unchanged. An integration needs explicit policy for conflicting independent answers, unavailable/none sentinels, invalid Choice responses and pending/retry state. "
              "These diagnostic scripts do not implement a production provider adapter.", "",
              "## Confidence is not a correctness guarantee", "",
              "Bins use probability of the selected answer, not Choice's separate distribution-sharpness confidence. "
              "This selected, unweighted development set with agent labels cannot validate production calibration or select a safe fallback cutoff.", "",
              "| Selected-answer probability, original arm | Reference agreement |",
              "| --- | ---: |"]
    for label, item in scores["confidence_bins_descriptive_only"]["raw"].items():
        lines.append(f"| {label} | {item['correct']}/{item['total']} |")
    lines += ["", "## Predeclared reference sensitivity", "",
              "Strict scores above remain primary. Before inference we flagged Meta-company versus Llama attribution (`es_14`), "
              "China stance intensity (`zh_cn_08`), and a national-origin-model generalization (`tr_19`). "
              f"Removing only the specified fields yields raw {count(raw['sensitivity'])} and translated {count(trans['sensitivity'])}. "
              "This does not resolve other debatable label boundaries, including news/opinion overlap and showcase-versus-promotion.", "",
              "## Extraction boundary and migration implications", "",
              "Jev returned only categorical decisions/probabilities. The prospective separate extractor would handle promoted entity identity, handles/domains, "
              "exact supporting passages and detailed event/job/personnel records. No extractor quality, extraction cost, dependency ordering or classifier-extractor consistency was measured. "
              "Jev still had to understand who/what the post discusses; removing extraction output does not remove that reasoning requirement.", "",
              "The test supplied candidate brand associations and known account facts from storage, all 49 tracked brands/curated aliases, and source-matched products from a 1,804-product catalog. "
              "It supplied no manually corrected promoted-company identity, expected label or previous model assignment. "
              "Only one selected author had a known official relationship, so staff/community/official differences are not adequately validated here.", "",
              "Translation and commentary configuration remains Gemma; headline generation and the application classifier remain unchanged. "
              "This is not evidence that changing one config model string would be safe, nor authorization to reclassify the database.", "",
              "## Usage and audit", "",
              f"- Calls: {scores['usage']['calls']} (117 original, 68 with stored English), zero retries.",
              f"- Input tokens: {scores['usage']['input_tokens']:,}; output tokens: {scores['usage']['output_tokens']:,} (unbilled under the checked Jev price).",
              f"- Model-cost estimate: US${scores['usage']['estimated_usd']} at $0.042/M input; ceiling $0.50. Not an invoice.",
              f"- Median local HTTPS request: {scores['usage']['median_seconds']:.3f} s; range {scores['usage']['min_seconds']:.3f}–{scores['usage']['max_seconds']:.3f} s.",
              "- Timing is local end-to-end request time; no matched 0731 speed/cost trial or production-throughput/load test.",
              f"- Read-only DB calls: {scores['audit']['db_calls']}; includes the retained SQL syntax-error receipt.",
              "- Frozen hashes, start/response counts, cost reconciliation and protected app/test hashes verified.",
              "- No application changes, DB writes, new X retrieval, deployment, scheduler mutation or model switch.", "",
              "## Evidence", "",
              "- [Frozen scope](scope.md), [evaluation contract](contract.md), [hashes](frozen.json).",
              "- [Exact requests](requests.json), [question definitions](questions.py), [source cohort](cohort.json).",
              "- [Frozen reference judgments and notes](reference_rows.json), [expanded references](references.json).",
              "- [Scores and raw probabilities](scores.json), [all disagreements](disagreements.json), [per-case review](case-results.md).",
              "- Raw provider and accounting receipts: `receipts/`; read-only SQL/Render responses retained alongside.",
              "- [Prior findings record](../2026-09-30-160557-jev-classification-findings.md).", "",
    ]
    with (HERE / "report.md").open("x") as stream:
        stream.write("\n".join(lines))

    case_lines = ["# Per-case Jev results against frozen source review", "",
                  "Reference judgments are not independent human ground truth. Every mismatch is preserved, including contestable boundaries.", ""]
    for case_id, case in cohort.items():
        if case_id not in refs:
            case_lines += [f"## {case_id} — excluded before inference", "", "See reference_rows.json for the source-language mismatch.", ""]
            continue
        case_rows = [r for r in all_rows if r["case_id"] == case_id]
        case_lines += [f"## {case_id} — {case['target_brand']} — {case['stratum']}", "",
                       f"[Source post](https://x.com/{case['author_handle']}/status/{case['post_id']}); "
                       f"[verbatim source/translation packet](review-{case['language']}.md).", "",
                       "Frozen rationale: " + refs[case_id]["note"], "",
                       "| Arm | Correct fields | Invalid fields |", "| --- | ---: | ---: |"]
        for arm in ("raw", "translated"):
            selected = [r for r in case_rows if r["arm"] == arm]
            if selected:
                s = summarize(selected)
                case_lines.append(f"| {arm} | {s['correct']}/{s['total']} | {s['invalid']} |")
        errors = [r for r in case_rows if not r["correct"]]
        if errors:
            case_lines += ["", "| Arm | Field | Reference | Jev | Selected probability |", "| --- | --- | --- | --- | ---: |"]
            for r in errors:
                case_lines.append(f"| {r['arm']} | {r['field']} | {clean(r['expected'])} | {clean(r['assigned']) if r['valid'] else 'INVALID'} | {percent(r.get('selected_probability'))} |")
        case_lines.append("")
    with (HERE / "case-results.md").open("x") as stream:
        stream.write("\n".join(case_lines))
    print(json.dumps({"report": str(HERE / "report.md"), "unmeasured_positive_recall": unsupported,
                      "consistency_counts": dict(issue_counts)}))


if __name__ == "__main__":
    main()
