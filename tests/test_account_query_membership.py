"""Query membership stays attached to the account and observed post."""

import pytest
from django.db import IntegrityError, transaction

from core.models import (
    Account,
    AccountPostAppearance,
    AccountQueryMembership,
    Post,
    SearchQuery,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_account_only_and_post_memberships_are_distinct_and_unique():
    account = Account.objects.create(author_id="query-member-1")
    query = SearchQuery.objects.create(query_id="query-member-1")
    post = Post.objects.create(tweet_id="query-member-post", text="fixture")
    AccountPostAppearance.objects.create(account=account, post=post)

    AccountQueryMembership.objects.create(account=account, search_query=query)
    AccountQueryMembership.objects.create(account=account, search_query=query, post=post)
    assert AccountQueryMembership.objects.filter(account=account).count() == 2
    with pytest.raises(IntegrityError), transaction.atomic():
        AccountQueryMembership.objects.create(account=account, search_query=query)
    with pytest.raises(IntegrityError), transaction.atomic():
        AccountQueryMembership.objects.create(account=account, search_query=query, post=post)


def test_post_membership_requires_that_accounts_appearance():
    account = Account.objects.create(author_id="query-member-2")
    query = SearchQuery.objects.create(query_id="query-member-2")
    post = Post.objects.create(tweet_id="query-member-other-post", text="fixture")
    with pytest.raises(IntegrityError), transaction.atomic():
        AccountQueryMembership.objects.create(account=account, search_query=query, post=post)
