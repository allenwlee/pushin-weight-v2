import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import HFModelCatalogRun, Product
from tests.test_hf_catalog_runner import api, scope

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_preview_makes_no_requests_or_writes(monkeypatch):
    scope()
    monkeypatch.setattr("httpx.Client", lambda **kw: pytest.fail("network in preview"))
    output = StringIO()
    call_command(
        "import_hf_product_catalog",
        brand="lab",
        confirmed_namespace="lab",
        stdout=output,
    )
    preview = json.loads(output.getvalue())
    assert preview["mode"] == "preview"
    assert preview["scope"]["namespaces"][0]["namespace"] == "lab"
    assert HFModelCatalogRun.objects.count() == Product.objects.count() == 0


def test_command_http_database_and_resume_chain(monkeypatch):
    scope()
    transport = api().client
    monkeypatch.setattr("httpx.Client", lambda **kw: transport)
    output = StringIO()
    with pytest.raises(CommandError) as exc:
        call_command(
            "import_hf_product_catalog",
            brand="lab",
            confirmed_namespace="lab",
            commit=True,
            max_requests=2,
            stdout=output,
        )
    assert exc.value.returncode == 2
    report = json.loads(output.getvalue())
    assert report["unique_models"] == 2 and not report["complete"]
    # A fresh transport is needed because the command owns its client context.
    monkeypatch.undo()
    transport = api().client
    monkeypatch.setattr("httpx.Client", lambda **kw: transport)
    output = StringIO()
    call_command(
        "import_hf_product_catalog", resume=report["run_id"], commit=True, stdout=output
    )
    assert json.loads(output.getvalue())["complete"]
    assert Product.objects.count() == 2
    assert Product.objects.first().downloads_all_time == 4_000_000_000


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"all_tracked": True, "brand": "lab"},
        {"brand": "lab"},
        {"resume": "bad"},
        {"all_tracked": True, "max_requests": 0},
        {"all_tracked": True, "max_seconds": float("nan")},
    ],
)
def test_invalid_options_fail_before_http(monkeypatch, kwargs):
    monkeypatch.setattr("httpx.Client", lambda **kw: pytest.fail("network"))
    with pytest.raises(CommandError):
        call_command("import_hf_product_catalog", **kwargs)
