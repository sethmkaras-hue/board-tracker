from unittest.mock import MagicMock

import pytest

from tracker import db, worker


def test_postgres_env_builds_url_without_credential_escaping(monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    settings = {
        "POSTGRES_HOST": "postgres.example.test",
        "POSTGRES_PORT": "5544",
        "POSTGRES_DB": "cards",
        "POSTGRES_USER": "board-owner",
        "POSTGRES_PASSWORD": "synthetic:p@ss/word#",
        "POSTGRES_SSLMODE": "verify-full",
        "POSTGRES_SSLROOTCERT": "/certs/postgres-ca.pem",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    url = db.database_url()
    assert (url.host, url.port, url.database, url.username) == ("postgres.example.test", 5544, "cards", "board-owner")
    assert url.password == settings["POSTGRES_PASSWORD"]
    assert url.query["sslmode"] == "verify-full"
    assert url.query["sslrootcert"] == "/certs/postgres-ca.pem"
    assert url.password not in str(url)


def test_smtp_starttls_modes(monkeypatch):
    relay = MagicMock()
    relay.__enter__.return_value = relay
    smtp = MagicMock(return_value=relay)
    monkeypatch.setattr(worker.smtplib, "SMTP", smtp)
    monkeypatch.delenv("SMTP_TLS", raising=False)
    monkeypatch.setenv("SMTP_HOST", "relay.example.test")
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    with worker.smtp_connection() as connection:
        assert connection is relay
    smtp.assert_called_once_with("relay.example.test", 25, timeout=15)
    relay.starttls.assert_not_called()
    relay.login.assert_not_called()

    monkeypatch.setenv("SMTP_USERNAME", "relay-user")
    monkeypatch.setenv("SMTP_PASSWORD", "synthetic")
    with pytest.raises(ValueError, match="require TLS"), worker.smtp_connection():
        pytest.fail("Refuse plain authentication before connecting")
    assert smtp.call_count == 1

    monkeypatch.setenv("SMTP_STARTTLS", "true")
    with worker.smtp_connection():
        relay.starttls.assert_called_once()
        relay.login.assert_called_once_with("relay-user", "synthetic")
