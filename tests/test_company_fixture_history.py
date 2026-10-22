"""Migration fixtures use the company label owner from their own schema."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from tests.collection_fixtures import historical_fixture_models
from tests.company_factory import company_with_label

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BRIDGE = ("core", "0089_job_owned_run_instructions")


@pytest.mark.parametrize("migration_rehearsal_schema", [BRIDGE], indirect=True)
def test_company_fixture_and_collection_setup_follow_the_historical_label_owner(
    migration_rehearsal_schema,
):
    historical = MigrationExecutor(connection).loader.project_state([BRIDGE]).apps
    with historical_fixture_models(historical):
        company = company_with_label("historical-company", "Retained old name")
        assert type(company) is historical.get_model("core", "Company")
        assert company.display_name == "Retained old name"

        # Exercise the original failing setup chain, not only the factory.
        from tests.test_benchmark_download_persistence import configured

        contract = configured()
        assert contract.pk
        assert historical.get_model("core", "Company").objects.get(
            pk="lab"
        ).display_name == "Lab"
