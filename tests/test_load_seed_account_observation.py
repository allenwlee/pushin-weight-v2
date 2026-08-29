from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from core.models import Account

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@override_settings(KNOWN_MODELS=frozenset({"minimax"}))
def test_load_seed_routes_account_writes_through_model_gateway():
    stdout = StringIO()
    with patch.object(
        Account.objects,
        "update_or_create",
        side_effect=AssertionError("Account.update_or_create bypassed gateway"),
    ):
        call_command("load_seed", brands="minimax", stdout=stdout)

    account = Account.objects.get(author_id="hailuo_ai")
    assert account.handle == "hailuo_ai"


@override_settings(KNOWN_MODELS=frozenset({"minimax"}))
def test_load_seed_is_idempotent_through_gateway():
    call_command("load_seed", brands="minimax", stdout=StringIO())
    first_seen = Account.objects.get(author_id="hailuo_ai").first_seen_at
    call_command("load_seed", brands="minimax", stdout=StringIO())

    account = Account.objects.get(author_id="hailuo_ai")
    assert account.handle == "hailuo_ai"
    assert account.first_seen_at == first_seen
