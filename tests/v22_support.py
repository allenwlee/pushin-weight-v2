"""Shared PostgreSQL-only support for the transitional v22 Django view nets.

U1 preserves the existing mocked view dependencies while U2/U3 replace them
with deterministic ORM-seeded fidelity data. Authentication is already real:
each Django test database creates its own ordinary user, so no developer
account lookup can hide an incomplete run.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase


V22_TEST_USER_EMAIL = "v22-verifier@example.test"


class PostgreSQLV22TestCase(TestCase):
    """Django ``TestCase`` with a suite-owned, non-privileged logged-in user."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.v22_test_user = get_user_model().objects.create_user(
            username="v22-verifier",
            email=V22_TEST_USER_EMAIL,
            password="v22-test-only-password",
        )

    def setUp(self):
        super().setUp()
        self.client = Client(HTTP_HOST="127.0.0.1")
        self.client.force_login(self.v22_test_user)


def assert_v22_selector_matches(
    test_case: TestCase,
    matches: int,
    *,
    selector: str,
    locale: str,
    viewport: str,
    oracle_source: str,
) -> None:
    """Fail a zero-match v22 selector with the context needed to reproduce it."""
    if matches == 0:
        test_case.fail(
            "v22 selector matched zero elements: "
            f"selector={selector!r}; locale={locale!r}; viewport={viewport!r}; "
            f"oracle_source={oracle_source!r}"
        )
