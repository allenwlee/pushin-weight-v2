from decimal import Decimal

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
