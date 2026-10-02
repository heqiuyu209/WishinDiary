"""Exercise serialized logging output, including the audit message body."""

import json
import logging
from unittest.mock import patch

from app.core.audit import audit, audit_logger
from app.core.logging_config import _build_json_formatter


def test_json_output_filters_unknown_extras_and_retains_metrics():
    record = logging.getLogger("wishindiary.fixture").makeRecord(
        "wishindiary.fixture", logging.INFO, __file__, 1, "safe fixture event", (), None,
        extra={"request_id": "fixture-id", "status": 200, "metric": "http_request",
               "email": "synthetic@example.test", "password": "synthetic-password",
               "token": "synthetic-token", "journal_text": "synthetic private text"},
    )
    rendered = _build_json_formatter().format(record)
    payload = json.loads(rendered)
    assert payload["request_id"] == "fixture-id"
    assert payload["status"] == 200
    assert payload["metric"] == "http_request"
    assert payload["message"] == "safe fixture event"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "wishindiary.fixture"
    assert "ts" in payload
    for field in ("email", "password", "token", "journal_text"):
        assert field not in payload
    assert "synthetic-password" not in rendered


def test_dictionary_message_cannot_bypass_extra_whitelist():
    record = logging.getLogger("wishindiary.fixture").makeRecord(
        "wishindiary.fixture", logging.INFO, __file__, 1,
        {"message": "safe structured event", "metric": "fixture",
         "email": "synthetic@example.test", "refresh_token": "synthetic-token"}, (), None,
    )
    rendered = _build_json_formatter().format(record)
    assert json.loads(rendered)["metric"] == "fixture"
    assert "synthetic@example.test" not in rendered
    assert "synthetic-token" not in rendered


def test_audit_details_filter_health_dates_and_sensitive_text_before_formatting():
    with patch.object(audit_logger, "info") as captured:
        audit("cycle.update", actor_user_id=7, details={
            "cycle_id": 12, "start_date": "2024-01-01", "end_date": "2024-01-05",
            "email": "synthetic@example.test", "password": "synthetic-password",
            "journal_text": "synthetic private text", "nested": {"token": "synthetic-token"},
        })
    message = captured.call_args.args[0]
    payload = json.loads(message)
    assert payload["action"] == "cycle.update"
    assert payload["actor_user_id"] == 7
    assert payload["details"] == {"cycle_id": 12}
    assert "2024-01-01" not in message
    assert "synthetic" not in message


def test_audit_rejects_sensitive_values_disguised_as_identifier():
    with patch.object(audit_logger, "info") as captured:
        audit("cycle.update", details={"cycle_id": "synthetic-password"})
    assert json.loads(captured.call_args.args[0])["details"] == {}
