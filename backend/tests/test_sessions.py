from db.models import StageAttempt
from tests.conftest import seed_sequence as _seed_sequence


def test_create_session_returns_first_stage(client, db_session):
    sequence = _seed_sequence(db_session)

    response = client.post(
        "/api/sessions", json={"sequence_id": sequence.id, "candidate_email": "gaurav@example.com"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["sequence_id"] == sequence.id
    assert body["candidate_email"] == "gaurav@example.com"
    assert body["status"] == "in_progress"
    assert body["current_stage"]["order_index"] == 1
    assert body["current_stage"]["stage_type"] == "anchor"
    assert body["current_stage"]["helper_locked"] is False


def test_create_session_precreates_all_five_stage_attempts(client, db_session):
    sequence = _seed_sequence(db_session)

    response = client.post("/api/sessions", json={"sequence_id": sequence.id})
    session_id = response.json()["id"]

    attempts = db_session.query(StageAttempt).filter(StageAttempt.session_id == session_id).all()
    assert len(attempts) == 5
    assert all(a.ready_at is None and a.score is None for a in attempts)


def test_create_session_without_email_is_optional(client, db_session):
    sequence = _seed_sequence(db_session)

    response = client.post("/api/sessions", json={"sequence_id": sequence.id})

    assert response.status_code == 201
    assert response.json()["candidate_email"] is None


def test_create_session_unknown_sequence_returns_404(client):
    response = client.post("/api/sessions", json={"sequence_id": 999})
    assert response.status_code == 404
