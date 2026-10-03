from app.schemas.daily_log import DailyLogRequest
from app.services.daily_log_service import DailyLogService


def test_structured_severe_symptoms_never_produce_reassurance():
    req = DailyLogRequest(log_date="2024-01-01", symptom_levels={"headache": 3, "fatigue": 3})
    hints = " ".join(DailyLogService._generate_advice(req))
    assert "头痛" in hints and "疲劳" in hints
    assert "医务" in hints
    assert "状态平稳" not in hints


def test_empty_record_is_not_health_assessment_and_diet_is_not_diagnosed():
    req = DailyLogRequest(log_date="2024-01-01", diet_tag="辛辣")
    hints = " ".join(DailyLogService._generate_advice(req))
    assert "不能用于判断" in hints
    assert "盆腔" not in hints


def test_hint_source_is_explicit(client, auth_header):
    body = client.post("/api/v1/daily_log", json={"log_date": "2024-01-01",
        "symptom_levels": {"fatigue": 3}}).json()
    assert body["advice_source"] == "rule_based"
    assert "疲劳" in " ".join(body["ai_health_advice"])
