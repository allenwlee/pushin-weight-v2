# U18A label-owner regression cohort

## Scope and provenance

This is a bounded source-visible review for the quality sweep, not human gold or a population accuracy estimate. It fixes an expected owner for each label in seven observed rows and three synthetic controls. No X/TwitterAPI, classifier, translator, or other paid provider call was made for this review. No database row was changed.

The observed rows came from read-only queries to Render database service `dpg-d9koekqjobas73fvjqng-a`, named `pushinweight-db-shadow`, whose database reports `current_database() = pushinweight_shadow`. `render postgres list` verified that identity on 2026-09-28. A separate read-only Render web-shell check confirmed the production web service's `DATABASE_URL` host/database resolves to this same service and database. These are current production-database observations. Every data query ran inside `BEGIN READ ONLY` and `COMMIT`.

The companion [fixture](../../tests/fixtures/u18a_label_owner_regressions_v1.json) holds source-visible text or excerpts and exact evidence phrases. The [repair manifest](2026-09-28-023934-u18a-label-owner-repair-manifest.json) freezes the five selected rows' 64-character input-context fingerprints, exact brand sets, complete canonical Stage 1 judgments, post-level promotions, promoted subjects, and selected content/brand/merge revision triplet. The manifest is an expected-result gate; it is not an instruction to edit one post-type edge. Any candidate disagreement on any field stops that row's repair for review, with no ad hoc override.

## Observed ownership error

| Post | Visible subject and role | Tracked brand | Current advertising | Reviewed target | Repair? |
| --- | --- | --- | --- | --- | --- |
| `2101798119298277764` | Token Machine daily spin; Qwen tokens are a prize | Qwen | Yes | Qwen `other`; Token Machine `general` promotion | Yes |
| `2101837112115093617` | Token Machine/$MACHINE crypto pitch; many models listed as possible prizes | DeepSeek, Llama, Qwen | No | Each tracked brand `other`; Token Machine `crypto` promotion | No, boundary |
| `2101887098726821978` | Token Machine daily spin; no Hunyuan prize won | Hunyuan | No | Hunyuan `other`; Token Machine `general` promotion | No, boundary |
| `2102033817418748243` | Token Machine daily spin; Hunyuan tokens are a prize | Hunyuan | Yes | Hunyuan `other`; Token Machine `general` promotion | Yes |
| `2103615895600017738` | Token Machine daily spin; Hunyuan tokens are a prize | Hunyuan | Yes | Hunyuan `other`; Token Machine `general` promotion | Yes |
| `2104375726627790944` | Token Machine daily spin; DeepSeek tokens are a prize | DeepSeek | Yes | DeepSeek `other`; Token Machine `general` promotion | Yes |
| `2104483144233853085` | B.AI platform guide campaign by author `xxyweb3`; GLM is a highlighted model inside it | Zhipu/`glm` | Yes | GLM `opinions_reactions`; B.AI `general` promotion | Yes |

Four of the five short Token Machine spin posts in this observed set currently transfer `advertising_marketing` to the prize brand; the long crypto list is a separate boundary. These are counts in this selected group, not a rate for all posts.

The GLM post's source visibly praises GLM-5.3-Flash as a standout feature, so its positive sentiment and `testimonial` label remain in the reviewed judgment. The call to visit a guide, the cost-savings claims, and the guide's API/deployment description promote the platform, so the reviewed GLM judgment removes `advertising_marketing`, `cost_performance`, and `api_developer_surface`. The resulting tracked post type is `opinions_reactions`. The source ends with `@BAI_AGI`; the B.AI name is also supplied by the owner. The shortened platform URL was not resolved in this review, so the subject's domain is left null. `xxyweb3` is the post author, not the promoted subject.

For the Hunyuan win on `2102033817418748243`, the current `opportunities` type describes the Token Machine prize chance, not a Hunyuan offer. For the DeepSeek win on `2104375726627790944`, winning tokens does not itself express positive sentiment toward DeepSeek. The manifest therefore removes those transferred judgments as well as advertising. Other fields are source-reviewed in full; the complete expected rows are in the manifest.

## Positive controls

Three clearly synthetic examples protect legitimate behavior: a direct official DeepSeek API pitch, a direct official Zhipu/GLM API pitch, and a post that independently calls readers to use DeepSeek and join Token Machine. The first two retain tracked-brand `advertising_marketing`; the third retains both tracked-brand advertising and post-level Token Machine promotion. These are contract controls, not sampled live posts.

## Translation and repair prerequisites

All five exact repair IDs had one current `succeeded` literal translation artifact in the read-only snapshot, with nonempty `en`, `ja`, and `zh-cn` text and a completion timestamp. The artifacts' IDs were `955`, `4306`, `18910`, `24670`, and `25450` in manifest order. Two artifacts reported source languages `other` and `tl`; their three text rows have no `is_source` flag, but all required translated locales are present. A repair command must still independently recheck current artifact, source fingerprint, brand set, prompt lineage, leases, and exact full candidate result immediately before publication.

## Read-only evidence queries

The review used these query shapes against the verified Render database service, each wrapped in `BEGIN READ ONLY; ...; COMMIT;`:

```sql
SELECT p.tweet_id, p.author_handle, p.author_id, p.text, p.quoted_text
FROM posts p
WHERE p.tweet_id IN (<the seven exact observed IDs>);

SELECT s.post_id, s.brand_id, s.input_context_fingerprint,
       s.prompt_version, s.model, j.canonical_judgment
FROM posts_brands_classification_states s
LEFT JOIN posts_brands_classification_judgments j
  ON j.id = s.selected_final_judgment_id
WHERE s.post_id IN (<the five exact repair IDs>);

SELECT a.post_id, a.state, a.is_current, a.completed_at,
       string_agg(t.locale, ',' ORDER BY t.locale) AS locales,
       bool_and(length(t.text) > 0) AS all_nonempty
FROM post_translation_artifacts a
JOIN post_translation_texts t ON t.artifact_id = a.id
WHERE a.post_id IN (<the five exact repair IDs>)
  AND a.is_current AND a.state = 'succeeded'
GROUP BY a.post_id, a.state, a.is_current, a.completed_at;
```

The current production-database selected finals all use `stage1-two-role-merge-0731-v5` and `deepseek-ai/DeepSeek-V4-Flash-0731`. Their post-level promotion rows already carry `general` for each repair ID. The fixture's source text normalizes line breaks for readability; the manifest fingerprint is copied from the selected final state, not recomputed from the fixture text.
