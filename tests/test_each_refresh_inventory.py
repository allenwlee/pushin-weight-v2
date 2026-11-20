"""The source oracle must not prevent later authorized staging refreshes."""
from dataclasses import replace

from scripts.staging_refresh.policy import authorize, load_policy
from tests.staging_refresh.test_policy import POLICY_PATH, _environment, _inspection


def test_current_source_with_each_oracle_passes_existing_refresh_guard():
    policy = load_policy(POLICY_PATH)
    current = _inspection(policy, source=True)
    authorize(policy, action='preflight', environ=_environment(policy),
              source=replace(current, views=current.views | {'each_brand_post_facts_source'}),
              target=_inspection(policy, source=False))


def test_supported_source_before_each_storage_still_passes_refresh_guard():
    policy = load_policy(POLICY_PATH)
    current = _inspection(policy, source=True)
    authorize(policy, action='preflight', environ=_environment(policy),
              source=replace(current, views=current.views - {'each_brand_post_facts_source'}),
              target=_inspection(policy, source=False))
