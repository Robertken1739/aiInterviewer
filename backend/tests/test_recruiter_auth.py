from db.models import Recruiter


def test_signup_creates_recruiter_with_hashed_password(client, db_session):
    response = client.post("/api/recruiters/signup", json={"email": "r@example.com", "password": "hunter2"})

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "r@example.com"
    assert "password" not in body
    assert "password_hash" not in body

    recruiter = db_session.query(Recruiter).filter_by(email="r@example.com").first()
    assert recruiter.password_hash != "hunter2"


def test_signup_rejects_duplicate_email(client, db_session):
    client.post("/api/recruiters/signup", json={"email": "r@example.com", "password": "hunter2"})

    response = client.post("/api/recruiters/signup", json={"email": "r@example.com", "password": "other"})

    assert response.status_code == 409


def test_login_returns_auth_token(client, db_session):
    client.post("/api/recruiters/signup", json={"email": "r@example.com", "password": "hunter2"})

    response = client.post("/api/recruiters/login", json={"email": "r@example.com", "password": "hunter2"})

    assert response.status_code == 200
    assert response.json()["auth_token"]


def test_login_rejects_wrong_password(client, db_session):
    client.post("/api/recruiters/signup", json={"email": "r@example.com", "password": "hunter2"})

    response = client.post("/api/recruiters/login", json={"email": "r@example.com", "password": "wrong"})

    assert response.status_code == 401


def test_login_rejects_unknown_email(client, db_session):
    response = client.post("/api/recruiters/login", json={"email": "nobody@example.com", "password": "x"})

    assert response.status_code == 401


def test_me_requires_valid_token(client, db_session):
    response = client.get("/api/recruiters/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_me_returns_recruiter_for_valid_token(client, db_session):
    client.post("/api/recruiters/signup", json={"email": "r@example.com", "password": "hunter2"})
    token = client.post(
        "/api/recruiters/login", json={"email": "r@example.com", "password": "hunter2"}
    ).json()["auth_token"]

    response = client.get("/api/recruiters/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "r@example.com"


def test_logout_invalidates_the_token(client, db_session):
    client.post("/api/recruiters/signup", json={"email": "r@example.com", "password": "hunter2"})
    token = client.post(
        "/api/recruiters/login", json={"email": "r@example.com", "password": "hunter2"}
    ).json()["auth_token"]

    logout_response = client.post("/api/recruiters/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_response.status_code == 204

    me_response = client.get("/api/recruiters/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 401


import pytest


@pytest.mark.parametrize(
    "email",
    ["@gmeel.com", "x@gmeel.com", "x@gmail.con", "a@b", "a@b.c", "a..b@x.com", ".a@x.com", "a@-x.com", "no-at-sign", "@"],
)
def test_signup_rejects_invalid_or_misspelled_email(client, db_session, email):
    response = client.post("/api/recruiters/signup", json={"email": email, "password": "hunter2"})

    assert response.status_code == 422


def test_signup_and_login_normalize_email_case_and_whitespace(client, db_session):
    signup = client.post("/api/recruiters/signup", json={"email": " Mixed@Example.COM ", "password": "hunter2"})
    assert signup.status_code == 201
    assert signup.json()["email"] == "mixed@example.com"

    login = client.post("/api/recruiters/login", json={"email": "MIXED@example.com", "password": "hunter2"})
    assert login.status_code == 200
