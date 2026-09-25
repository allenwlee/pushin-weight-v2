"""The historical language repair must be bounded and language-only."""

import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection

from core.models import Post


class FakeClient:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        return {"lang_detected": next(self.answers)}


def test_repair_dry_run_and_bounded_apply(db):
    first = Post.objects.create(tweet_id="repair-001", text="Bonjour", text_en="Hello", lang_detected="other")
    second = Post.objects.create(tweet_id="repair-002", text="Unknown", text_en="Kept", lang_detected="other")
    client = FakeClient(["fr", "zz"])
    output = io.StringIO()
    with patch("monitor.management.commands.repair_post_language_codes.build_translator_client_from_env") as builder:
        call_command("repair_post_language_codes", max_posts=1, stdout=output)
        builder.assert_not_called()
    preview = json.loads(output.getvalue())
    assert preview["eligible"] == 2
    assert preview["max_provider_calls"] == 1
    assert preview["preview_end_cursor"] == first.pk

    config = SimpleNamespace(llm=SimpleNamespace(translator_model="test-model"))
    with patch("monitor.management.commands.repair_post_language_codes.load_config", return_value=config), \
         patch("monitor.management.commands.repair_post_language_codes.build_translator_client_from_env", return_value=client):
        call_command("repair_post_language_codes", apply=True, max_posts=1,
                     confirm_database=connection.settings_dict["NAME"],
                     confirm_provider_calls=1, stdout=io.StringIO())
        call_command("repair_post_language_codes", apply=True, max_posts=1,
                     after_post_id=first.pk, confirm_database=connection.settings_dict["NAME"],
                     confirm_provider_calls=1, stdout=io.StringIO())
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.lang_detected == "fr"
    assert first.text_en == "Hello"
    assert second.lang_detected == "other"
    assert second.text_en == "Kept"
    assert len(client.calls) == 2
