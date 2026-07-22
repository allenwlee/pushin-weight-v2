"""Custom template filters for the Pushin' Weight dashboard.

Provides `get_item` for dict lookups by variable key in Django templates,
which lack the `dict[key]` syntax when `key` is a loop variable.
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.filter(name="get_item")
def get_item(d: dict, key: str):
    """Return d[key] or None. Safe dict lookup for template use.

    Usage in template:
        {{ mydict|get_item:variable_key }}
    """
    if d is None:
        return None
    try:
        return d.get(key)
    except (TypeError, AttributeError):
        return None
