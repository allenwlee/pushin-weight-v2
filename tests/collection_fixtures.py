"""Explicit instruction registration for saved collection evidence fixtures."""

from core.collection_state import register_direct_job


def evidence_job(*, source_id, purpose="catalog", contract_id=None, scope=None):
    return register_direct_job(
        source_id=source_id,
        purpose=purpose,
        contract_id=contract_id,
        scope={} if scope is None else scope,
        driver="persist_source" if purpose == "metric" else "execute_catalog",
        limits={"fixture": True},
    )
