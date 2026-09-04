"""daily_logs 新增自记录维度（睡眠/熬夜、用药、症状明细）+ GET/PUT/DELETE 接口测试。

覆盖：
- 新字段写入与回读（含缺省默认值、upsert 覆盖）；
- 校验边界：sleep_duration=1441 拒绝 / 1440 接受、sleep_quality 越界拒绝、
  symptom_levels 非法键 / 越界 / 非整型拒绝、medication_note 超长拒绝；
- GET 单日查询（无记录 404）、PUT 幂等覆盖、DELETE（无记录 404）。
"""

from datetime import date, timedelta

TODAY = date.today()
D = TODAY.isoformat()
PREV = (TODAY - timedelta(days=1)).isoformat()
FUTURE = (TODAY + timedelta(days=5)).isoformat()

FULL_SYMPTOMS = {
    "headache": 0,
    "bloat": 0,
    "breast_tenderness": 0,
    "fatigue": 0,
}

BASE = {
    "log_date": D,
    "mood_level": 2,
    "cramps_severity": 1,
}


def _create(client, payload):
    resp = client.post("/api/v1/daily_log", json=payload)
    assert resp.status_code == 200, resp.text
    return resp


def _get_log(client, date_str=D):
    resp = client.get(f"/api/v1/daily_log?date={date_str}")
    assert resp.status_code == 200, resp.text
    return resp.json()["log"]


class TestSleepMedicationSymptomPersistence:
    def test_defaults_zero_on_empty_submit(self, client, auth_header):
        _create(client, BASE)
        log = _get_log(client)
        assert log["sleep_duration_minutes"] == 0
        assert log["sleep_quality"] == 0
        assert log["is_late_night"] is False
        assert log["is_medication"] is False
        assert log["medication_note"] is None
        assert log["symptom_levels"] == FULL_SYMPTOMS

    def test_write_and_read_new_fields(self, client, auth_header):
        payload = {
            **BASE,
            "sleep_duration_minutes": 420,
            "sleep_quality": 3,
            "is_late_night": True,
            "is_medication": True,
            "medication_note": "布洛芬 200mg 睡前",
            "symptom_levels": {"headache": 2, "fatigue": 3},
        }
        _create(client, payload)
        log = _get_log(client)
        assert log["sleep_duration_minutes"] == 420
        assert log["sleep_quality"] == 3
        assert log["is_late_night"] is True
        assert log["is_medication"] is True
        assert log["medication_note"] == "布洛芬 200mg 睡前"
        # 仅传部分症状键时，缺失键服务端补 0
        assert log["symptom_levels"] == {"headache": 2, "bloat": 0, "breast_tenderness": 0, "fatigue": 3}

    def test_upsert_overwrites_fields(self, client, auth_header):
        _create(client, {**BASE, "sleep_duration_minutes": 300, "is_late_night": False})
        _create(client, {**BASE, "sleep_duration_minutes": 480, "is_late_night": True})
        log = _get_log(client)
        assert log["sleep_duration_minutes"] == 480
        assert log["is_late_night"] is True


class TestValidationBoundaries:
    def test_sleep_duration_1441_rejected(self, client, auth_header):
        resp = client.post("/api/v1/daily_log", json={**BASE, "sleep_duration_minutes": 1441})
        assert resp.status_code == 422

    def test_sleep_duration_1440_accepted(self, client, auth_header):
        resp = client.post("/api/v1/daily_log", json={**BASE, "sleep_duration_minutes": 1440})
        assert resp.status_code == 200

    def test_sleep_duration_negative_rejected(self, client, auth_header):
        resp = client.post("/api/v1/daily_log", json={**BASE, "sleep_duration_minutes": -1})
        assert resp.status_code == 422

    def test_sleep_quality_out_of_range_rejected(self, client, auth_header):
        resp = client.post("/api/v1/daily_log", json={**BASE, "sleep_quality": 4})
        assert resp.status_code == 422

    def test_symptom_unknown_key_rejected(self, client, auth_header):
        resp = client.post(
            "/api/v1/daily_log",
            json={**BASE, "symptom_levels": {"headache": 1, "nausea": 2}},
        )
        assert resp.status_code == 422
        assert "symptom_levels" in str(resp.json())

    def test_symptom_level_out_of_range_rejected(self, client, auth_header):
        resp = client.post("/api/v1/daily_log", json={**BASE, "symptom_levels": {"headache": 9}})
        assert resp.status_code == 422
        assert "symptom_levels" in str(resp.json())

    def test_symptom_non_int_rejected(self, client, auth_header):
        resp = client.post(
            "/api/v1/daily_log",
            json={**BASE, "symptom_levels": {"headache": "heavy"}},
        )
        assert resp.status_code == 422

    def test_medication_note_too_long_rejected(self, client, auth_header):
        resp = client.post("/api/v1/daily_log", json={**BASE, "medication_note": "x" * 101})
        assert resp.status_code == 422

    def test_medication_note_100_accepted(self, client, auth_header):
        _create(client, {**BASE, "medication_note": "x" * 100})
        assert _get_log(client)["medication_note"] == "x" * 100


class TestGetPutDelete:
    def test_get_missing_log_returns_404(self, client, auth_header):
        resp = client.get(f"/api/v1/daily_log?date={PREV}")
        assert resp.status_code == 404

    def test_put_creates_then_overwrites(self, client, auth_header):
        put1 = {"log_date": D, "is_medication": True, "medication_note": "维生素 D"}
        resp = client.put("/api/v1/daily_log", json=put1)
        assert resp.status_code == 200, resp.text
        log = _get_log(client)
        assert log["is_medication"] is True
        assert log["medication_note"] == "维生素 D"
        assert log["mood_level"] == 0  # 未传字段走默认

        put2 = {
            "log_date": D,
            "is_medication": False,
            "sleep_duration_minutes": 600,
            "symptom_levels": {"bloat": 1},
        }
        resp = client.put("/api/v1/daily_log", json=put2)
        assert resp.status_code == 200
        log = _get_log(client)
        assert log["is_medication"] is False
        assert log["medication_note"] is None
        assert log["sleep_duration_minutes"] == 600
        assert log["symptom_levels"] == {"headache": 0, "bloat": 1, "breast_tenderness": 0, "fatigue": 0}

    def test_delete_then_get_404(self, client, auth_header):
        _create(client, BASE)
        resp = client.delete(f"/api/v1/daily_log?date={D}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert client.get(f"/api/v1/daily_log?date={D}").status_code == 404

    def test_delete_missing_log_returns_404(self, client, auth_header):
        resp = client.delete(f"/api/v1/daily_log?date={PREV}")
        assert resp.status_code == 404

    def test_future_date_rejected(self, client, auth_header):
        resp = client.post("/api/v1/daily_log", json={**BASE, "log_date": FUTURE})
        assert resp.status_code == 400
