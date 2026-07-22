"""U7 + U1 + U2: smoketest runner — hierarchical multi-discourse / unsanctioned / URL / discourse-field-source.

Plans:
- docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md (U7)
- docs/plans/2026-07-04-001-feat-post-fetch-smoketest-and-prompt-tuning-plan.md (U1, U2)
- docs/plans/2026-07-06-001-feat-remove-trans_disc-plan.md (post-grace:
  discourse_role is classifier-only; trans_disc: is removed)
- smoketest skill (pushin_weight_smoketest 2026-07-06):
  hierarchical layout — post-level fields under `post:`, per-brand
  fields under `brand_mentions:` with the brand name as a bare
  section header.

Verifies:
- `_render_sample_posts` handles multi-value `post_types[]` /
  `discourse_roles[]` arrays by rendering nested bullets, not
  flattening or expanding to a cartesian product.
- `_render_sample_posts` surfaces unsanctioned flags per post when
  present.
- U1-final (2026-07-06): translator no longer emits `discourse_role`;
  the report has NO `trans_disc:` line. Per-brand `cls_discourse=` is
  the only discourse field — emitted when `cls.discourse_roles` or
  legacy `cls.discourse_role` is present, omitted entirely (not a
  placeholder) when absent.
- smoketest skill (pushin_weight_smoketest 2026-07-06): the report
  groups post-level tags under `post:` (types + annotation) and
  per-brand tags under `brand_mentions:` (post_types, sentiment,
  cls_discourse, cn, us).
- U2: each post header includes the full X / Twitter URL.
- Backwards compat: legacy scalar `cls.discourse_role` still renders
  as a single-element `cls_discourse=`.
"""

from __future__ import annotations

from scripts.post_fetch_smoketest import _render_sample_posts


def test_u7_renders_one_block_per_brand_with_scalar_fields():
    """Legacy shape: scalar `post_type` + scalar `cls.discourse_role`.

    U2: header includes URL. Plan 2026-07-06-001 removed the
    translator's `trans_disc:` field — pragmatic register is the
    classifier's exclusive output (`cls_discourse=` per brand).

    smoketest skill (pushin_weight_smoketest 2026-07-06):
    hierarchical layout — post-level tags under `post:`, per-brand
    tags under `brand_mentions:`.
    """
    sample = [
        {"tweet_id": "111", "id": "111", "text": "GLM 5.2 真棒",
         "author_handle": "testuser"},
    ]
    trans = [
        {"tweet_id": "111", "text_en": None, "text_zh_cn": "GLM 5.2 真棒",
         "literal_zh": "GLM 5.2 真棒",
         "cn_equivalent": "GLM 5.2 真棒", "annotation": "(none)"},
    ]
    class_rows = {
        "111": [
            {"brand_id": "glm", "post_type": "hands_on_usage",
             "sentiment": "positive", "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    assert "post:" in out
    assert "\n  types=hands_on_usage" in out
    assert "\n  annotation=(none)" in out
    assert "\nbrand_mentions:" in out
    # Brand section header is bare (NOT inside `[]`).
    assert "\n  glm\n" in out
    # Legacy scalar post_type uses the `post_types=` shorthand.
    assert "    post_types=hands_on_usage" in out
    # Per-brand sentiment / cls_discourse / cn / us each on its own line.
    assert "    sentiment=positive" in out
    assert "    cls_discourse=genuine_hype" in out
    assert "    cn=none" in out
    assert "    us=none" in out


def test_u7_renders_post_types_bullet_list_when_array():
    """post_types[] array → nested bullets under the brand block."""
    sample = [{"tweet_id": "222", "id": "222", "text": "GLM vs Kimi?"}]
    trans = [{"tweet_id": "222", "literal_zh": "GLM vs Kimi?"}]
    class_rows = {
        "222": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons", "feedback_questions"],
             "sentiment": "neutral",
             "discourse_role": "self_deprecation",
             "china_nationalism": "mild_pro", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    assert "    post_types:\n" in out
    assert "      - performance_comparisons\n" in out
    assert "      - feedback_questions\n" in out
    # Legacy single scalar cls.discourse_role still maps to cls_discourse=.
    assert "    cls_discourse=self_deprecation" in out
    # post: types= lists both at the post level (unique-set).
    assert "\n  types=performance_comparisons,feedback_questions\n" in out


def test_u7_renders_discourse_roles_bullet_list_when_many():
    """Multi-element `discourse_roles[]` array → nested bullets;
    `cls_discourse=` line is omitted in the multi-bullet case."""
    sample = [{"tweet_id": "333", "id": "333", "text": "GLM is great"}]
    trans = [{"tweet_id": "333", "literal_zh": "GLM 太棒了"}]
    class_rows = {
        "333": [
            {"brand_id": "glm",
             "post_types": ["hands_on_usage"],
             "sentiment": "positive",
             "discourse_roles": ["genuine_hype", "advertising-marketing"],
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    assert "    discourse_roles:\n" in out
    assert "      - genuine_hype\n" in out
    assert "      - advertising-marketing\n" in out
    # The `cls_discourse=` line is NOT rendered when discourse_roles
    # has multiple elements (the bullet list is the source of truth).
    assert "    cls_discourse=" not in out


def test_u7_renders_single_element_discourse_role_inline():
    """Single-element `discourse_roles[]` array → `cls_discourse=`
    on its own line (not a bullet list)."""
    sample = [{"tweet_id": "344", "id": "344", "text": "GLM is great"}]
    trans = [{"tweet_id": "344", "literal_zh": "GLM 太棒了"}]
    class_rows = {
        "344": [
            {"brand_id": "glm",
             "post_types": ["hands_on_usage"],
             "sentiment": "positive",
             "discourse_roles": ["genuine_hype"],
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    assert "    cls_discourse=genuine_hype" in out
    # No bullet list when only one role.
    assert "    discourse_roles:\n" not in out


def test_u7_renders_one_block_per_brand_when_array():
    """post_types array + single-element discourse_role: exactly
    one brand block (no cartesian expansion)."""
    sample = [{"tweet_id": "444", "id": "444", "text": "complex post"}]
    trans = [{"tweet_id": "444", "literal_zh": "复杂 post"}]
    class_rows = {
        "444": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons", "feedback_questions"],
             "sentiment": "mixed",
             "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    # One header.
    assert out.count("\n  glm\n") == 1


def test_u7_surfaces_unsanctioned_flags_for_post():
    """When a post has unsanctioned flags, render them in the output."""
    sample = [{"tweet_id": "555", "id": "555", "text": "$GLM $NUSD scam"}]
    trans = [{"tweet_id": "555", "literal_zh": "假"}]
    class_rows = {}  # no classifications
    flags = {"555": ["marketing_spam", "crypto", "unauthorized"]}
    out = _render_sample_posts(sample, trans, class_rows, flags)
    assert "unsanctioned:" in out
    assert "marketing_spam" in out
    assert "crypto" in out
    assert "unauthorized" in out


def test_u7_no_unsanctioned_line_when_empty():
    """When a post has no unsanctioned flags, no 'unsanctioned:' line."""
    sample = [{"tweet_id": "666", "id": "666", "text": "normal post"}]
    trans = [{"tweet_id": "666", "literal_zh": "normal"}]
    class_rows = {}
    out = _render_sample_posts(sample, trans, class_rows)
    assert "unsanctioned:" not in out


def test_u7_trans_disc_field_removed_from_render():
    """Plan 2026-07-06-001: translator no longer emits discourse_role,
    so the report has NO `trans_disc:` line at all. The translator
    field is silently absent regardless of input shape (no default
    placeholder, no `(none)`, nothing)."""
    sample = [{"tweet_id": "777", "id": "777", "text": "test"}]
    trans = [{
        "tweet_id": "777",
        "literal_zh": "test",
        "discourse_role": ["genuine_hype", "advertising-marketing"],
    }]
    out = _render_sample_posts(sample, trans, {})
    assert "trans_disc:" not in out, (
        f"trans_disc: must NOT be rendered; classifier is the sole "
        f"discourse source. Got:\n{out}"
    )


def test_u7_empty_discourse_role_also_removed():
    """Empty `discourse_role` array on translator dict → no
    `trans_disc: uncategorized` placeholder either. The field is gone."""
    sample = [{"tweet_id": "888", "id": "888", "text": "test"}]
    trans = [{"tweet_id": "888", "literal_zh": "test",
              "discourse_role": []}]
    out = _render_sample_posts(sample, trans, {})
    assert "trans_disc:" not in out


def test_u7_legacy_scalar_discourse_ignored():
    """Legacy scalar `discourse_role` on the translator dict is
    ignored — the renderer no longer reads `tr.discourse_role`
    at all (post-grace)."""
    sample = [{"tweet_id": "999", "id": "999", "text": "test"}]
    trans = [{"tweet_id": "999", "literal_zh": "test",
              "discourse_role": "genuine_hype"}]
    out = _render_sample_posts(sample, trans, {})
    assert "trans_disc:" not in out
    assert "discourse:  genuine_hype" not in out  # legacy single-word label also gone


def test_u7_multiple_brands_render_separately():
    """Two brands each with arrays → both render their own blocks.
    Multi-element post_types / discourse_roles render as bullets."""
    sample = [{"tweet_id": "aa1", "id": "aa1", "text": "GLM + Kimi"}]
    trans = [{"tweet_id": "aa1", "literal_zh": "GLM + Kimi"}]
    class_rows = {
        "aa1": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons"],
             "sentiment": "positive",
             "discourse_roles": ["genuine_hype"],
             "china_nationalism": "none", "us_nationalism": "none"},
            {"brand_id": "moonshot_kimi",
             "post_types": ["performance_comparisons"],
             "sentiment": "mixed",
             "discourse_roles": ["self_deprecation"],
             "china_nationalism": "mild_pro", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    # Each brand appears once as a bare section header.
    assert out.count("\n  glm\n") == 1
    assert out.count("\n  moonshot_kimi\n") == 1
    assert "    cls_discourse=genuine_hype" in out
    assert "    cls_discourse=self_deprecation" in out


def test_u7_no_classifications_renders_brand_mentions_none():
    """When a post has classifications=[] (e.g. no detected brand),
    `post:` keeps types=(none) and `brand_mentions: (none)`."""
    sample = [{"tweet_id": "bb1", "id": "bb1", "text": "lonely post"}]
    trans = [{"tweet_id": "bb1", "literal_zh": "孤单 post"}]
    out = _render_sample_posts(sample, trans, {})
    assert "post:" in out
    assert "  types=(none)" in out
    assert "brand_mentions: (none)" in out


def test_u1_post_level_header_drops_trans_disc_after_grace():
    """Plan 2026-07-06-001: the previous U1 rename (`discourse:` →
    `trans_disc:`) is now obsolete because the translator no longer
    emits `discourse_role` at all. The renderer has no post-level
    discourse field; per-brand `cls_discourse=` is the sole source."""
    sample = [{"tweet_id": "100", "id": "100", "text": "hello"}]
    trans = [{"tweet_id": "100", "literal_zh": "你好",
              "discourse_role": "genuine_hype"}]
    out = _render_sample_posts(sample, trans, {})
    # No post-level discourse line at all (not `trans_disc:`, not
    # `discourse:`, not `(none)` placeholder).
    assert "trans_disc:" not in out
    assert "\ndiscourse:" not in ("\n" + out)


def test_u1_per_brand_cls_discourse_emitted_when_in_payload():
    """cls_discourse= comes from `cls.discourse_roles` when present."""
    sample = [{"tweet_id": "200", "id": "200", "text": "t"}]
    trans = [{"tweet_id": "200", "literal_zh": "t"}]
    class_rows = {
        "200": [
            {"brand_id": "kimi",
             "post_types": ["hands_on_usage"],
             "sentiment": "positive",
             "discourse_roles": ["genuine_hype"],
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    assert "    cls_discourse=genuine_hype" in out


def test_u1_per_brand_cls_discourse_omitted_when_absent():
    """U1: when discourse_roles is absent, the cls_discourse= field is
    omitted entirely — NOT emitted as a placeholder
    `cls_discourse=uncategorized`.
    """
    sample = [{"tweet_id": "300", "id": "300", "text": "t"}]
    trans = [{"tweet_id": "300", "literal_zh": "t"}]
    class_rows = {
        "300": [
            # No `discourse_roles` key, no `discourse_role` legacy key.
            {"brand_id": "kimi",
             "post_types": ["hands_on_usage"],
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    # Brand block exists (cn/us are always emitted).
    assert "\n  kimi\n" in out
    assert "    cn=none" in out
    assert "    us=none" in out
    # No cls_discourse= line when payload lacks the field.
    assert "    cls_discourse=" not in out


def test_u1_per_brand_legacy_discourse_role_still_emits_cls_discourse():
    """Backwards compat: legacy scalar `discourse_role` on the class
    row is wrapped into a single-element `cls_discourse=`.
    """
    sample = [{"tweet_id": "400", "id": "400", "text": "t"}]
    trans = [{"tweet_id": "400", "literal_zh": "t"}]
    class_rows = {
        "400": [
            {"brand_id": "kimi",
             "post_types": ["hands_on_usage"],
             "sentiment": "positive",
             "discourse_role": "genuine_hype",  # legacy scalar
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    assert "    cls_discourse=genuine_hype" in out


# --- U2: full X / Twitter URL in post header -----------------------------


def test_u2_renders_url_when_author_handle_present():
    """U2: URL included in the post header."""
    sample = [{"tweet_id": "abc123", "id": "abc123", "text": "x",
               "author_handle": "adlenesifi"}]
    trans = [{"tweet_id": "abc123", "literal_zh": "x"}]
    out = _render_sample_posts(sample, trans, {})
    assert "url=https://x.com/adlenesifi/status/abc123" in out


def test_u2_renders_no_handle_fallback_when_missing():
    """U2: empty/None author_handle → `(no handle)` so the URL slot
    is unambiguous.
    """
    sample = [{"tweet_id": "xyz", "id": "xyz", "text": "x",
               "author_handle": None}]
    trans = [{"tweet_id": "xyz", "literal_zh": "x"}]
    out = _render_sample_posts(sample, trans, {})
    assert "url=https://x.com/(no handle)/status/xyz" in out


def test_u2_renders_no_handle_fallback_when_empty_string():
    """U2: empty-string author_handle → `(no handle)` (Postgres NULL
    vs empty string both treated as missing).
    """
    sample = [{"tweet_id": "xyz", "id": "xyz", "text": "x",
               "author_handle": ""}]
    trans = [{"tweet_id": "xyz", "literal_zh": "x"}]
    out = _render_sample_posts(sample, trans, {})
    assert "url=https://x.com/(no handle)/status/xyz" in out
