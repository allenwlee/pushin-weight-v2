"""Measure the supported output shape with offline transports and real storage."""

import copy
import json
import re
from collections import Counter
from pathlib import Path
from time import perf_counter

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core import models
from monitor import pulse_control
from monitor.pulse_processing import process_saved_findings
from tests.test_classified_product_releases import CombinedTransport, setup_cycle
from tests.test_compressed_classifier import answers, extraction

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_maximum_findings_shape_has_explicit_growth_and_provider_free_replay(monkeypatch, tmp_path, settings):
    state, runner, transport = setup_cycle(monkeypatch)
    document = extraction()
    template = document["release_findings"]["findings"][0]
    document["entities"] = []
    document["release_findings"]["findings"] = []
    texts = []
    for index in range(8):
        name = f"QwenProduct{index}"
        text = f"{name} weights are available today."
        texts.append(text)
        document["entities"].append({"name": name, "source": "post", "evidence": text})
        finding = copy.deepcopy(template)
        finding["observed_name"] = name
        finding["assertions"] = [
            {**copy.deepcopy(template["assertions"][0]), "source_excerpt": text,
             "assertion_text": f"{name} availability statement {number}"}
            for number in range(8)
        ]
        document["release_findings"]["findings"].append(finding)
    state.post.text = " ".join(texts)
    state.post.save(update_fields=["text"])

    def respond(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model"].startswith("deepseek"):
            return copy.deepcopy(document)
        return answers(json.loads(kwargs["messages"][0]["content"]))

    monkeypatch.setattr(CombinedTransport, "messages_create", respond)
    started = perf_counter()
    with CaptureQueriesContext(connection) as queries:
        runner._run_post_fetch([], run_id="maximum-shape")
    elapsed_ms = (perf_counter() - started) * 1000
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    assert len(transport.calls) == 2
    assert models.EventDossier.objects.count() == 8
    assert models.EventDossierSource.objects.count() == 8
    assert models.EventDossierClaim.objects.count() == 72
    assert models.CollectionEvidenceArchive.objects.filter(capture_kind="product_release_intake").count() == 8
    assert not models.Product.objects.exists()
    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="measurement")
    first = process_saved_findings()
    assert first["processed"] == 1 and first["unresolved"] == 8
    assert first["provider_calls"] == 0
    from core.product_release_detection_queue import enqueue_posts

    counts = (models.EventDossier.objects.count(), models.EventDossierClaim.objects.count(),
              models.CollectionEvidenceArchive.objects.count())
    enqueue_posts([state.pk])
    replay = process_saved_findings()
    assert replay["processed"] == 1 and replay["provider_calls"] == 0
    assert counts == (models.EventDossier.objects.count(), models.EventDossierClaim.objects.count(),
                      models.CollectionEvidenceArchive.objects.count())
    assert len(transport.calls) == 2
    receipt = {"kind": "synthetic maximum supported 8 findings x 8 assertions; local PostgreSQL",
               "publication_queries": len(queries), "publication_elapsed_ms": round(elapsed_ms, 3),
               "query_patterns": Counter(re.sub(r"'[^']*'|\b\d+\b", "?", row["sql"])
                                         for row in queries).most_common(20),
               "identity": first, "replay": replay, "dossiers": 8, "claims": 72,
               "physical_provider_requests": 0, "synthetic_transport_requests": len(transport.calls)}
    destination = Path(settings.BASE_DIR) / ".local/p1-resource-workload.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2))
