from core.models import Post
from monitor.post_artifacts import _legacy_literal


def test_original_english_is_available_without_translation():
    post = Post(tweet_id="source-en", text="Original text", lang_detected="en")
    assert _legacy_literal(post)["en"] == "Original text"
