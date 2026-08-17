"""Rotating the field key must not be a one-way trip."""

import pytest

from app.core.config import settings
from app.core.field_encryption import FieldDecryptionError, decrypt_field, encrypt_field


def test_data_written_before_the_split_is_still_readable(monkeypatch: pytest.MonkeyPatch):
    """Every existing database was encrypted with a key derived from SECRET_KEY.

    Introducing a separate setting must not orphan that data, so an empty
    FIELD_ENCRYPTION_KEY has to keep meaning exactly what it meant before.
    """
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_PREVIOUS_KEYS", [])
    sealed = encrypt_field("клиент")

    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", settings.SECRET_KEY)
    assert decrypt_field(sealed) == "клиент"


def test_a_previous_key_still_opens_what_it_sealed(monkeypatch: pytest.MonkeyPatch):
    """The point of the change: a rotation that leaves the data readable.

    Without the previous key listed, everything already stored becomes noise the
    moment the key changes — which is how one unreadable customer took down a whole
    section, and there is no way back from it.
    """
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", "the-old-key")
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_PREVIOUS_KEYS", [])
    sealed = encrypt_field("+7 999 000-00-00")

    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", "the-new-key")
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_PREVIOUS_KEYS", ["the-old-key"])
    assert decrypt_field(sealed) == "+7 999 000-00-00"

    # And what is written now is sealed with the new key, so dropping the old one
    # later costs only the records nobody has rewritten yet.
    resealed = encrypt_field("+7 999 000-00-00")
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_PREVIOUS_KEYS", [])
    assert decrypt_field(resealed) == "+7 999 000-00-00"


def test_dropping_a_key_still_in_use_is_not_silent(monkeypatch: pytest.MonkeyPatch):
    """Losing the key that sealed a value must fail loudly, not return emptiness."""
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", "the-old-key")
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_PREVIOUS_KEYS", [])
    sealed = encrypt_field("ИНН")

    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", "the-new-key")
    with pytest.raises(FieldDecryptionError):
        decrypt_field(sealed)
