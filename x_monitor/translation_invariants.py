"""Small, deterministic guards for explicit large token quantities.

This module deliberately does not attempt general semantic translation
validation.  It recognizes only Arabic-digit quantities next to a token unit;
spelled-out numbers, unrelated units, and contextual paraphrases are outside
its contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

_UNIT = r"(?:[个個]?(?:tokens?|トークン(?:数)?|令牌))"
_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_ENGLISH = re.compile(
    rf"(?<![@/#.,A-Za-z0-9_-])(?P<number>{_NUMBER})\s*"
    rf"(?P<scale>million|billion|trillion)\s*(?P<unit>{_UNIT})(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_IMPLICIT_ENGLISH = re.compile(
    rf"(?<![@/#.,A-Za-z0-9_-])(?P<word>a|one|next)\s+"
    rf"(?P<scale>million|billion|trillion)\s*(?P<unit>{_UNIT})(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_CJK = re.compile(
    rf"(?<![@/#.,A-Za-z0-9_-])(?P<quantity>"
    rf"{_NUMBER}\s*(?:万亿|萬億|兆|亿|億|万|萬)"
    rf"(?:\s*{_NUMBER}\s*(?:万亿|萬億|兆|亿|億|万|萬))*"
    rf")\s*"
    rf"(?P<unit>{_UNIT})(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_CJK_PART = re.compile(rf"({_NUMBER})\s*(万亿|萬億|兆|亿|億|万|萬)")
_URL_OR_HANDLE = re.compile(r"https?://\S+|www\.\S+|@[A-Za-z0-9_]+", re.IGNORECASE)
_ENGLISH_SCALE = {"million": Decimal("1e6"), "billion": Decimal("1e9"), "trillion": Decimal("1e12")}
_CJK_SCALE = {
    "万": Decimal("1e4"), "萬": Decimal("1e4"), "亿": Decimal("1e8"), "億": Decimal("1e8"),
    "兆": Decimal("1e12"), "万亿": Decimal("1e12"), "萬億": Decimal("1e12"),
}


@dataclass(frozen=True)
class Quantity:
    """A recognized source/translation token quantity and its exact value."""

    span: str
    value: Decimal
    start: int = -1
    end: int = -1


def extract_token_quantities(text: str) -> list[Quantity]:
    """Return explicit, large Arabic-digit token quantities outside URLs/handles."""
    masked = _URL_OR_HANDLE.sub(lambda match: " " * len(match.group()), text)
    quantities: list[Quantity] = []
    for match in _ENGLISH.finditer(masked):
        value = Decimal(match["number"].replace(",", "")) * _ENGLISH_SCALE[match["scale"].lower()]
        quantities.append(Quantity(text[match.start():match.end()], value, match.start(), match.end()))
    for match in _IMPLICIT_ENGLISH.finditer(masked):
        value = _ENGLISH_SCALE[match["scale"].lower()]
        start = match.start("scale") if match["word"].lower() == "next" else match.start()
        quantities.append(Quantity(text[start:match.end()], value, start, match.end()))
    for match in _CJK.finditer(masked):
        value = sum(
            (Decimal(number.replace(",", "")) * _CJK_SCALE[scale] for number, scale in _CJK_PART.findall(match["quantity"])),
            Decimal(0),
        )
        quantities.append(Quantity(text[match.start():match.end()], value, match.start(), match.end()))
    return sorted(quantities, key=lambda quantity: quantity.start)


def quantity_instruction(source: str) -> str:
    """Return a short preservation instruction when the source has supported quantities."""
    quantities = extract_token_quantities(source)
    if not quantities:
        return ""
    rendered = ", ".join(f"{quantity.span!r} (= {_format_value(quantity.value)} tokens)" for quantity in quantities)
    return f"Preserve the exact meaning of these token quantities; do not round or change magnitude: {rendered}."


def _validation_source_values(source: str, *, source_language: str | None) -> set[Decimal]:
    """Include narrow source shorthand without changing protected request text."""
    values = {quantity.value for quantity in extract_token_quantities(source)}
    # X's complete short links often abut CJK prose without whitespace. Mask
    # just that link before the generic URL matcher can swallow the prose too.
    # Paths, queries, fragments and longer identifiers remain generic URLs.
    short_links_masked = re.sub(
        r"https?://t\.co/[A-Za-z0-9]{10}(?![A-Za-z0-9_/?#.%=-])",
        lambda match: " " * len(match.group()), source,
    )
    masked = _URL_OR_HANDLE.sub(lambda match: " " * len(match.group()), short_links_masked)
    boundary = r"(?<![@/#.,A-Za-z0-9_-])"
    per = re.compile(
        boundary + rf"per[ -]+(?P<scale>million|billion|trillion)\s+"
        rf"(?:(?:input|output|cached|cache)\s+)?{_UNIT}(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    abbreviated = re.compile(
        boundary + rf"(?P<number>{_NUMBER})\s*(?P<scale>mil|[MBT])\s*"
        rf"{_UNIT}(?![A-Za-z0-9_])", re.IGNORECASE,
    )
    elliptical = re.compile(
        boundary + r"per\s+(?:million|billion|trillion)\s+tokens?\s*[?!.]?"
        r"\s*\n+\s*(?:I|we|they)\s+(?:use|consume|process|generate|emit)\s+"
        rf"(?P<number>{_NUMBER})\s+(?P<scale>million|billion|trillion)\s+"
        r"(?:a|per|each)\s+(?:day|month|year)\b", re.IGNORECASE,
    )
    language = (source_language or "").lower().replace("_", "-").split("-")[0]
    # English informal "mil" means million; Spanish "mil" means thousand.
    # Without either declared language this narrow guard cannot disambiguate it.
    mil = (Decimal("1e6"),) if language == "en" else (
        (Decimal("1e3"),) if language == "es" else (Decimal("1e3"), Decimal("1e6"))
    )
    scales = {"m": (Decimal("1e6"),), "b": (Decimal("1e9"),), "t": (Decimal("1e12"),), "mil": mil}
    for match in per.finditer(masked):
        values.add(_ENGLISH_SCALE[match["scale"].lower()])
    for match in abbreviated.finditer(masked):
        count = Decimal(match["number"].replace(",", ""))
        values.update(count * scale for scale in scales[match["scale"].lower()])
    for match in elliptical.finditer(masked):
        values.add(Decimal(match["number"].replace(",", "")) * _ENGLISH_SCALE[match["scale"].lower()])
    words = {word: Decimal(n) for n, word in enumerate(
        ("two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"), start=2,
    )}
    number_words = set(words) | {
        "one", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
        "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty",
        "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
        "billion", "trillion",
    }
    spelled = re.compile(
        boundary + rf"(?P<number>{'|'.join(words)})\s+"
        rf"(?P<scale>million|billion|trillion)\s*{_UNIT}(?![A-Za-z0-9_])", re.IGNORECASE,
    )
    for match in spelled.finditer(masked):
        previous = re.search(r"([A-Za-z]+)\s+(?:and\s+)?$", masked[:match.start()], re.IGNORECASE)
        # Do not turn an unsupported compound such as 'twenty three' or
        # 'one hundred and three' into a false source value of three.
        if previous and previous[1].lower() in number_words:
            continue
        values.add(words[match["number"].lower()] * _ENGLISH_SCALE[match["scale"].lower()])
    ranges = re.compile(
        boundary + rf"(?P<low>{_NUMBER})\s*(?:-|–|—|to)\s*(?P<high>{_NUMBER})\s*"
        rf"(?P<scale>million|billion|trillion)\s*{_UNIT}(?![A-Za-z0-9_])", re.IGNORECASE,
    )
    for match in ranges.finditer(masked):
        low, high = (Decimal(match[k].replace(",", "")) for k in ("low", "high"))
        if low <= high:
            values.update(n * _ENGLISH_SCALE[match["scale"].lower()] for n in (low, high))
    # Japanese/Chinese compounds can use 千万 as a part: 1億5千万 = 150M.
    # Validation alone accepts it; paid prompts and protected spans stay stable.
    cjk_scale = _CJK_SCALE | {"千万": Decimal("1e7"), "千萬": Decimal("1e7")}
    cjk_part = rf"{_NUMBER}\s*(?:千万|千萬|万亿|萬億|兆|亿|億|万|萬)"
    cjk_compound = re.compile(
        boundary + rf"(?P<quantity>{cjk_part}(?:\s*{cjk_part})*)\s*"
        rf"{_UNIT}(?![A-Za-z0-9_])", re.IGNORECASE,
    )
    for match in cjk_compound.finditer(masked):
        parts = re.findall(rf"({_NUMBER})\s*(千万|千萬|万亿|萬億|兆|亿|億|万|萬)", match["quantity"])
        values.add(sum((Decimal(n.replace(",", "")) * cjk_scale[scale] for n, scale in parts), Decimal(0)))
    return values


def validate_translation_quantities(
    source: str, translated: str, *, source_language: str | None = None,
) -> list[str]:
    """Report introduced supported token quantities whose values are absent from source.

    Repeated source or localized quantities are allowed.  The function does not
    reject omitted quantities, because this narrow detector cannot reliably
    distinguish an omission from an unsupported written-out paraphrase.
    """
    source_values = _validation_source_values(source, source_language=source_language)
    if not source_values:
        return []
    errors = []
    for quantity in extract_token_quantities(translated):
        if quantity.value not in source_values:
            expected = ", ".join(_format_value(value) for value in sorted(source_values))
            errors.append(
                f"translated token quantity {quantity.span!r} means {_format_value(quantity.value)} tokens; "
                f"source supports only {expected} tokens"
            )
    return errors


def protect_token_quantities(source: str, target_language: str) -> tuple[str, dict[str, str]]:
    """Replace supported quantity phrases with collision-free target-language markers.

    Qualifiers such as ``next`` are intentionally outside the protected span.
    """
    quantities = extract_token_quantities(source)
    if not quantities:
        return source, {}
    namespace = 0
    while f"[[PQ{namespace}:" in source:
        namespace += 1
    replacements: dict[str, str] = {}
    masked = source
    for index, quantity in enumerate(reversed(quantities), start=1):
        marker = f"[[PQ{namespace}:{len(quantities) - index + 1:03d}]]"
        replacements[marker] = _render_quantity(quantity.value, target_language)
        masked = masked[:quantity.start] + marker + masked[quantity.end:]
    return masked, replacements


def protect_translation_spans(source: str, target_language: str) -> tuple[str, dict[str, str]]:
    """Protect quantities and explicit Latin-spelling → katakana-reading examples.

    Ordinary Japanese prose remains translatable. Only an anchored mapping and
    quoted katakana alternatives on that same line are copied, not explanations.
    This deliberately does not attempt universal pronunciation detection.
    """
    masked, replacements = protect_token_quantities(source, target_language)
    spans: list[tuple[int, int]] = []
    for line in re.finditer(r"[^\r\n]+", masked):
        pair = re.match(r"[ \t]*[A-Za-z][A-Za-z0-9 .·+/_-]*[ \t]*→[ \t]*[ァ-ヺー・]+", line.group())
        if pair is None:
            continue
        spans.append((line.start(), line.start() + pair.end()))
        for alternative in re.finditer(r'[「『“"]([ァ-ヺー・]+)[」』”"]', line.group()[pair.end():]):
            offset = line.start() + pair.end()
            spans.append((offset + alternative.start(1), offset + alternative.end(1)))
    if not spans:
        return masked, replacements
    namespace = 0
    while f"[[PQ{namespace}:" in source:
        namespace += 1
    start_index = len(replacements)
    for index in range(len(spans) - 1, -1, -1):
        start, end = spans[index]
        marker = f"[[PQ{namespace}:{start_index + index + 1:03d}]]"
        replacements[marker] = masked[start:end]
        masked = masked[:start] + marker + masked[end:]
    return masked, replacements


def restore_token_quantities(text: str, replacements: dict[str, str]) -> str | None:
    """Restore placeholders only when every expected marker survived exactly once."""
    if not replacements:
        return text
    # This namespace was absent from the source. Other namespaces may be
    # literal source content and must survive collision handling unchanged.
    prefix = next(iter(replacements)).split(":", 1)[0] + ":"
    found = re.findall(re.escape(prefix) + r"\d+\]\]", text)
    if len(found) != len(replacements) or set(found) != set(replacements):
        return None
    if any(text.count(marker) != 1 for marker in replacements):
        return None
    restored = text
    for marker, replacement in replacements.items():
        restored = restored.replace(marker, replacement)
    return None if prefix in restored else restored


def quantity_placeholder_instruction(replacements: dict[str, str]) -> str:
    """Tell a translation provider to preserve every placeholder exactly once."""
    if not replacements:
        return ""
    markers = ", ".join(replacements)
    return f"Keep each quantity placeholder exactly once and unchanged: {markers}. Do not add placeholders."


def _render_quantity(value: Decimal, target_language: str) -> str:
    language = target_language.lower().replace("_", "-")
    if language == "ja":
        number, unit = _cjk_number_and_unit(value, ((Decimal("1e12"), "兆"), (Decimal("1e8"), "億"), (Decimal("1e4"), "万")))
        return f"{number}{unit}トークン"
    if language in {"zh-hans", "zh-cn"}:
        number, unit = _cjk_number_and_unit(value, ((Decimal("1e12"), "万亿"), (Decimal("1e8"), "亿"), (Decimal("1e4"), "万")))
        return f"{number}{unit}个Token"
    number, unit = _cjk_number_and_unit(value, ((Decimal("1e12"), "trillion"), (Decimal("1e9"), "billion"), (Decimal("1e6"), "million")))
    return f"{number} {unit} tokens"


def _cjk_number_and_unit(value: Decimal, units: tuple[tuple[Decimal, str], ...]) -> tuple[str, str]:
    for scale, unit in units:
        if value >= scale:
            return _format_value(value / scale), unit
    scale, unit = units[-1]
    return _format_value(value / scale), unit


def _format_value(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
