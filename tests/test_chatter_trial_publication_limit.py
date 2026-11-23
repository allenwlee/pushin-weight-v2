"""A bounded operator trial limits packages without changing recurring editions."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from monitor.editorial.chatter_chain import _queue_writers
from monitor.editorial.chatter_trends import TRENDS_SCOPE
from monitor.editorial.config import ChatterTrial, load_editorial_config
from tests.test_original_content_consideration import consideration


def test_legacy_trial_snapshot_serialization_is_unchanged():
    original = {"scope": "chatter-test", "limit_usd": 10.0, "carry_usd": 0.1}
    assert ChatterTrial.model_validate(original).model_dump(mode="json") == original


@pytest.mark.parametrize("limit", [0, 19, True, "1", 1.5])
def test_publication_limit_requires_a_bounded_integer(limit):
    with pytest.raises(ValidationError):
        ChatterTrial(scope="chatter-test", limit_usd=10, carry_usd=0,
                     publication_limit=limit)


@pytest.mark.parametrize("limit", [None, 1])
@pytest.mark.parametrize("personalized", [False, True])
@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_trial_plans_only_its_selected_packages(monkeypatch, limit, personalized):
    giant = consideration(consideration_state="selected", editorial_group="giant")
    rest = consideration(consideration_state="selected")
    rest.run = giant.run
    rest.save(update_fields=["run"])
    run = giant.run
    if personalized:
        run.scope_key = TRENDS_SCOPE
        run.save(update_fields=["scope_key"])
    cfg = load_editorial_config(Path("config/editorial-chatter-staging.yaml"))
    cfg = cfg.model_copy(update={"voices": {
        "chatter:ja": cfg.voices["chatter:ja"],
        "chatter:en": cfg.voices["chatter:en"],
    }, "locale_routes": {}})
    trial = {"scope": "chatter-test", "limit_usd": 10, "carry_usd": 0}
    if limit is not None:
        trial["publication_limit"] = limit
    cfg = cfg.model_copy(update={"chatter": cfg.chatter.model_copy(
        update={"trial": ChatterTrial.model_validate(trial)})})
    all_pairs = [(rest.pk, "en"), (giant.pk, "en"), (rest.pk, "ja"), (giant.pk, "ja")]
    pairs = [(rest.pk, "en")] if limit == 1 else all_pairs

    def check_saved_plan(*args, **kwargs):
        saved = type(run).objects.get(pk=run.pk).outcome
        assert saved["planned_writers"] == [f"{row_id}:{locale}" for row_id, locale in pairs]
        if limit is not None:
            assert saved["trial_deferred_writers"] == [
                f"{row_id}:{locale}" for row_id, locale in all_pairs[limit:]]
        else:
            assert "trial_deferred_writers" not in saved

    writer, enqueue = Mock(side_effect=check_saved_plan), Mock(side_effect=check_saved_plan)
    monkeypatch.setattr("monitor.editorial.chatter_chain.write_chatter", writer)

    for _ in range(2):
        writer.reset_mock()
        enqueue.reset_mock()
        _queue_writers(run, cfg, enqueue)
        run.refresh_from_db()
        assert run.outcome["planned_writers"] == [
            f"{row_id}:{locale}" for row_id, locale in pairs]
        if limit is not None:
            assert run.outcome["trial_deferred_writers"] == [
                f"{row_id}:{locale}" for row_id, locale in all_pairs[limit:]]
        else:
            assert "trial_deferred_writers" not in run.outcome
        if personalized:
            assert [(call.args[0], call.args[1]) for call in writer.call_args_list] == pairs
            enqueue.assert_not_called()
        else:
            assert [call.args for call in enqueue.call_args_list] == [
                ("write", row_id, locale) for row_id, locale in pairs]
            writer.assert_not_called()
