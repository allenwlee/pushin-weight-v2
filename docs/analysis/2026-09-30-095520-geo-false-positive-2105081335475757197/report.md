# Geo false positive: @PreciousBa82157 / 2105081335475757197

Status: diagnosed at stored-classification level; no fix or data correction applied.
Observed: 2026-09-30T00:53:47.495954+00:00.
Source: [X post](https://x.com/PreciousBa82157/status/2105081335475757197), read from production storage.

## Debug summary

**Problem:** A company-focused criticism/comparison received `nationalism`, `China: pro`, and `US: anti` for GLM. Neither the stored post nor its saved quote expresses a national judgment.

**Root cause:** The brand-interpretation result already contains the unsupported national labels. The likely semantic mistake is transferring the author's negative evaluation of Anthropic/OpenAI into hostility toward the US, and the favorable contrast with GLM into support for China. That inferred motivation is not a recorded model explanation. The confirmed failure boundary is the brand-interpretation judgment; subsequent structural validation, merge, persistence and dashboard projection preserve its values.

**Recommended verification if a fix is later authorized:** Keep this exact source and quote as a negative geopolitical example. Pair it with a positive example that actually evaluates national origin/systems, so a fix does not simply disable geopolitics. Existing runtime and persistence tests own the transport/publication path; their fake responses cannot prove the model understands this boundary. No tests, model evaluations or prompt changes were run for this diagnosis.

**Fix:** Diagnosis only.

**Prevention gap:** Geo output requires no supporting passage. Stored geo `evidence` repeats axis, value and input fingerprint, rather than establishing why the national classification is supported. Current checks verify allowed values and consistency, not semantic grounding in source text.

**Confidence:** High that this is an upstream classification false positive, not an invented display tag. Medium on the particular mental shortcut the model took; no rationale or raw batch response was retained in the inspected records.

## Source meaning and expected result

The author condemns Anthropic's behavior, groups OpenAI with it in a hacking allegation, and contrasts those companies with GLM 5.3. The saved @attrc quote asks why Anthropic wrote a blog advertising a switch to GLM for cybersecurity teams.

The criticism is directed at companies and conduct. There is no China/US comparison, national-group evaluation, national-policy argument, or judgment based on vendor nationality in either text. 'All around the globe' and criticism of corporate monopoly do not establish national sentiment.

Expected model output on the geo axes:

```json
{
  "geopolitical_modes": ["none"],
  "china_national_stance": "none",
  "us_national_stance": "none"
}
```

The storage parser normalizes `["none"]` into an empty mode list with `geopolitical_modes_state="none"`; it is not an unavailable/pending judgment. Other classifications, including testimonial/sentiment, were not comprehensively adjudicated in this geo-only investigation.

## Observed records

Only brand `glm` has a current classification for this post.

| Stage | Judgment ID | Prompt version | Relevant result |
| --- | ---: | --- | --- |
| Content | 124093 | stage1-content-0731-v6 | opinions_reactions; openness_license |
| Brand interpretation | 124094 | stage1-brand-interpretation-0731-v5 | nationalism; China pro; US anti; positive sentiment; testimonial |
| Final | 124095 | stage1-two-role-merge-0731-v6 | Same geo/stance values as brand interpretation |

All three judgments share revision `794af3c4e3d1e504c0d688d7f2e0a85ef71d2e8de3d7d9b87f578000b428a8bd` and input fingerprint `bee6c1329acd901410e8a5e8937f244cbf81eccce8923a2466d71a580237b110`. The current state selects final judgment 124095; the geopolitical edge points to the same judgment and stores only `nationalism`.

Model: `deepseek-ai/DeepSeek-V4-Flash-0731`. Taxonomy: `stage1-taxonomy-v4`. Classified at 2026-09-29T23:49:39.759479Z, or September 30 08:49:39 JST. This is versioned current state, not inferred classification-era history.

## Code trace

Inspected against `origin/main` at `86fdda2` and the existing analysis worktree at `1edbc3a`. Existing local changes restore the content advertising definition and content/merge revision selection; the relevant brand prompt, geo validation and persistence are unchanged. The historical deployed SHA and complete request packet are not retained in these judgment rows.

1. `monitor/cycle.py:3724` constructs the classifier's source packet from the original text, stored quote, local reply parent if any, translation and reviewed affiliations. This post is not a reply; its saved quote is available. A linked article's unseen content is not fetched into this packet.
2. `x_monitor/attribution.py:3743` builds fixed decision slots and passes source/context plus a tracked-brand identity catalog. There is no explicit country/account-geography field in that payload. Catalog identity and the model's general knowledge are not evidence of the author's national stance.
3. `x_monitor/classifier_0731_prompts.py:56` defines nationalism and explicitly states: “Mere nationality, country name, flag, vendor origin, historical analogy, ordinary product praise, or ordinary product criticism is insufficient.”
4. `x_monitor/attribution.py:3986` validates brand-interpretation values. National stances must use recognized enum values; directional stances require nationalism. There is no source-text evidence requirement for these fields.
5. `x_monitor/attribution.py:4383` combines the disjoint content and brand interpretations. For a classified result like this, it copies the brand interpretation rather than running a semantic reviewer. `core/classification_contract.py:273` checks and normalizes the complete result without evaluating its source meaning.
6. `monitor/cycle.py:1521` persists the national stances. `monitor/classification_persistence.py:451` persists each geo mode with axis/value/fingerprint as its evidence.
7. The dashboard reads stored geopolitical edges and current stance fields (`monitor/views.py:2497` locally, `2510` in the inspected main revision), and `monitor/static/pw-feed.js:829` in main renders the supplied modes. A browser session was not inspected, but the unwanted values already exist upstream of presentation.

## Competing explanations checked

- **Display-only invention or stale legacy fallback:** does not explain this case; selected final judgment, current v4 state and current geo edge all agree on the unwanted values.
- **Saved quote supplies geopolitical context:** unsupported by the stored quote, which discusses Anthropic, GLM and cybersecurity teams without national framing.
- **Automatic nationalism completion creates the entire label:** the normalization branch at `x_monitor/attribution.py:3892` only appends nationalism to an existing nonempty mode list and preserves those prior modes. It does not replace `none` or `unavailable`. This record's sole `["nationalism"]` mode therefore is not explained by that append-only branch.
- **Local experiment rollback caused a live result:** these are uncommitted local content-prompt changes, not the production brand-interpretation prompt. The stored brand prompt remains v5. The local dirty worktree was not stashed or modified for this investigation.
- **Exact model reasoning or raw slot/batch assignment:** not reconstructible from canonical judgment records alone. The vendor-nationality shortcut is a well-supported interpretation of the output, not direct access to model reasoning. No new model call was made to invent a retrospective explanation.

Targeted GitHub searches for geopolitical issues and nationalism pull requests returned no results; this is a narrow search, not proof that no related work exists.

## Scope and next decision

No production records, labels, code, prompts, services or schedules changed. One read-only production query; zero classifier/model calls and zero tests.

The next design question is how to require source-grounded national interpretation without a crude country-keyword filter. The intended boundary is already in the prompt, so merely adding a longer restatement has not been established as a fix. Supporting evidence could improve auditability, but extracting a quote alone would not prove semantic correctness.

Existing tests to extend only if implementation is requested: `tests/test_u18_runtime_0731.py` for the real caller/response-validation boundary, `tests/test_u18a_v4_classification_persistence.py` for publication, and the existing semantic evaluation fixtures for this negative example. Fake-client tests can verify guards and propagation, not claim improved model judgment. The owner's stop on further model tests remains in force.

## Evidence files

- [Exact read-only SQL](inspection.sql)
- [Render response](render-result.json)
- [Parsed observation](observation.json)
- [Request and limitations](request.json)

