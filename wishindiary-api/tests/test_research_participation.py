from app.core.database import transaction
from app.core.research_policy import POLICY_VERSION


def join(client, **changes):
    return client.put("/api/v1/research/participation", json={"participate": True,
        "policy_version": POLICY_VERSION, "adult_confirmed": True, **changes})


def test_consent_is_independent_explicit_versioned_and_idempotent(client, auth_header):
    assert client.get("/api/v1/research/participation").json()["participating"] is False
    assert join(client, adult_confirmed=False).status_code == 400
    assert join(client, policy_version="obsolete").status_code == 409
    assert join(client).status_code == 200
    assert join(client).status_code == 200
    data = client.get("/api/v1/research/participation").json()
    assert data["participating"] is True and data["decision_at"].endswith("+00:00")
    exported = client.get("/api/v1/user/export").json()
    assert len(exported["research_consent_events"]) == 1


def test_withdraw_rejoin_and_delete_preserve_personal_records_and_remove_events(client, auth_header):
    user_id = client.get("/api/v1/auth/session").json()["user_id"]
    assert join(client).status_code == 200
    assert client.post("/api/v1/daily_log", json={"log_date": "2024-01-01", "stress_level": 2}).status_code == 200
    assert client.put("/api/v1/research/background", json={"diagnosed_pcos": True}).status_code == 200
    assert client.put("/api/v1/research/participation", json={"participate": False}).status_code == 200
    assert client.get("/api/v1/research/participation").json()["participating"] is False
    assert client.get("/api/v1/daily_log?date=2024-01-01").status_code == 200
    assert join(client).status_code == 200
    events = client.get("/api/v1/user/export").json()["research_consent_events"]
    assert [row["action"] for row in events] == ["grant", "withdraw", "grant"]
    assert events[0]["episode_id"] != events[2]["episode_id"]
    assert client.delete("/api/v1/user/me").status_code == 200
    with transaction() as connection:
        with connection.cursor() as cursor:
            for table in ("research_consent_events", "research_background_revisions"):
                cursor.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=%s", (user_id,))
                assert cursor.fetchone()["n"] == 0


def test_background_unknowns_and_later_changes_are_preserved(client, auth_header):
    assert client.put("/api/v1/research/background", json={"pregnancy": False}).status_code == 200
    data = client.get("/api/v1/research/participation").json()["background"]
    assert data["fields"]["pregnancy"] is False
    assert data["fields"]["hormonal_contraception"] is None
    assert client.put("/api/v1/research/background", json={"pregnancy": True}).status_code == 200
    assert len(client.get("/api/v1/user/export").json()["research_background_revisions"]) == 2
    assert client.put("/api/v1/research/background", json={"diagnosed_pcos": "yes"}).status_code == 422
    assert client.put("/api/v1/research/background", json={"age_band": "under18"}).status_code == 200
    assert join(client).status_code == 400


def test_participation_routes_require_authentication(client):
    assert client.get("/api/v1/research/participation").status_code == 401
    assert join(client).status_code == 401
    assert client.put("/api/v1/research/background", json={}).status_code == 401
