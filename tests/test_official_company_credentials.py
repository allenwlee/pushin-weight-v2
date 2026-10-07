from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from core.models import OfficialCompanyOwnerCredential
from core.official_company_credentials import OwnerTokenStore
from core.official_company_lists import XListError

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_rotation_saves_both_tokens_encrypted_and_next_process_reads_them():
    key = Fernet.generate_key()
    store = OwnerTokenStore(key=key, client_id="client", client_secret="client-secret")
    store.provision(access_token="old-access", refresh_token="old-refresh")
    response = Mock(status_code=200)
    response.json.return_value = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 7200,
        "scope": "tweet.read users.read list.read list.write offline.access",
    }
    request = Mock(return_value=response)
    assert store.refresh(request=request) == "new-access"
    row = OfficialCompanyOwnerCredential.objects.get()
    assert b"new-access" not in bytes(row.encrypted_tokens)
    assert b"new-refresh" not in bytes(row.encrypted_tokens)
    fresh = OwnerTokenStore(key=key, client_id="client", client_secret="client-secret")
    assert fresh.load()["refresh_token"] == "new-refresh"
    assert fresh.load()["expires_at"] > 0


def test_failed_or_ambiguous_refresh_blocks_repeated_refresh_attempts():
    store = OwnerTokenStore(
        key=Fernet.generate_key(), client_id="client", client_secret="secret"
    )
    store.provision(access_token="old-access", refresh_token="old-refresh")
    request = Mock(side_effect=TimeoutError())
    with pytest.raises(XListError, match="refresh_failed"):
        store.refresh(request=request)
    with pytest.raises(XListError, match="credential_blocked"):
        store.refresh(request=request)
    assert request.call_count == 1


def test_wrong_key_or_client_cannot_read_and_refresh_other_app_tokens():
    key = Fernet.generate_key()
    store = OwnerTokenStore(key=key, client_id="client", client_secret="secret")
    store.provision(access_token="access", refresh_token="refresh")
    with pytest.raises(XListError, match="credential_decryption"):
        OwnerTokenStore(
            key=Fernet.generate_key(), client_id="client", client_secret="secret"
        ).load()
    with pytest.raises(XListError, match="credential_client_mismatch"):
        OwnerTokenStore(key=key, client_id="different", client_secret="secret").load()
