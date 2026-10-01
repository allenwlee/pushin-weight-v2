"""Generate a comparison only from saved scores; never submit model calls."""
from collections import Counter
import json

import run

HERE, JEV = run.HERE, run.JEV
s = run.read("scores.json")
j = json.loads((JEV / "scores.json").read_text())
pairs = run.read("model-pairs.json")
cohort = {c["case_id"]: c for c in json.loads((JEV / "cohort.json").read_text())["cases"]}
refs = json.loads((JEV / "references.json").read_text())["references"]


def pct(value):
    return "unmeasured" if value is None else f"{100 * value:.1f}%"


def agreement(value):
    return f'{value["correct"]}/{value["total"]} ({pct(value["agreement"])})'


def positive(value, key):
    return pct(value["positive_binary"][key])


def table(headers, rows):
    return ["| " + " | ".join(map(str, headers)) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *["| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |" for row in rows], ""]


def pair_counts(arm, family=None):
    part = [p for p in pairs if p["arm"] == arm and (family is None or p["field"].split(":")[0] == family)]
    return {"both_right": sum(p["jev_correct"] and p["0731_correct"] for p in part),
        "0731_only_right": sum(not p["jev_correct"] and p["0731_correct"] for p in part),
        "jev_only_right": sum(p["jev_correct"] and not p["0731_correct"] for p in part),
        "both_wrong": sum(not p["jev_correct"] and not p["0731_correct"] for p in part)}


raw, jraw = s["summary"]["raw"]["combined"], j["summary"]["raw"]["combined"]
counts = pair_counts("raw")
lines = ["# 0731 versus Jev: matched multilingual full-taxonomy diagnostic", "",
    "Completed 2026-09-30. One frozen pass on existing evidence; no application changes.", "",
    "## Main result", "",
    f'On the same 117 original-text posts, 0731 agrees with the frozen agent reference on **{agreement(raw)}** fields, '
    f'versus Jev **{agreement(jraw)}**. Complete 38-field agreement occurs on '
    f'**{raw["all_fields_correct"]}/117 posts** for 0731 and **{jraw["all_fields_correct"]}/117** for Jev.', "",
    f'0731 positive-label precision is **{positive(raw, "precision")}**, recall **{positive(raw, "recall")}**, '
    f'and F1 **{positive(raw, "f1")}**. Jev has **{positive(jraw, "precision")}**, '
    f'**{positive(jraw, "recall")}**, and **{positive(jraw, "f1")}**, respectively. '
    "Positive precision is the fraction of assigned tags supported by the reference; recall is the fraction of reference-positive tags recovered.", "",
    f'Paired original-field outcomes: both right {counts["both_right"]}; 0731 alone right {counts["0731_only_right"]}; '
    f'Jev alone right {counts["jev_only_right"]}; both wrong {counts["both_wrong"]}. '
    f'Net difference: {counts["0731_only_right"] - counts["jev_only_right"]:+d} matching fields.', "",
    "These are agreements with a single agent's source judgments fixed before either run, not independent human-adjudicated production accuracy. "
    "Most binary answers should be negative. The balanced-language and coverage-seeking selection is not representative of whole-database prevalence. "
    "Neither model should be judged from field agreement alone.", "",
    "## What was held fixed", "",
    "Same 117 source posts, one target brand per post, 38 question definitions/criteria, original/quote/parent text, "
    "account relationships, 49-brand catalog with source-matched products, 68 stored English translations, question/input serialization, "
    "reference answers, exclusions and sensitivity rules. Same 185-call order. No new source collection or Jev calls.", "",
    "0731 used the existing direct-DeepInfra non-reasoning profile (temperature 1, top_p 1, seed 42, reasoning_effort none, "
    "standard tier), with a 4,096-token output ceiling fixed before calls. The user content exactly matches Jev's state/questions objects. "
    "The system wrapper adapts those questions to compact JSON labels plus self-reported probability distributions; "
    "it is verbatim the prior matched test's B_probabilities wrapper. This is not the current application's production classifier prompt, "
    "nor a test of a higher-reasoning 0731 configuration. No labels-only comparison arm was added.", "",
    "The same >=50% threshold maps binary probabilities to labels; fixed-choice labels must maximize their distributions. "
    "0731's written percentages and Jev's native decision probabilities have different production mechanisms. "
    "Agreement here does not attribute any difference uniquely to model weights, API design, eliciting probabilities, or parallel question handling.", "",
    "## Language results — original text", ""]
languages = ["ja", "zh-cn", "ko", "en", "es", "tr"]
lines += table(["Language", "Posts", "Jev field agreement", "0731 field agreement", "Jev positive precision / recall", "0731 positive precision / recall", "0731 entire post"], [
    [lang, s["summary"]["raw"]["languages"][lang]["cases"],
     agreement(j["summary"]["raw"]["languages"][lang]), agreement(s["summary"]["raw"]["languages"][lang]),
     positive(j["summary"]["raw"]["languages"][lang], "precision") + " / " + positive(j["summary"]["raw"]["languages"][lang], "recall"),
     positive(s["summary"]["raw"]["languages"][lang], "precision") + " / " + positive(s["summary"]["raw"]["languages"][lang], "recall"),
     str(s["summary"]["raw"]["languages"][lang]["all_fields_correct"])] for lang in languages])
lines += ["English, Spanish and Turkish were the next three language buckets in the saved 279,892-post database census. "
    "Three incorrect language assignments were excluded before either model ran; no new exclusions occurred. "
    "Small, differently composed language samples do not establish a general language ranking.", "",
    "## Classification families — original text", ""]
families = s["summary"]["raw"]["families"]
lines += table(["Family", "Jev field agreement", "0731 field agreement", "Jev positive precision / recall", "0731 positive precision / recall", "0731 exact family"], [
    [f, agreement(j["summary"]["raw"]["families"][f]), agreement(families[f]),
     positive(j["summary"]["raw"]["families"][f], "precision") + " / " + positive(j["summary"]["raw"]["families"][f], "recall"),
     positive(families[f], "precision") + " / " + positive(families[f], "recall"),
     f'{families[f]["all_fields_correct"]}/117'] for f in families])
lines += ["Positive precision/recall applies to binary memberships, not the four scalar families.", "",
    "## Original problem areas and per-label errors", "",
    "TP = supported positive assignment; FP = unsupported positive assignment; FN = missed reference positive, including invalid answers. "
    "False means disagreement with the fixed agent reference, not an independently settled error for every subjective boundary.", ""]
labels = [f for f, value in s["label_results"]["raw"].items()
          if any(isinstance(r["expected"], bool) for r in s["rows"] if r["field"] == f)]
lines += table(["Label", "Reference positives", "Jev TP / FP / FN", "0731 TP / FP / FN", "Jev precision / recall", "0731 precision / recall"], [
    [f, s["label_results"]["raw"][f]["positive_binary"]["tp"] + s["label_results"]["raw"][f]["positive_binary"]["fn"],
     " / ".join(str(j["label_results"]["raw"][f]["positive_binary"][k]) for k in ("tp", "fp", "fn")),
     " / ".join(str(s["label_results"]["raw"][f]["positive_binary"][k]) for k in ("tp", "fp", "fn")),
     positive(j["label_results"]["raw"][f], "precision") + " / " + positive(j["label_results"]["raw"][f], "recall"),
     positive(s["label_results"]["raw"][f], "precision") + " / " + positive(s["label_results"]["raw"][f], "recall")]
    for f in labels])
lines += ["Scam and unauthorized promotion have no reference-positive examples; their positive recall is unmeasured, not perfect. "
    "Spam, jobs and several other labels have very few positives. Only one selected author has a known official relationship, "
    "so this does not validate the proposed affiliation-dependent promotion policy.", "", "## Natural versus coverage selection", ""]
lines += table(["Sample", "Posts", "Jev field agreement", "0731 field agreement", "0731 positive precision / recall"], [
    [st, s["summary"]["raw"]["strata"][st]["cases"], agreement(j["summary"]["raw"]["strata"][st]),
     agreement(s["summary"]["raw"]["strata"][st]), positive(s["summary"]["raw"]["strata"][st], "precision") + " / " +
     positive(s["summary"]["raw"]["strata"][st], "recall")] for st in ("natural", "coverage")])
lines += ["## Translation comparison on identical paired posts", "",
    "Only the 68 posts with a distinct saved English translation are compared here. Original and quote/parent source remain in both inputs. "
    "Stored translations can be summaries; none was generated or repaired for this experiment.", ""]
lines += table(["Model", "Paired original field agreement", "With translation", "Original positive F1", "With translation positive F1"], [
    [name, agreement(result["paired"]["raw"]), agreement(result["paired"]["translated"]),
     positive(result["paired"]["raw"], "f1"), positive(result["paired"]["translated"], "f1")]
    for name, result in (("Jev", j), ("0731", s))])
paired_ids = {r["case_id"] for r in s["rows"] if r["arm"] == "translated"}
lines += table(["Language", "Paired posts", "0731 original", "0731 with translation"], [
    [lang, len({r["case_id"] for r in s["rows"] if r["language"] == lang and r["arm"] == "translated"}),
     agreement(run.jev.summarize([r for r in s["rows"] if r["language"] == lang and r["arm"] == "raw" and r["case_id"] in paired_ids])),
     agreement(run.jev.summarize([r for r in s["rows"] if r["language"] == lang and r["arm"] == "translated"]))]
    for lang in languages if lang != "en"])
lines += ["One observation per arm does not separate translation effects from model variability. No repeatability or fresh-translation study was run.", "",
    "## Output validity and consistency", "",
    f'Invalid 0731 fields: raw **{raw["invalid"]}**, translated **{s["summary"]["translated"]["combined"]["invalid"]}**. '
    f'Raw semantic-label agreement ignoring only probability-format failures: **{agreement(s["summary"]["raw"]["semantic_labels"])}**. '
    "Strict scores remain primary; no response was repaired or retried.", "",
    f'0731 responses with cross-answer/envelope/extra-output issues: **{len(s["consistency_issues"])}/185**; '
    f'Jev: **{len(j["consistency_issues"])}/185**. Counts by issue can overlap:', ""]
issues = Counter(code for response in s["consistency_issues"] for code in response["issues"])
lines += [f"- `{code}`: {count}." for code, count in sorted(issues.items())] or ["- None recorded."]
lines += ["", "Independent valid answers can still conflict; no hidden reconciliation step cleared such answers before scoring.", "",
    "## Self-reported confidence — descriptive only", "",
    "Selected-answer probabilities, not token likelihoods. Bins are neither a calibration validation nor a proposed routing threshold; "
    "easy negative decisions dominate the highest-confidence bin.", ""]
bins = []
for low, high in ((0, .6), (.6, .8), (.8, .9), (.9, 1.000001)):
    row = [f'{low:.2f}–{min(high, 1):.2f}']
    for result in (j, s):
        subset = [r for r in result["rows"] if r["arm"] == "raw" and r["valid"] and low <= r["selected_probability"] < high]
        row.append(agreement(run.jev.summarize(subset)))
    bins.append(row)
lines += table(["Probability bin", "Jev reference agreement", "0731 reference agreement"], bins)
lines += ["## Predeclared reference sensitivity", "",
    f'Omitting only the original three sets of flagged reference fields yields 0731 **{agreement(s["summary"]["raw"]["sensitivity"])}**, '
    f'versus Jev **{agreement(j["summary"]["raw"]["sensitivity"])}**. '
    "Strict results above stay primary. There were no post-response edits to expected answers.", "",
    "## Cost and observed request time", ""]
lines += table(["Metric", "Jev", "0731"], [
    ["Physical model calls", j["usage"]["calls"], s["usage"]["calls"]],
    ["Input tokens", j["usage"]["input_tokens"], s["usage"]["input_tokens"]],
    ["Output tokens", j["usage"]["output_tokens"], s["usage"]["output_tokens"]],
    ["Reported cached input tokens", "not reported by this comparison", s["usage"]["cached_input_tokens"]],
    ["Estimated model USD", j["usage"]["estimated_usd"], s["usage"]["estimated_usd"]],
    ["Median HTTPS seconds", f'{j["usage"]["median_seconds"]:.3f}', f'{s["usage"]["median_seconds"]:.3f}'],
    ["Range, seconds", f'{j["usage"]["min_seconds"]:.3f}–{j["usage"]["max_seconds"]:.3f}',
     f'{s["usage"]["min_seconds"]:.3f}–{s["usage"]["max_seconds"]:.3f}']])
lines += ["0731 spend is the sum of provider-returned estimated_cost; Jev uses the previously checked input-only price. "
    "Neither is an invoice. 0731's model-spend ceiling was US$0.50; Render job compute is excluded. "
    "0731 ran on Render and Jev locally, at different times and cache/load conditions. These durations are observations, not a controlled speed benchmark. "
    "This comparison requests 0731's probability text; it does not establish cost against compact labels-only output.", "",
    "## Extraction and operational boundary", "",
    "No model generated arbitrary entity names, handles/domains, supporting quotations, translations or commentary. "
    "A separate extractor's quality, cost, ordering and consistency with labels remain untested. "
    "Jev and 0731 both still needed to reason about the promoted offering from the supplied evidence; no oracle target was supplied.", "",
    "No production model switch, application/configuration change, database access/write, X retrieval, scheduler resume or deployment. "
    "This comparison supplies evidence for a model choice, not a verified production integration or permission to reclassify stored posts.", "",
    "## Audit and evidence", "",
    "Frozen input/reference/helper/app hashes verified; every request's source/question parity, start/response identity, field count and cost reconciled. "
    "Zero model retries. Offline parser fixtures and a fake-transport end-to-end test passed before inference. "
    "Lossless LZMA replaced only the transport compression before submission to keep the job command below the operating-system argument limit; "
    "decompressed packet hashes and all model payloads are unchanged.", "",
    "- [Frozen contract](contract.md), [manifest](frozen.json), [transport manifest](transport-frozen.json).",
    "- [Exact 0731 requests](requests.json), [scores/probabilities](scores.json), [all disagreements](disagreements.json).",
    "- [Paired model decisions](model-pairs.json), [per-case review](case-results.md).",
    "- [Job receipt](job.json), [service preflight](render-preflight.json); raw captured responses in `events/`, original Render logs in `log-pages/`.",
    "- [Unchanged Jev report](../2026-09-30-070427-jev-multilingual-classification/report.md), [pre-inference references](../2026-09-30-070427-jev-multilingual-classification/reference_rows.json).",
    "- [Consolidated findings record](../2026-09-30-160557-jev-classification-findings.md).", ""]
with (HERE / "report.md").open("x") as stream:
    stream.write("\n".join(lines))

case_lines = ["# Paired case results: 0731 and Jev", "",
    "Frozen single-agent references, not independent human ground truth. Full source text/translation is linked for review. "
    "Every 0731 mismatch and every strict model-score difference is retained below; unchanged shared correct fields are omitted.", ""]
jev_rows = {(r["request_id"], r["field"]): r for r in j["rows"]}
for case_id in refs:
    c = cohort[case_id]
    case_lines += [f'## {case_id} — {c["target_brand"]} — {c["stratum"]}', "",
        f'[Source](https://x.com/{c["author_handle"]}/status/{c["post_id"]}); '
        f'[verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-{c["language"]}.md).', "",
        "Frozen rationale: " + refs[case_id]["note"], ""]
    part = [r for r in s["rows"] if r["case_id"] == case_id]
    case_lines += table(["Arm", "Jev matching fields", "0731 matching fields", "0731 invalid"], [
        [arm, sum(jev_rows[(r["request_id"], r["field"])]["correct"] for r in part if r["arm"] == arm),
         sum(r["correct"] for r in part if r["arm"] == arm), sum(not r["valid"] for r in part if r["arm"] == arm)]
        for arm in ("raw", "translated") if any(r["arm"] == arm for r in part)])
    rows = []
    for r in part:
        old = jev_rows[(r["request_id"], r["field"])]
        if r["correct"] and old["correct"]:
            continue
        rows.append([r["arm"], r["field"], r["expected"], old["assigned"], r["assigned"],
            pct(r.get("selected_probability")), "yes" if r["valid"] else "NO"])
    case_lines += table(["Arm", "Field", "Reference", "Jev", "0731", "0731 selected probability", "0731 valid"], rows)
with (HERE / "case-results.md").open("x") as stream:
    stream.write("\n".join(case_lines))
print(json.dumps({"report": str(HERE / "report.md"), "raw_model_pairs": counts, "usage": s["usage"]}))
