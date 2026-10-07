# G2 context retrieval and source attribution

Local implementation on `feat/g2-editorial`, base `bacbb433`; changes remain
uncommitted. No model call, X collection, staging/production mutation or deployment
in this continuation. Earlier three live iterations remain distinct and their
numeric-ownership quality failure is not declared resolved here.

The existing [G2 plan](../plans/2026-09-30-051835-docs-g2-voices-corpus-plan.md)
now incorporates the useful additions from the [cloned-session design](../brainstorms/2026-10-07-141532-g2-story-evidence-collector-design.md)
in U3/U4/U6/U8. One collector serves automatic and manual anchors, keeps selected
anchors separate from retrieved context and actual cited support, and freezes
writer evidence across tracks/locales. Unlinked official-team teaser nomination
remains planned: current implementation follows explicit parent/quote links and
source names, without assuming that same-team posts concern the same release.
The GLM five-day delay remains an unverified owner-supplied example.

## Limits and database shape

- Discovery evidence: **240,000 UTF-8 bytes**, formerly 120,000; preserve a quarter
  of that allowance for background while trimming complete rows.
- Selected-story evidence: **96,000 bytes**, anchors plus at most **24** context
  posts, at most **180 days** back. Preserve up to eight historical slots when
  eligible history exists. Each search returns at most 80 candidates; expanded
  lookup samples eight per month. Each statement has a 1,500ms timeout.
- One expansion round, at most two new names/phrases. Keep exact bridge post,
  source field, offsets, wording and nearby anchor terms. No hardcoded Mistral
  or Chaton query. Common brand names alone are not story links. Version conflicts,
  explicit token-address promotions and duplicate content are filtered.
- Schema cap: **120,000 bytes**; total serialized request cap **390,000 bytes**.
  All request bytes still enter pre-send cost reservation.
- No new table or column. Edition JSON saves `attribution.post_count` and all
  `attribution.posts` IDs/URLs, plus `cited_post_ids`, source checks and context
  receipt. Reader/API exposes exact `source_count` and links. Anchors remain
  `post_ids` for unchanged-story compatibility.
- Migration `0069_editorial_context_search` creates one concurrent multicolumn
  GIN index on uppercase original and quoted text using pg_trgm. The extension
  is retained on rollback because it may be shared. Applied only to disposable
  local test databases; staging and production are unchanged.

## Seven local implementation passes

A pass groups a substantive code revision and its verification; this is not a
count of individual shell/test invocations. The prior live loop stays at three
iterations/five model calls in its own report.

| Pass | Major change and observed failure/fix |
| --- | --- |
| 1 | Increased/protected evidence capacity; added selected-story recall and exact citation attribution. First suite: 92 passed, one failure from a nonnumeric fixture X ID; replaced it with a valid-shaped ID. Missing real source URLs still block publication. |
| 2 | Measured staging lookup: raw regex/name search timed out and generic brands/URL fragments admitted unrelated roundups. Excluded those seeds, bounded database time, and prepared a search index. The index expression's mixed Django field types caused test setup errors; corrected the expression. |
| 3 | Integrated Chonk bridge expansion, missing manual anchors and direct teaser links. Added old-version rejection and fixed the Chinese plural header exposed by the browser test. Eight targeted checks passed. Browser setup initially needed the proxy HTTPS header for the actual local route. |
| 4 | Froze shared evidence across tracks, separated cited support from candidates, and added a complete provider-to-edition attribution test. Full suite: 115 passed, one fixture failure because the fake provider cited only its first source. Corrected it to emit both intended source checks. |
| 5 | Full 116-test suite passed. Indexed replay revealed that a uniform all-long synthetic corpus led PostgreSQL to prefer a sequential scan despite a valid index. Added query-plan diagnostics and made the index/query use original/quoted fields directly. |
| 6 | A mixed-length background corpus showed normal index use and fast real-source recall. This is a local planning/performance observation, not production latency proof; the all-long synthetic planning limitation remains recorded. |
| 7 | Inspected retained real posts, removed token-address promotions, normalized phrase edges (Meet/IS), and ranked original-post name evidence above repeated quoted announcements. The actual DeepChatBot backstory now reaches Mistral's writer input. Added regression pins; final 118-test suite and saved-source replay pass. |

## Verification

`tests/test_editorial_*.py`: **118 passed in 20.15s**, including **56 required
PostgreSQL tests**, zero skips/errors. Coverage includes months-old history,
cutoffs, tight byte caps, name/version collisions, source-grounded bridge phrases,
manual/automatic parity, direct unnamed teaser links, complete source attribution,
shared frozen writer input and existing budget/fence/no-resend checks. The actual
anonymous story route displays the source count and every URL in English, Chinese
and Japanese at a mobile viewport through Playwright. This attribution-only change
does not touch homepage controls, so the homepage assurance profile is not invoked.

A separate local replay migrated a disposable PostgreSQL database, loaded **99
saved real Ajax/Mistral posts plus 20,000 synthetic background posts**, and invoked
the same collector with manual anchors. It passed (one required PostgreSQL test).
Both search plans use `idx_posts_editorial_context` under normal planner settings.
The fixture uses a mixture of short and long background posts; it is not a copy
of production and does not establish production latency or scale capacity.

- **ajax**: 0.061s, 24 added context posts, 26,401 evidence bytes, no query timeout.
- **mistral**: 0.050s, 24 added context posts, 30,164 evidence bytes, no query timeout.

The Mistral replay discovers `le chaton fat` from source bridge text and includes
post `2107540640104141075` describing the fictional-model joke. It excludes the
identified token promotions. These saved Mistral posts report older meme history;
they are not a recovered June primary-source corpus. Multi-month retrieval is
separately exercised with dated 90/95/140-day fixtures.

Read-only staging reconstruction (without the new index) retained **128 recent
and 22 background posts**, compared with 105 recent/no background previously.
The packet was 237,724 bytes; editor schema 94,337 bytes; complete editor request
347,225 bytes. Historical queries on that unindexed database timed out, so no
claim of successful live-database context expansion is made. No provider was sent
this reconstructed request.

Ruff, `git diff --check`, and Django migration-drift check pass. Final commands and
machine-local receipts are in `.local/g2-context-verification-20261007/`:
`final-tests.txt`, `replay-tests.txt`, `indexed-replay.json`, `*-indexed-story.json`,
query plans, original read-only reconstruction and replay script. They contain no
credentials. The replay's source material comes from preserved earlier evidence.

## Images and remaining limits

An image evidence reference is a pointer tying a claim to a supplied source image
(post ID, image URL/identity, and delivery receipt), not a generated image caption.
Current source checks still bind text passages only; no image-claim reference
contract, OCR stage or new image-description call was added. Actual image delivery
and third-party image claims remain distinct from primary verification.

The initial keyword extractor targets Latin-script names/phrases, including those
inside Chinese/Japanese posts. Heuristic relevance is not a semantic truth check;
selected-story recall cannot recover a development the editor never selected.
No new headline was generated, and no fresh model-quality acceptance is claimed.
