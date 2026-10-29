from datetime import timedelta
import re

import pytest

from app.core.config import settings
from app.core.database import transaction
from app.core.email import MailDeliveryError
from app.services import notification_service


@pytest.fixture
def outbox(monkeypatch):
    messages = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.fixture.invalid")
    monkeypatch.setattr(settings, "SMTP_FROM", "noreply@example.com")
    monkeypatch.setattr(notification_service, "send_email", lambda recipient, subject, body: messages.append((recipient, subject, body)))
    return messages


def _request(client, email="alice@example.com"):
    return client.post("/api/v1/notifications/email/request", json={"email": email})


def _code(outbox):
    return re.search(r"\b([0-9]{6})\b", outbox[-1][2]).group(1)


def test_binding_is_verified_and_reminders_are_opt_in(client, auth_header, outbox):
    initial = client.get("/api/v1/notifications/settings").json()
    assert initial["email"] is None and initial["enabled"] is False
    assert initial["lead_days"] == 2
    assert client.put("/api/v1/notifications/settings", json={"enabled": True}).status_code == 400
    response = _request(client)
    assert response.status_code == 200
    assert _code(outbox) not in response.text
    assert client.get("/api/v1/notifications/settings").json()["pending_email"] == "alice@example.com"
    assert client.post("/api/v1/notifications/email/verify", json={"code": _code(outbox)}).status_code == 200
    prefs = client.get("/api/v1/notifications/settings").json()
    assert prefs["email_verified"] is True and prefs["enabled"] is False
    assert client.put("/api/v1/notifications/settings", json={"enabled": True, "lead_days": 3, "timezone": "UTC"}).status_code == 200
    assert client.get("/api/v1/notifications/settings").json()["enabled"] is True
    assert client.delete("/api/v1/notifications/email").status_code == 200
    prefs = client.get("/api/v1/notifications/settings").json()
    assert prefs["email"] is None and prefs["enabled"] is False


def test_wrong_attempts_persist_and_code_cannot_be_replayed(client, auth_header, outbox):
    assert _request(client).status_code == 200
    correct = _code(outbox)
    wrong = "111111" if correct != "111111" else "222222"
    for _ in range(5):
        assert client.post("/api/v1/notifications/email/verify", json={"code": wrong}).status_code == 400
    assert client.post("/api/v1/notifications/email/verify", json={"code": correct}).status_code == 400
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT attempts, code_hash FROM email_verifications")
            row = cursor.fetchone()
            assert row["attempts"] == 5
            assert row["code_hash"] != correct


def test_verification_code_expiry_and_resend_cooldown(client, auth_header, outbox, monkeypatch):
    assert _request(client).status_code == 200
    assert _request(client).status_code == 429
    correct = _code(outbox)
    now = notification_service._utc_now()
    monkeypatch.setattr(notification_service, "_utc_now", lambda: now + timedelta(minutes=11))
    assert client.post("/api/v1/notifications/email/verify", json={"code": correct}).status_code == 400
    assert _request(client).status_code == 200
    assert client.post("/api/v1/notifications/email/verify", json={"code": _code(outbox)}).status_code == 200
    assert client.post("/api/v1/notifications/email/verify", json={"code": _code(outbox)}).status_code == 400


def test_disabled_mail_or_delivery_failure_has_no_pending_binding(client, auth_header, monkeypatch, outbox):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert _request(client).status_code == 503
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.fixture.invalid")
    def failed(*args):
        raise MailDeliveryError("fixture failure")
    monkeypatch.setattr(notification_service, "send_email", failed)
    assert _request(client).status_code == 503
    assert client.get("/api/v1/notifications/settings").json()["pending_email"] is None


def test_verified_email_can_login_and_is_unique(client, auth_header, outbox):
    assert _request(client).status_code == 200
    assert client.post("/api/v1/notifications/email/verify", json={"code": _code(outbox)}).status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.post("/api/v1/auth/login", json={"username": "ALICE@example.com", "password": "password123"}).status_code == 200
    assert client.get("/api/v1/auth/session").json()["username"] == "test_user"
    assert client.post("/api/v1/auth/logout").status_code == 200
    new = {"username": "another_user", "password": "password123"}
    assert client.post("/api/v1/auth/register", json=new).status_code == 200
    assert client.post("/api/v1/auth/login", json=new).status_code == 200
    assert _request(client).status_code == 409


def test_registration_email_does_not_block_account_when_delivery_fails(client, outbox, monkeypatch):
    def failed(*args):
        raise MailDeliveryError("fixture failure")
    monkeypatch.setattr(notification_service, "send_email", failed)
    payload = {"username": "register_email", "password": "password123", "email": "new@example.com"}
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 200
    assert response.json()["email_verification_required"] is True
    assert response.json()["email_verification_sent"] is False
    assert client.post("/api/v1/auth/login", json=payload).status_code == 200


def test_invalid_timezone_and_lead_days_are_rejected(client, auth_header):
    assert client.put("/api/v1/notifications/settings", json={"enabled": False, "timezone": "invalid/zone"}).status_code == 422
    assert client.put("/api/v1/notifications/settings", json={"enabled": False, "lead_days": 9}).status_code == 422


def test_deleted_account_removes_pending_codes(client, auth_header, outbox):
    assert _request(client).status_code == 200
    assert client.delete("/api/v1/user/me").status_code == 200
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM email_verifications")
            assert cursor.fetchone()["n"] == 0
