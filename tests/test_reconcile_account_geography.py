"""Retired schema operations cannot read or write the live canonical schema."""

import pytest
from django.core.management import call_command, CommandError


@pytest.mark.django_db
def test_retired_command_fails_before_database_access(django_assert_num_queries):
    with django_assert_num_queries(0), pytest.raises(CommandError, match="Retired country/region"):
        call_command("reconcile_account_geography", apply=True)
