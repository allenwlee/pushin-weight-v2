"""Pure connection-contract tests: no PostgreSQL or provider calls."""
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.data_source_backfill_target import validate_backfill_target

HOST = 'dpg-dbfemu2vcj2c73fsafe0-a.oregon-postgres.render.com'
URL = f'postgresql://xbackfiller:private-password@{HOST}/xbackfiller'


class Database:
    def __init__(self, *, name='xbackfiller', login='xbackfiller', readonly=False,
                 schema=True, host=HOST):
        self.settings_dict = {'HOST': host, 'NAME': name, 'USER': login, 'PORT': '5432'}
        self.identity = (name, login, 'on' if readonly else 'off')
        self.schema = schema
        self.queries = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchone(self):
        return self.identity if len(self.queries) == 1 else (self.schema,)


def test_missing_explicit_credential_never_uses_default_database():
    db = Database()
    with pytest.raises(ValueError, match='backfill credential missing'):
        validate_backfill_target(database=db, environ={})
    assert not db.queries


@pytest.mark.parametrize('name,host', [('pushinweight_shadow', HOST),
    ('xbackfiller', 'dpg-d9koekqjobas73fvjqng-a.oregon-postgres.render.com')])
def test_wrong_target_is_refused_before_connecting(name, host):
    db = Database(name=name, host=host)
    with pytest.raises(ValueError, match='backfill connection identity mismatch'):
        validate_backfill_target(database=db, environ={'BACKFILL_DATABASE_URL': URL})
    assert not db.queries


def test_authenticated_login_and_current_schema_are_verified():
    db = Database()
    result = validate_backfill_target(database=db, environ={'BACKFILL_DATABASE_URL': URL},
                                      require_write=True)
    assert result['database'] == 'xbackfiller'
    assert result['schema_ready'] is True
    assert len(db.queries) == 2
    assert 'session_user' in db.queries[0][0]


def test_readonly_inspection_can_report_old_schema_but_execution_cannot():
    db = Database(readonly=True, schema=False)
    result = validate_backfill_target(database=db, environ={'BACKFILL_DATABASE_URL': URL})
    assert result['schema_ready'] is False
    with pytest.raises(ValueError, match='read-only backfill connection'):
        validate_backfill_target(database=Database(readonly=True),
            environ={'BACKFILL_DATABASE_URL': URL}, require_write=True)
    with pytest.raises(ValueError, match='backfill schema upgrade required'):
        validate_backfill_target(database=Database(schema=False),
            environ={'BACKFILL_DATABASE_URL': URL}, require_write=True)


@pytest.mark.parametrize('command_name', ['backfiller_data_source', 'upgrade_data_source_backfill'])
def test_cli_rejects_missing_target_before_service_or_provider_access(monkeypatch, command_name):
    monkeypatch.delenv('BACKFILL_DATABASE_URL', raising=False)
    from core.management.commands import backfiller_data_source as command
    monkeypatch.setattr(command.service, 'report_campaign',
                        lambda **_: pytest.fail('service reached before target validation'))
    with pytest.raises(CommandError, match='backfill credential missing') as error:
        call_command(command_name, stdout=StringIO())
    assert 'private-password' not in str(error.value)
