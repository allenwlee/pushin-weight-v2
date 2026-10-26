"""Preserve provider entity documents; interpret aliases without rewriting them."""

import json
import logging
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)
_ENTITY_LISTS = {"urls", "user_mentions", "hashtags", "symbols", "media"}


def entity_text(record: dict, *keys: str) -> str:
    """First nonblank string alias wins; invalid aliases fall through."""
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def mention_id(record: dict) -> str:
    """Prefer the provider's lossless id_str over legacy numeric/string id."""
    for key in ("id_str", "id"):
        value = record.get(key)
        if type(value) is int and value > 0:
            return str(value)
        if isinstance(value, str) and value.isascii() and value.isdigit():
            return value
    return ""


def normalize_entities(value: Any) -> dict[str, Any]:
    """Accept an object or JSON object string; ignore malformed entity lists.

    Missing/null/empty/scalar inputs provide no evidence. Valid records retain
    their original aliases and all provider fields, including URL positions.
    """
    if isinstance(value, str):
        if not value.strip() or value.strip().lower() == "null":
            return {}
        try:
            value = json.loads(value)
        except ValueError:
            logger.warning("Ignoring malformed tweet entities JSON")
            return {}
    if not isinstance(value, dict):
        return {}
    result = deepcopy(value)
    for key in _ENTITY_LISTS & result.keys():
        entries = result[key]
        if not isinstance(entries, list):
            del result[key]
        else:
            result[key] = [entry for entry in entries if isinstance(entry, dict) and entry]
    return result


def _identity(group: str, entry: dict) -> str:
    if group == "user_mentions":
        return mention_id(entry)
    if group in {"hashtags", "symbols"}:
        return entity_text(entry, "text", "tag").lower().lstrip("#")
    return entity_text(entry, "url", "expanded_url", "id_str")


def _merge_fields(old: dict, new: dict) -> dict:
    result = deepcopy(old)
    for key, value in new.items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        previous = result.get(key)
        if previous is not None and type(previous) is not type(value):
            continue
        result[key] = (_merge_fields(previous, value)
                       if isinstance(previous, dict) and isinstance(value, dict)
                       else deepcopy(value))
    return result


def merge_entities(existing: Any, incoming: Any) -> dict[str, Any]:
    """Merge observations without clearing earlier evidence on partial replies.

    Match entries by URL, stable account ID or tag, and by positions when both
    replies supply them. Nonempty fields from the newer matching entry win;
    missing/null/empty fields cannot erase earlier values. Distinct positions
    remain distinct source entries. Unknown provider fields are retained.
    """
    result = normalize_entities(existing)
    for group, values in normalize_entities(incoming).items():
        if group not in _ENTITY_LISTS:
            result = _merge_fields(result, {group: values})
            continue
        saved = result.setdefault(group, [])
        for entry in values:
            identity = _identity(group, entry)
            match = next((i for i, old in enumerate(saved)
                          if identity and _identity(group, old) == identity
                          and (not old.get("indices") or not entry.get("indices")
                               or old["indices"] == entry["indices"])), None)
            if match is not None:
                saved[match] = _merge_fields(saved[match], entry)
            elif entry not in saved:
                saved.append(deepcopy(entry))
    return result
