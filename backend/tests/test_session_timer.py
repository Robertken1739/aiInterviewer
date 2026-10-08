from datetime import datetime, timedelta

from db.models import Assessment, InterviewSession
from tests.conftest import seed_sequence


def _signup_and_login(client, path: str, email: str) -> dict:
    client.post(f"/api/{path}/signup", json={"email": email, "password": "pw"})
    token = client.post(f"/api/{path}/login", json={"email": email, "password": "pw"}).json()["auth_token"]
    return {"Authorization": f"Bearer {token}"}


def _joined_session(client, db_session, duration_minutes: int = 30) -> str:
    sequence = seed_sequence(db_session)
    recruiter_headers = _signup_and_login(client, "recruiters", "r@example.com")
    candidate_headers = _signup_and_login(client, "candidates", "cand@example.com")
    share_token = client.post(
        "/api/assessments",
        json={"sequence_id": sequence.id, "duration_minutes": duration_minutes},
        headers=recruiter_headers,
    ).json()["share_token"]
    session_id = client.post(
        "/api/assessments/join", json={"share_token": share_token}, headers=candidate_headers
    ).json()["id"]
    return session_id


def _expire(db_session, session_id: str) -> None:
    session = db_session.get(InterviewSession, session_id)
    session.started_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()


def test_helper_is_blocked_once_the_timer_expires(client, db_session, mock_llm):
    session_id = _joined_session(client, db_session, duration_minutes=30)
    _expire(db_session, session_id)

    response = client.post(f"/api/sessions/{session_id}/helper", json={"question": "hint?"})

    assert response.status_code == 409


def test_ready_is_blocked_once_the_timer_expires(client, db_session, mock_llm):
    session_id = _joined_session(client, db_session, duration_minutes=30)
    _expire(db_session, session_id)

    response = client.post(f"/api/sessions/{session_id}/ready")

    assert response.status_code == 409


def test_answer_still_succeeds_after_timer_expires_for_auto_submit(client, db_session, mock_llm):
    session_id = _joined_session(client, db_session, duration_minutes=30)
    client.post(f"/api/sessions/{session_id}/ready")
    _expire(db_session, session_id)

    response = client.post(f"/api/sessions/{session_id}/answer", json={"text": "whatever I had typed"})

    assert response.status_code == 200


def test_session_with_no_assessment_has_no_deadline(client, db_session):
    sequence = seed_sequence(db_session)

    session_id = client.post("/api/sessions", json={"sequence_id": sequence.id}).json()["id"]
    state = client.get(f"/api/sessions/{session_id}").json()

    assert state["deadline_at"] is None


def test_end_session_force_completes_with_partial_scores(client, db_session):
    session_id = _joined_session(client, db_session, duration_minutes=30)
    client.post(f"/api/sessions/{session_id}/ready")

    response = client.post(f"/api/sessions/{session_id}/end")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"

    results = client.get(f"/api/sessions/{session_id}/results").json()
    assert results["overall_score"] is None  # no stages scored yet
    assert all(r["score"] is None for r in results["stage_results"])


def test_end_session_twice_is_rejected(client, db_session):
    session_id = _joined_session(client, db_session, duration_minutes=30)

    assert client.post(f"/api/sessions/{session_id}/end").status_code == 200
    assert client.post(f"/api/sessions/{session_id}/end").status_code == 409
