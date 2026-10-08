from db.models import Candidate


def test_signup_creates_candidate_with_hashed_password(client, db_session):
    response = client.post("/api/candidates/signup", json={"email": "c@example.com", "password": "hunter2"})

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "c@example.com"
    assert "password" not in body
    assert "password_hash" not in body

    candidate = db_session.query(Candidate).filter_by(email="c@example.com").first()
    assert candidate.password_hash != "hunter2"


def test_signup_rejects_duplicate_email(client, db_session):
    client.post("/api/candidates/signup", json={"email": "c@example.com", "password": "hunter2"})

    response = client.post("/api/candidates/signup", json={"email": "c@example.com", "password": "other"})

    assert response.status_code == 409


def test_login_returns_auth_token(client, db_session):
    client.post("/api/candidates/signup", json={"email": "c@example.com", "password": "hunter2"})

    response = client.post("/api/candidates/login", json={"email": "c@example.com", "password": "hunter2"})

    assert response.status_code == 200
    assert response.json()["auth_token"]


def test_login_rejects_wrong_password(client, db_session):
    client.post("/api/candidates/signup", json={"email": "c@example.com", "password": "hunter2"})

    response = client.post("/api/candidates/login", json={"email": "c@example.com", "password": "wrong"})

    assert response.status_code == 401


def test_me_requires_valid_token(client, db_session):
    response = client.get("/api/candidates/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_logout_invalidates_the_token(client, db_session):
    client.post("/api/candidates/signup", json={"email": "c@example.com", "password": "hunter2"})
    token = client.post(
        "/api/candidates/login", json={"email": "c@example.com", "password": "hunter2"}
    ).json()["auth_token"]

    assert client.post("/api/candidates/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    assert client.get("/api/candidates/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


import pytest


@pytest.mark.parametrize(
    "email",
    ["@gmeel.com", "x@gmeel.com", "x@gmail.con", "a@b", "a@b.c", "a..b@x.com", ".a@x.com", "a@-x.com", "no-at-sign", "@"],
)
def test_signup_rejects_invalid_or_misspelled_email(client, db_session, email):
    response = client.post("/api/candidates/signup", json={"email": email, "password": "hunter2"})

    assert response.status_code == 422


def test_signup_and_login_normalize_email_case_and_whitespace(client, db_session):
    signup = client.post("/api/candidates/signup", json={"email": " Mixed@Example.COM ", "password": "hunter2"})
    assert signup.status_code == 201
    assert signup.json()["email"] == "mixed@example.com"

    login = client.post("/api/candidates/login", json={"email": "MIXED@example.com", "password": "hunter2"})
    assert login.status_code == 200
