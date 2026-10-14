---
name: senior-ed-read
description: Review a generated news story against its source packet as a senior editor. Fact-check claims, vet source ownership and fairness, and grade the headline, supporting line, body and local-language writing from A+ to F. Use for editorial trials and publication-readiness reviews.
---

# Senior editor read

Review the untouched draft as a managing editor would before publication. Be demanding about evidence and reader value while allowing lively, generous tabloid writing. A joke does not need to be in the source; the factual premise of the joke does. This skill defines a reusable review contract, not a production integration or permission to publish, retrieve more data, make paid calls, or rewrite the draft.

## Inputs and review identity

Read the complete headline, substantive supporting line (called `byline` in Chatter), and body, together with the actual source packet, source relationships, image evidence actually supplied, cutoff, and available original receipts. In a split version, inspect both the beatwriter ledger and copyeditor input. A model-generated ledger is an interpretation to check, not a replacement for original evidence.

Default to the supplied, closed evidence packet for both factual checking and source vetting. Do not retrieve outside story information or fill gaps from memory. Check available raw receipts and relationships within that packet; label unresolved claims and missing evidence. External verification belongs to a separately authorized review, must be recorded separately, and must never silently change a frozen test packet.

Record the draft ID and content hash, packet hash/cutoff, language, voice, writer/beatwriter models and settings, reviewer, review time, and this skill's hash. Preserve the first draft and exact request. Distinguish a confirmed defect from a missing source, unverifiable statement, or editorial preference. Review every result, including held/partial results; mark unavailable copy explicitly instead of inventing a grade for unwritten text.

## Grades

Use **A+, A, A−, B+, B, B−, C+, C, C−, D+, D, D−, F** for every applicable section and every substantive finding. Use ASCII minus in machine-readable records. An unavailable section has `grade: null` and an explicit reason, never an automatic A or F.

| Grade band | Meaning |
| --- | --- |
| A+ | Exceptional: accurate, clear, memorable and ready as written; reserve for standout work. |
| A / A− | Strong and ready; any suggested improvement is optional. |
| B+ / B / B− | Useful, with a specific edit needed; the premise and main facts hold. |
| C+ / C / C− | Substantial weaknesses; needs meaningful revision or a missing source resolved. |
| D+ / D / D− | Major defects undermine the section; extensive correction is needed. |
| F | Fundamentally false, misleading, unsupported, or unusable for the stated purpose. |

Use plus/minus for strength within a band. Explain every section grade, substantive finding grade and overall grade in **one or two sentences**, using concrete wording and evidence. Length, confident tone and successful JSON validation earn no credit by themselves. Do not force a ranking or spread. Give a separate overall editorial grade and publication verdict; a strong pun cannot cancel a material factual or fairness defect.

## 1. Source quality and provenance

Check who actually said each material thing, whether the source is first-party, a report, opinion, allegation, quoted post, reply, or supplied historical background. Verify source IDs/URLs, dates and relationships against available raw receipts. Different posts do not establish independent confirmation, and a URL is not proof its contents were read. Separate real photo pixels, reviewed transcription, source caption and invented visual interpretation. State coverage gaps and the exact verification performed. Grade source adequacy for this story, not the prestige of its author.

## 2. Factual fidelity and numbers

Map material assertions in headline, supporting line and body to source passages. Check identities, roles, model/version names, money, units, parameter counts, dates, rankings and comparison classes. Preserve total versus active parameters, open weights versus an open-source licence, API availability versus downloadable weights, and announcements versus completed actions. A price correction is the subject's claim unless independently established. Flag invented motives, reactions, consensus, causal links and background facts. Mechanical source-span/number checks are supporting evidence, not semantic fact-checking.

## 3. Attribution, uncertainty and time

Keep company claims and allegations owned in the supporting line and body. Allow playful shorthand in a headline when the ordinary reader will not mistake a disputed claim for established fact. Check that a historical source does not establish a current role or a new launch. Interpret “today,” “now” and promised availability against the packet cutoff. Separate the source's joke from a literal factual allegation; preserve relevant scope and qualifiers without making the article read like an evidence report.

## 4. Fairness and reputational risk

Read for unsupported wrongdoing, guilt, deception, cheapness, motives, hostile character judgments, fake quotes and exaggerated accusations. Distinguish a subject calling something “slander” from a legal finding. Consider the ordinary implication of the whole item, including headline and image. Humor should remain playful and generous to people; do not penalize harmless wordplay merely for being irreverent. Identify the exact problematic wording and why it changes the reader's understanding. This is an editorial risk review, not a legal determination. If a jurisdiction-specific legal question matters, flag it for separately authorized legal review rather than inventing a rule or retrieving outside information during a closed-packet test.

## 5. Context and news judgment

Can a reader unfamiliar with AI understand who the person/company is, what happened, why it is interesting, and what changed? Prefer sourced, economical context. Check whether the strongest real tension is clear, whether important facts disappeared during the beatwriter handoff, and whether source-checking notes leaked into the story. Do not demand unrelated background or imply that sparse evidence supports a large conclusion.

## 6. Headline

Grade factual premise and ordinary implication, punch, originality, economy, specificity to this story, and fit to the requested publication/language. Explain the joke when needed for evaluation, without treating an English pun as the target in another language. A technically true but lifeless label can receive a weak creative grade; a brilliant but misleading headline fails readiness. Record any alternative as an editorial suggestion, never silently replace the model's result.

## 7. Supporting line

Grade whether it adds a concrete development, explanation or implication rather than repeating the headline, listing sources or inventing an author. Check attribution, clarity and how well it resolves any playful shorthand above it.

## 8. Body

Grade the lead, organization, selection of facts, clarity, pace, length, voice and ending. Check every paragraph for factual support. Identify repetition, padding, awkward translations, bland recitation and internal checking prose. An article must inform readers; repeated “the packet does not establish…” disclaimers usually belong in the review, unless the actual evidentiary dispute is the news. Preserve useful uncertainty in natural reporting language.

## 9. Local-language voice and readability

Judge English, Japanese and simplified Chinese on their own conventions and the selected voice. Do not require NYPost-style English puns in ToSpo or WeMedia. Check natural wording, names/titles, register, unexplained English, local units/currency clarity and whether the text sounds written in that language. Separate demonstrable errors from a taste judgment. State when native-reader certification has not occurred; do not present the reviewing agent as a native panel.

## Findings, overall grade and verdict

For each numbered section provide `grade`, a one- or two-sentence `reason`, and findings with their own grade and one- or two-sentence reason, draft excerpt, source pointer (or explicit absence), verification status, severity, and suggested correction where needed. Keep factual blockers separate from creative preferences. Grade headline and body independently even if one is excellent and the other weak.

Use one verdict:

- **publish**: no unresolved material factual, source, attribution or fairness defect; remaining edits are optional.
- **revise**: evidence is adequate and identified copy edits can fix the item.
- **hold**: an unresolved material claim, missing evidence, misleading premise or unavailable draft prevents publication.

Do not average a material blocker away. Explain the overall grade as an editorial judgment, list required changes and remaining uncertainties, and identify any useful strengths. Publish here means “editorially ready,” not actual publication authority. In comparisons, apply the same rubric to each result and distinguish headline winner from whole-story winner.

## Durable review record

Save a record next to the run, using the existing artifact store rather than creating a database schema. Recommended shape:

```json
{
  "review_contract": "senior-ed-read/v1",
  "skill_sha256": "...",
  "draft_id": "...",
  "draft_sha256": "...",
  "packet_sha256": "...",
  "cutoff": "...",
  "locale": "ja",
  "voice": "...",
  "reviewer": "...",
  "reviewed_at": "...",
  "sections": {
    "sources": {"grade": "A-", "reason": "...", "findings": []},
    "facts": {"grade": "A-", "reason": "...", "findings": []},
    "attribution_time": {"grade": "A-", "reason": "...", "findings": []},
    "fairness": {"grade": "A-", "reason": "...", "findings": []},
    "context": {"grade": "B+", "reason": "...", "findings": []},
    "headline": {"grade": "B", "reason": "...", "findings": []},
    "supporting_line": {"grade": "A-", "reason": "...", "findings": []},
    "body": {"grade": "B+", "reason": "...", "findings": []},
    "local_voice": {"grade": "B+", "reason": "...", "findings": []}
  },
  "overall_grade": "B+",
  "overall_reason": "The facts are supported, but the headline repeats the supporting line. Give each line a distinct job before publication.",
  "verdict": "revise",
  "required_changes": [],
  "uncertainties": ["Native-reader certification not performed."],
  "strengths": []
}
```

Production integrations may use this record contract. Installing the skill alone does not activate a review step, validate an automated judge, or change the production writer.
