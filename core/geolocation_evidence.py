"""Explicit source-only projections of existing owners; no extra tables.

Canonical models omit these columns at cutover. PostgreSQL grants, rather than
Python naming, decide which process may read them. Writers use their current
connection inside the same transaction as the canonical parent.
"""

from django.db import connections, models


class SourceProjection(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        raise TypeError("Use write_source_evidence on an existing canonical owner")

    def delete(self, *args, **kwargs):
        raise TypeError("Source projections do not own parent deletion")


class AccountLocationEvidence(SourceProjection):
    account_key = models.UUIDField(primary_key=True)
    reported_profile_location = models.TextField(db_column="location", null=True)

    class Meta:
        managed = False
        db_table = "accounts"


class AccountBasedInEvidence(SourceProjection):
    account_key = models.UUIDField(primary_key=True)
    reported_based_in = models.TextField(db_column="account_based_in", null=True)

    class Meta:
        managed = False
        db_table = "x_account_details"


class PostLocationEvidence(SourceProjection):
    tweet_id = models.TextField(primary_key=True)
    reported_author_location = models.TextField(db_column="author_location", null=True)

    class Meta:
        managed = False
        db_table = "posts"


class ProfileLocationEvidence(SourceProjection):
    id = models.BigIntegerField(primary_key=True)
    reported_location = models.TextField(db_column="location", null=True)
    profile_data = models.JSONField()
    raw_profile_payload = models.JSONField(null=True)

    class Meta:
        managed = False
        db_table = "account_profile_snapshots"


class AffiliationLocationEvidence(SourceProjection):
    id = models.BigIntegerField(primary_key=True)
    reported_location = models.TextField(db_column="location", null=True)

    class Meta:
        managed = False
        db_table = "people_brand_affiliations"


class JobSourceEvidence(SourceProjection):
    id = models.BigIntegerField(primary_key=True)
    raw_payload = models.JSONField(null=True)

    class Meta:
        managed = False
        db_table = "job_listings"


class JobExtractionEvidence(SourceProjection):
    id = models.BigIntegerField(primary_key=True)
    raw_evidence = models.JSONField(null=True)

    class Meta:
        managed = False
        db_table = "job_listing_evidence"


class JobLocationSourceEvidence(SourceProjection):
    id = models.BigIntegerField(primary_key=True)
    reported_value = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = "job_listing_locations"


PROJECTIONS = {
    "accounts": AccountLocationEvidence,
    "x_account_details": AccountBasedInEvidence,
    "posts": PostLocationEvidence,
    "account_profile_snapshots": ProfileLocationEvidence,
    "people_brand_affiliations": AffiliationLocationEvidence,
    "job_listings": JobSourceEvidence,
    "job_listing_evidence": JobExtractionEvidence,
    "job_listing_locations": JobLocationSourceEvidence,
}


def source_evidence(owner):
    """Authorized ingestion/correction read; serving credentials cannot use it."""
    projection = PROJECTIONS[owner._meta.db_table]
    return projection.objects.using(owner._state.db or "default").get(pk=owner.pk)


def write_source_evidence(owner, **values):
    """Update only source columns on an existing owner, in its transaction."""
    projection = PROJECTIONS[owner._meta.db_table]
    alias = owner._state.db or "default"
    if owner._state.adding or not connections[alias].in_atomic_block:
        raise ValueError("Source and canonical writes require one parent transaction")
    allowed = {field.name for field in projection._meta.fields if not field.primary_key}
    if not values or set(values) - allowed:
        raise ValueError("Only the explicit source fields may be written")
    if projection.objects.using(alias).filter(pk=owner.pk).update(**values) != 1:
        raise ValueError("Source owner no longer exists")
