from unittest.mock import MagicMock
import smtplib

import pytest
from pydantic import SecretStr

from app.core import email
from app.core.config import settings


@pytest.mark.parametrize("security", ["starttls", "ssl"])
def test_transport_encrypts_authenticates_and_sends_without_logging_secrets(monkeypatch, security, caplog):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.fixture.invalid")
    monkeypatch.setattr(settings, "SMTP_FROM", "noreply@example.com")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "fixture-user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", SecretStr("fixture-app-secret"))
    monkeypatch.setattr(settings, "SMTP_SECURITY", security)
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {}
    plain, encrypted = MagicMock(return_value=smtp), MagicMock(return_value=smtp)
    monkeypatch.setattr(email.smtplib, "SMTP", plain)
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", encrypted)
    email.send_email("person@example.com", "Generic subject", "Body")
    assert encrypted.called is (security == "ssl")
    assert smtp.starttls.called is (security == "starttls")
    smtp.login.assert_called_once_with("fixture-user", "fixture-app-secret")
    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "person@example.com"
    assert "person@example.com" not in caplog.text and "fixture-app-secret" not in caplog.text


def test_transport_failure_does_not_expose_recipient(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.fixture.invalid")
    monkeypatch.setattr(settings, "SMTP_FROM", "noreply@example.com")
    def rejected(*args, **kwargs):
        raise smtplib.SMTPException("Private SMTP response for person@example.com")
    monkeypatch.setattr(email.smtplib, "SMTP", rejected)
    with pytest.raises(email.MailDeliveryError, match="Mail delivery failed") as error:
        email.send_email("person@example.com", "Subject", "Body")
    assert "person@example.com" not in str(error.value)


def test_production_refuses_plaintext_smtp(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.fixture.invalid")
    monkeypatch.setattr(settings, "SMTP_FROM", "noreply@example.com")
    monkeypatch.setattr(settings, "SMTP_SECURITY", "none")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    transport = MagicMock()
    monkeypatch.setattr(email.smtplib, "SMTP", transport)
    with pytest.raises(email.MailDeliveryError):
        email.send_email("person@example.com", "Subject", "Body")
    transport.assert_not_called()
