from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import pytest

from app.core.config import settings
from app.core.database import transaction
from app.core.email import MailDeliveryError
from app.services import reminder_service
from app.services.prediction_service import PredictionService
from app.services.reminder_service import ReminderService, plan_reminder

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
START = date(2026, 9, 4)


class FakePrediction:
    next_start = "2026-10-02"

    def get_prediction(self, user_id, *, record=True):
        assert record is False
        return {"status": "success", "prediction": {
            "last_period_start": START.isoformat(), "next_period_start": self.next_start,
        }}


@pytest.fixture
def subscriber(client, auth_header, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.fixture.invalid")
    monkeypatch.setattr(settings, "SMTP_FROM", "noreply@example.com")
    user_id = client.get("/api/v1/auth/session").json()["user_id"]
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE users SET email='subscriber@example.com', email_verified_at=UTC_TIMESTAMP(), reminder_enabled=1, notification_timezone='UTC' WHERE user_id=%s", (user_id,))
            cursor.execute("INSERT INTO cycles (user_id, start_date) VALUES (%s,%s)", (user_id, START))
    return user_id


@pytest.fixture
def mail(monkeypatch):
    messages = []
    monkeypatch.setattr(reminder_service, "send_email", lambda *args: messages.append(args))
    return messages


def rows(table):
    assert table in {"reminder_deliveries", "prediction_logs"}
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table}")
            return list(cursor.fetchall())


def test_preview_uses_real_basic_prediction_without_db_or_monitor_writes(subscriber, mail, monkeypatch):
    from app.core import metrics
    from app.ml import monitoring
    monkeypatch.setattr(metrics, "record_model_inference", lambda **kwargs: pytest.fail("Preview recorded metrics"))
    monkeypatch.setattr(monitoring, "record_prediction", lambda **kwargs: pytest.fail("Preview wrote monitor data"))
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO cycles (user_id, start_date, end_date, cycle_length, bleeding_days) VALUES (%s,'2026-08-07','2026-09-04',28,5)", (subscriber,))
    summary = ReminderService(PredictionService(predictor=object())).run_once(now=NOW)
    assert summary["due"] == 1
    assert rows("reminder_deliveries") == rows("prediction_logs") == []
    assert mail == []


def test_sends_once_per_cycle_even_after_prediction_changes(subscriber, mail):
    predictor = FakePrediction()
    service = ReminderService(predictor)
    assert service.run_once(send=True, now=NOW)["sent"] == 1
    assert service.run_once(send=True, now=NOW)["sent"] == 0
    predictor.next_start = "2026-10-03"
    assert service.run_once(send=True, now=NOW.replace(day=1, month=10))["sent"] == 0
    assert len(mail) == 1
    assert rows("reminder_deliveries")[0]["state"] == "sent"
    assert "2026-10-02" not in mail[0][2] and START.isoformat() not in mail[0][2]


def test_two_workers_cannot_deliver_the_same_cycle(subscriber, mail):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: ReminderService(FakePrediction()).run_once(send=True, now=NOW), range(2)))
    assert sum(result["sent"] for result in results) == 1
    assert sum(result["errors"] for result in results) == 0
    assert len(mail) == len(rows("reminder_deliveries")) == 1


def test_due_date_uses_account_timezone(subscriber, mail):
    moment = datetime(2026, 9, 29, 16, 5, tzinfo=timezone.utc)
    service = ReminderService(FakePrediction())
    assert service.run_once(send=True, now=moment)["sent"] == 0
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE users SET notification_timezone='Asia/Shanghai' WHERE user_id=%s", (subscriber,))
    assert service.run_once(send=True, now=moment)["sent"] == 1
    assert len(mail) == 1


@pytest.mark.parametrize("change", ["reminder_enabled=0", "email_verified_at=NULL", "email=NULL"])
def test_opt_out_or_unverified_account_is_excluded(subscriber, mail, change):
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"UPDATE users SET {change} WHERE user_id=%s", (subscriber,))
    result = ReminderService(FakePrediction()).run_once(send=True, now=NOW)
    assert result["checked"] == result["sent"] == 0
    assert mail == []


def test_new_actual_start_between_prediction_and_claim_suppresses_mail(subscriber, mail):
    class ChangedHistory(FakePrediction):
        def get_prediction(self, user_id, *, record=True):
            with transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("INSERT INTO cycles (user_id, start_date) VALUES (%s,'2026-09-29')", (user_id,))
            return super().get_prediction(user_id, record=record)
    result = ReminderService(ChangedHistory()).run_once(send=True, now=NOW)
    assert result["skipped"] == 1 and result["sent"] == 0
    assert mail == rows("reminder_deliveries") == []


def test_opt_out_after_claim_cancels_without_smtp(subscriber, mail, monkeypatch):
    service = ReminderService(FakePrediction())
    original = service._send_claimed
    def opt_out_then_send(*args):
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE users SET reminder_enabled=0 WHERE user_id=%s", (subscriber,))
        return original(*args)
    monkeypatch.setattr(service, "_send_claimed", opt_out_then_send)
    assert service.run_once(send=True, now=NOW)["canceled"] == 1
    assert mail == []
    assert rows("reminder_deliveries")[0]["state"] == "canceled"


def test_uncertain_smtp_delivery_is_not_retried(subscriber, monkeypatch):
    attempts = []
    def uncertain(*args):
        attempts.append(args)
        raise MailDeliveryError("Acknowledgement lost")
    monkeypatch.setattr(reminder_service, "send_email", uncertain)
    service = ReminderService(FakePrediction())
    assert service.run_once(send=True, now=NOW)["unknown"] == 1
    assert rows("reminder_deliveries")[0]["state"] == "unknown"
    assert service.run_once(send=True, now=NOW)["skipped"] == 1
    assert len(attempts) == 1


def test_process_failure_keeps_committed_claim_and_prevents_resend(subscriber, mail, monkeypatch):
    service = ReminderService(FakePrediction())
    def crash(*args):
        raise RuntimeError("Process stopped before SMTP acknowledgement")
    monkeypatch.setattr(service, "_send_claimed", crash)
    assert service.run_once(send=True, now=NOW)["errors"] == 1
    assert rows("reminder_deliveries")[0]["state"] == "sending"
    assert ReminderService(FakePrediction()).run_once(send=True, now=NOW)["sent"] == 0
    assert mail == []


@pytest.mark.parametrize("next_start", ["2026-09-30", "2026-09-29", "2026-10-01", "2026-10-03"])
def test_expired_or_non_due_prediction_is_not_sent(subscriber, mail, next_start):
    prediction = FakePrediction()
    prediction.next_start = next_start
    assert ReminderService(prediction).run_once(send=True, now=NOW)["sent"] == 0
    assert mail == []


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        plan_reminder({}, {}, datetime(2026, 9, 30))


def test_missing_smtp_fails_before_claiming(subscriber, mail, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    with pytest.raises(MailDeliveryError):
        ReminderService(FakePrediction()).run_once(send=True, now=NOW)
    assert mail == rows("reminder_deliveries") == []


def test_account_deletion_removes_delivery_history(client, subscriber, mail):
    assert ReminderService(FakePrediction()).run_once(send=True, now=NOW)["sent"] == 1
    assert client.delete("/api/v1/user/me").status_code == 200
    assert rows("reminder_deliveries") == []
