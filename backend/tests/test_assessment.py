from tests.conftest import seed_sequence


def _signup_and_login_recruiter(client, email: str = "r@example.com") -> dict:
    client.post("/api/recruiters/signup", json={"email": email, "password": "pw"})
    token = client.post("/api/recruiters/login", json={"email": email, "password": "pw"}).json()["auth_token"]
    return {"Authorization": f"Bearer {token}"}


def _signup_and_login_candidate(client, email: str = "cand@example.com") -> dict:
    client.post("/api/candidates/signup", json={"email": email, "password": "pw"})
    token = client.post("/api/candidates/login", json={"email": email, "password": "pw"}).json()["auth_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_assessment_returns_share_token_and_sequence_title(client, db_session):
    sequence = seed_sequence(db_session)
    headers = _signup_and_login_recruiter(client)

    response = client.post(
        "/api/assessments", json={"sequence_id": sequence.id, "duration_minutes": 30}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["sequence_title"] == sequence.title
    assert body["duration_minutes"] == 30
    assert body["share_token"]
    assert body["closed_at"] is None


def test_create_assessment_requires_recruiter_auth(client, db_session):
    sequence = seed_sequence(db_session)

    response = client.post("/api/assessments", json={"sequence_id": sequence.id, "duration_minutes": 30})

    assert response.status_code == 422  # missing Authorization header


def test_list_assessments_returns_only_own(client, db_session):
    sequence = seed_sequence(db_session)
    headers_a = _signup_and_login_recruiter(client, "a@example.com")
    headers_b = _signup_and_login_recruiter(client, "b@example.com")
    client.post("/api/assessments", json={"sequence_id": sequence.id, "duration_minutes": 30}, headers=headers_a)

    response = client.get("/api/assessments", headers=headers_b)

    assert response.status_code == 200
    assert response.json() == []


def test_get_assessment_rejects_non_owner(client, db_session):
    sequence = seed_sequence(db_session)
    headers_a = _signup_and_login_recruiter(client, "a@example.com")
    headers_b = _signup_and_login_recruiter(client, "b@example.com")
    assessment_id = client.post(
        "/api/assessments", json={"sequence_id": sequence.id, "duration_minutes": 30}, headers=headers_a
    ).json()["id"]

    response = client.get(f"/api/assessments/{assessment_id}", headers=headers_b)

    assert response.status_code == 403


def test_close_assessment_sets_closed_at(client, db_session):
    sequence = seed_sequence(db_session)
    headers = _signup_and_login_recruiter(client)
    assessment_id = client.post(
        "/api/assessments", json={"sequence_id": sequence.id, "duration_minutes": 30}, headers=headers
    ).json()["id"]

    response = client.post(f"/api/assessments/{assessment_id}/close", headers=headers)

    assert response.status_code == 200
    assert response.json()["closed_at"] is not None


def test_list_sequences_requires_recruiter_auth_and_returns_seeded(client, db_session):
    sequence = seed_sequence(db_session)
    headers = _signup_and_login_recruiter(client)

    response = client.get("/api/sequences", headers=headers)

    assert response.status_code == 200
    assert {"id": sequence.id, "title": sequence.title} in response.json()


def test_join_creates_session_and_is_idempotent(client, db_session):
    sequence = seed_sequence(db_session)
    recruiter_headers = _signup_and_login_recruiter(client)
    candidate_headers = _signup_and_login_candidate(client)
    share_token = client.post(
        "/api/assessments", json={"sequence_id": sequence.id, "duration_minutes": 30}, headers=recruiter_headers
    ).json()["share_token"]

    first = client.post("/api/assessments/join", json={"share_token": share_token}, headers=candidate_headers)
    second = client.post("/api/assessments/join", json={"share_token": share_token}, headers=candidate_headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["deadline_at"] is not None


def test_join_rejects_after_close(client, db_session):
    sequence = seed_sequence(db_session)
    recruiter_headers = _signup_and_login_recruiter(client)
    candidate_headers = _signup_and_login_candidate(client)
    assessment = client.post(
        "/api/assessments", json={"sequence_id": sequence.id, "duration_minutes": 30}, headers=recruiter_headers
    ).json()
    client.post(f"/api/assessments/{assessment['id']}/close", headers=recruiter_headers)

    response = client.post(
        "/api/assessments/join", json={"share_token": assessment["share_token"]}, headers=candidate_headers
    )

    assert response.status_code == 409


def test_assessment_sessions_lists_joined_candidates(client, db_session):
    sequence = seed_sequence(db_session)
    recruiter_headers = _signup_and_login_recruiter(client)
    candidate_headers = _signup_and_login_candidate(client)
    assessment = client.post(
        "/api/assessments", json={"sequence_id": sequence.id, "duration_minutes": 30}, headers=recruiter_headers
    ).json()
    client.post("/api/assessments/join", json={"share_token": assessment["share_token"]}, headers=candidate_headers)

    response = client.get(f"/api/assessments/{assessment['id']}/sessions", headers=recruiter_headers)

    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["candidate_email"] == "cand@example.com"
    assert sessions[0]["status"] == "in_progress"
