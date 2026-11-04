"""Pin datasource backfill operations to the dedicated database, before effects."""
from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit

from django.db import connection

RESOURCE = 'dpg-dbfemu2vcj2c73fsafe0-a'
DATABASE = 'xbackfiller'
SCHEMA_FLOOR = '0221_affiliation_trigger_column_permissions'


def _backfill_host(host):
    return host in {RESOURCE, RESOURCE + '.oregon-postgres.render.com'}


def validate_backfill_target(*, database=None, environ=None, require_write=False):
    """Inspect only; never reconnect, change credentials, or migrate implicitly."""
    env = os.environ if environ is None else environ
    value = env.get('BACKFILL_DATABASE_URL')
    if not value:
        raise ValueError('backfill credential missing; set BACKFILL_DATABASE_URL explicitly')
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {'postgres', 'postgresql'}
                 and _backfill_host(parsed.hostname)
                 and unquote(parsed.path.lstrip('/')) == DATABASE
                 and unquote(parsed.username or '') == DATABASE
                 and parsed.port in {None, 5432})
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('backfill credential identity mismatch')
    db = connection if database is None else database
    configured = db.settings_dict
    if (not _backfill_host(configured.get('HOST'))
            or configured.get('NAME') != DATABASE
            or configured.get('USER') != DATABASE
            or str(configured.get('PORT') or 5432) != '5432'):
        raise ValueError('backfill connection identity mismatch')
    with db.cursor() as cursor:
        cursor.execute("SELECT current_database(),session_user,current_setting('transaction_read_only')")
        name, login, readonly = cursor.fetchone()
        if (name, login) != (DATABASE, DATABASE):
            raise ValueError('authenticated backfill identity mismatch')
        if require_write and readonly == 'on':
            raise ValueError('read-only backfill connection cannot collect')
        cursor.execute('SELECT EXISTS(SELECT 1 FROM django_migrations WHERE app=%s AND name=%s)',
                       ['core', SCHEMA_FLOOR])
        ready = bool(cursor.fetchone()[0])
    if require_write and not ready:
        raise ValueError('backfill schema upgrade required before collection')
    return {'resource': RESOURCE, 'database': name, 'login': login,
            'schema_ready': ready, 'required_migration': SCHEMA_FLOOR,
            'read_only': readonly == 'on'}
