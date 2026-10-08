"""Candidate signup/login/logout — plain functions, mirrors recruiter/auth.py."""

from sqlalchemy.orm import Session

from auth_utils import generate_token, hash_password, verify_password
from db.models import Candidate


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


def signup(db: Session, email: str, password: str) -> Candidate:
    if db.query(Candidate).filter_by(email=email).first() is not None:
        raise EmailAlreadyRegisteredError(email)

    candidate = Candidate(email=email, password_hash=hash_password(password))
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def login(db: Session, email: str, password: str) -> Candidate:
    candidate = db.query(Candidate).filter_by(email=email).first()
    if candidate is None or not verify_password(password, candidate.password_hash):
        raise InvalidCredentialsError(email)

    candidate.auth_token = generate_token()
    db.commit()
    db.refresh(candidate)
    return candidate


def logout(db: Session, candidate: Candidate) -> None:
    candidate.auth_token = None
    db.commit()


def get_candidate_by_token(db: Session, token: str) -> Candidate:
    candidate = db.query(Candidate).filter_by(auth_token=token).first()
    if candidate is None:
        raise InvalidTokenError(token)
    return candidate
