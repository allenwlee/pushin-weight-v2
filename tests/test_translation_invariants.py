from decimal import Decimal

import pytest

from x_monitor.translation_invariants import (
    extract_token_quantities,
    protect_token_quantities,
    quantity_instruction,
    quantity_placeholder_instruction,
    restore_token_quantities,
    validate_translation_quantities,
)

SOURCE = "The model trained on 10.9 trillion tokens."


def test_normalizes_equivalent_english_and_cjk_token_quantities():
    assert [item.value for item in extract_token_quantities(SOURCE)] == [Decimal(10900000000000)]
    assert [item.value for item in extract_token_quantities("模型使用10.9万亿 tokens训练。")] == [Decimal(10900000000000)]
    assert [item.value for item in extract_token_quantities("モデルは10兆9000億トークンで訓練された。")] == [Decimal(10900000000000)]
    assert [item.value for item in extract_token_quantities("10.9兆トークン")] == [Decimal(10900000000000)]


def test_accepts_localized_and_bilingual_repetitions_of_source_quantity():
    assert validate_translation_quantities(SOURCE, "模型使用10.9万亿 tokens训练（10.9 trillion tokens）。") == []
    assert validate_translation_quantities(SOURCE, "モデルは10兆9000億トークンで訓練された。") == []


def test_rejects_wrong_magnitude_even_when_correct_value_also_appears():
    errors = validate_translation_quantities(
        SOURCE,
        "模型使用10.9万亿 tokens训练，但错误地写成100億 tokens。",
    )

    assert len(errors) == 1
    assert "100億 tokens" in errors[0]
    assert "10000000000" in errors[0]
    assert "10900000000000" in errors[0]


def test_standard_cjk_compound_arithmetic_distinguishes_one_and_109_trillion():
    assert [item.value for item in extract_token_quantities("1万亿 tokens")] == [Decimal(1000000000000)]
    assert [item.value for item in extract_token_quantities("109万亿 tokens")] == [Decimal(109000000000000)]
    assert validate_translation_quantities("1 trillion tokens", "109万亿 tokens")
    assert validate_translation_quantities("109 trillion tokens", "109万亿 tokens") == []


def test_accepts_named_implicit_next_trillion_and_cjk_token_prefix():
    source = "The bigger opportunity is the next trillion tokens."
    assert [item.value for item in extract_token_quantities(source)] == [Decimal(1000000000000)]
    assert validate_translation_quantities(source, "より大きな機会は次の1兆トークンです。") == []
    assert validate_translation_quantities("10.9 trillion tokens", "10.9万亿个Token") == []


def test_saved_artifact_flags_only_its_wrong_100_oku_token_quantity():
    # Minimal excerpts from 2095737515894313379, kept inline so this regression
    # remains runnable without a machine-local experiment directory.
    source = "10.9 Trillion Tokens Later. More than 10.9 trillion tokens. The next trillion tokens."
    translated = "10.9兆トークンを処理した今。100億トークン以上。より大きな機会は次の1兆トークン。"
    errors = validate_translation_quantities(source, translated)

    assert len(errors) == 1
    assert "100億トークン" in errors[0]


def test_protected_quantity_uses_target_language_rendering_and_keeps_next_outside_marker():
    masked, replacements = protect_token_quantities(
        "The next trillion tokens follow 10.9 trillion tokens.", "ja"
    )
    assert masked == "The next [[PQ0:001]] follow [[PQ0:002]]."
    assert replacements == {"[[PQ0:001]]": "1兆トークン", "[[PQ0:002]]": "10.9兆トークン"}
    assert quantity_placeholder_instruction(replacements).startswith("Keep each quantity placeholder")


def test_protected_quantities_render_chinese_with_optional_ge_prefix_and_restore_fails_closed():
    masked, replacements = protect_token_quantities("10.9 trillion tokens", "zh-Hans")
    assert replacements == {"[[PQ0:001]]": "10.9万亿个Token"}
    assert restore_token_quantities(masked, replacements) == "10.9万亿个Token"
    assert restore_token_quantities("[[PQ0:001]] [[PQ0:001]]", replacements) is None
    assert restore_token_quantities("[[PQ9:001]]", replacements) is None
    assert restore_token_quantities("[[PQ0:001", replacements) is None


def test_quantity_instruction_exposes_supported_source_spans_and_normalized_value():
    assert quantity_instruction(SOURCE) == (
        "Preserve the exact meaning of these token quantities; do not round or change magnitude: "
        "'10.9 trillion tokens' (= 10900000000000 tokens)."
    )
    assert quantity_instruction("A normal post without an explicit token quantity.") == ""


def test_ignores_urls_handles_identifiers_and_unrelated_units_to_limit_false_positives():
    text = (
        "https://example.test/10.9-trillion-tokens @model_10_9_trillion_tokens "
        "build_10.9_trillion_tokens 10.9 trillion parameters 10.9 trillion tokens"
    )

    assert [item.span for item in extract_token_quantities(text)] == ["10.9 trillion tokens"]


def test_grouped_digits_are_whole_numbers_not_partial_matches():
    assert validate_translation_quantities("89.56 million tokens", "8,956万トークン") == []
    assert extract_token_quantities("89,56 million tokens") == []
    assert validate_translation_quantities("1,000 billion tokens", "1兆トークン") == []


def test_protection_preserves_precision_and_literal_marker_collisions():
    source = "Literal [[PQ0:001]] beside 89.56 million tokens and one trillion tokens."
    masked, replacements = protect_token_quantities(source, "en")
    assert "Literal [[PQ0:001]]" in masked
    assert "[[PQ1:001]]" in masked
    assert restore_token_quantities(masked, replacements) == source.replace("one trillion", "1 trillion")
    assert restore_token_quantities("original [[PQ0:001]]", {}) == "original [[PQ0:001]]"
    assert restore_token_quantities(masked + " [[PQ1:999]]", replacements) is None


@pytest.mark.parametrize("source,translated", [
    ("100M tokens; 210M tokens. Costs per million input tokens.", "100万トークン当たりの料金。"),
    ("173 million tokens, priced per-million input tokens.", "[[PQ0:001]]。100万トークン当たり。"),
    ("$5 per billion tokens?\n\nI use 150 billion a month. Also 1 million tokens.", "1500億トークン。"),
    ("10 million tokens of context; a 2 mil token corpus.", "200万トークンのコーパス。"),
])
def test_accepts_saved_reply_unit_prices_abbreviations_and_billing_ellipsis(source, translated):
    assert validate_translation_quantities(source, translated, source_language="en") == []


@pytest.mark.parametrize("source,translated", [
    ("1 million tokens and 2 billion parameters", "20億トークン"),
    ("1 million tokens. 2B parameters.", "20億トークン"),
    ("1 million tokens @2M_tokens", "200万トークン"),
    ("1 million tokens https://example.test/2M-tokens", "200万トークン"),
    ("1 million tokens. 2M tokens.", "20億トークン"),
    ("1 million tokens. Costs per million input tokens.", "1億トークン"),
    ("1 million tokens. 2 mil tokens.", "20億トークン"),
    ("1 million tokens. $5 per billion tokens?\n\nI use 150 billion a month.", "150兆トークン"),
    ("1 million tokens. $5 per billion parameters?\n\nI use 150 billion a month.", "1500億トークン"),
    ("1 million tokens. $5 per billion tokens?\n\nI use 150 billion parameters a month.", "1500億トークン"),
])
def test_extra_source_forms_do_not_license_wrong_values_units_urls_or_handles(source, translated):
    assert validate_translation_quantities(source, translated, source_language="en")


@pytest.mark.parametrize("language,good,bad", [
    ("en", "2000万トークン", "2万トークン"),
    ("es", "2万トークン", "2000万トークン"),
])
def test_mil_uses_declared_source_language(language, good, bad):
    assert validate_translation_quantities("20 mil tokens", good, source_language=language) == []
    assert validate_translation_quantities("20 mil tokens", bad, source_language=language)


def test_validation_extensions_leave_paid_protection_and_instructions_unchanged():
    source = "10 million tokens of context; a 2 mil token corpus. Costs per million tokens."
    assert protect_token_quantities(source, "ja") == (
        "[[PQ0:001]] of context; a 2 mil token corpus. Costs per million tokens.",
        {"[[PQ0:001]]": "1000万トークン"},
    )
    assert quantity_instruction(source) == (
        "Preserve the exact meaning of these token quantities; do not round or change magnitude: "
        "'10 million tokens' (= 10000000 tokens)."
    )


@pytest.mark.parametrize("source,translated", [
    ("1億5千万トークン。1億トークン。", "150 million tokens; 100 million tokens."),
    ("1亿5千万个Token。1亿个Token。", "1.5亿个Token。1亿个Token。"),
    ("1億5千萬トークン。1億トークン。", "1.5亿个Token。1亿个Token。"),
    ("1兆2億3千万トークン。1億トークン。", "1000230 million tokens."),
])
def test_validation_accepts_explicit_cjk_thousand_ten_thousand_compounds(source, translated):
    assert validate_translation_quantities(source, translated, source_language="ja") == []


@pytest.mark.parametrize("source,translated", [
    ("1億5千万トークン。1億トークン。", "1.5 billion tokens."),
    ("1億5千万パラメータ。1億トークン。", "150 million tokens."),
    ("https://example.test/1億5千万トークン 1億トークン。", "150 million tokens."),
])
def test_compound_validation_still_rejects_wrong_values_units_and_urls(source, translated):
    assert validate_translation_quantities(source, translated, source_language="ja")


def test_compound_source_validation_does_not_change_paid_quantity_protection():
    assert protect_token_quantities("1億5千万トークン。1億トークン。", "en") == (
        "1億5千万トークン。[[PQ0:001]]。", {"[[PQ0:001]]": "100 million tokens"},
    )


@pytest.mark.parametrize("source,translated", [
    ("143亿Token。https://t.co/xWdYwT1HGs在接入后达到143.5亿Tokens。", "14.35 billion tokens"),
    ("1.2亿Token。https://t.co/xdDkZo7AST，实名后7000万Token自动到账。", "70 million tokens"),
])
def test_validation_sees_cjk_prose_immediately_after_complete_tco_link(source, translated):
    assert validate_translation_quantities(source, translated, source_language="zh") == []


@pytest.mark.parametrize("url", [
    "https://t.co/abcdefghij/143.5亿Tokens",
    "https://t.co/abcdefghij?qty=143.5亿Tokens",
    "https://t.co/abcdefghij#143.5亿Tokens",
    "https://t.co/abcdefghijk143.5亿Tokens",
    "https://example.com/143.5亿Tokens",
    "@n143.5亿Tokens",
])
def test_tco_boundary_does_not_license_quantities_inside_links_or_handles(url):
    assert validate_translation_quantities(f"143亿Token。{url}", "14.35 billion tokens", source_language="zh")


def test_tco_validation_keeps_original_quantity_protection_and_instruction():
    source = "143亿Token。https://t.co/xWdYwT1HGs在接入后达到143.5亿Tokens。"
    assert protect_token_quantities(source, "en") == (
        "[[PQ0:001]]。https://t.co/xWdYwT1HGs在接入后达到143.5亿Tokens。",
        {"[[PQ0:001]]": "14.3 billion tokens"},
    )
    assert "143.5" not in quantity_instruction(source)


@pytest.mark.parametrize("source,translated", [
    ("A million tokens of context; three million tokens of cache.", "300万トークン"),
    ("100 billion tokens saved, with 5-10 billion tokens on the plan.", "100億トークン"),
    ("100 billion tokens saved, with 5–10 billion tokens on the plan.", "50億トークン"),
    ("100 billion tokens saved, with 5 to 10 billion tokens on the plan.", "100億トークン"),
])
def test_validation_accepts_small_word_quantities_and_scaled_range_endpoints(source, translated):
    assert validate_translation_quantities(source, translated, source_language="en") == []


@pytest.mark.parametrize("source,translated", [
    ("1 million tokens, three million parameters", "3 million tokens"),
    ("1 million tokens, twenty three million tokens", "3 million tokens"),
    ("1 million tokens, one hundred and three million tokens", "3 million tokens"),
    ("1 million tokens, twenty-three million tokens", "3 million tokens"),
    ("1 million tokens, 5-10 billion parameters", "10 billion tokens"),
    ("1 million tokens, 5-10 billion tokens", "20 billion tokens"),
    ("1 million tokens https://example.test/three-million-tokens", "3 million tokens"),
    ("1 million tokens https://example.test/5-10-billion-tokens", "10 billion tokens"),
])
def test_word_and_range_forms_keep_compound_unit_url_and_magnitude_guards(source, translated):
    assert validate_translation_quantities(source, translated, source_language="en")
