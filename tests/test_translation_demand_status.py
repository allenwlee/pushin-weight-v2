from monitor.post_enrichment import (
    enrichment_fact_terminal_complete,
    enrichment_stage_outcome,
)


def test_unrequested_translation_does_not_keep_classified_post_pending():
    fact = {"translation_status": "pending", "translation_requested": False,
            "classification_status": "succeeded", "output_complete": False}
    assert enrichment_stage_outcome(translation_status="pending", classification_status="succeeded", translation_requested=False) == "succeeded"
    assert enrichment_fact_terminal_complete(fact)
    fact["translation_requested"] = True
    assert not enrichment_fact_terminal_complete(fact)
