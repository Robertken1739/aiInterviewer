"""Recruiter signup/login/logout — plain functions, no service/repository classes."""

from sqlalchemy.orm import Session

from auth_utils import generate_token, hash_password, verify_password
from db.models import Recruiter


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


def signup(db: Session, email: str, password: str) -> Recruiter:
    if db.query(Recruiter).filter_by(email=email).first() is not None:
        raise EmailAlreadyRegisteredError(email)

    recruiter = Recruiter(email=email, password_hash=hash_password(password))
    db.add(recruiter)
    db.commit()
    db.refresh(recruiter)
    return recruiter


def login(db: Session, email: str, password: str) -> Recruiter:
    recruiter = db.query(Recruiter).filter_by(email=email).first()
    if recruiter is None or not verify_password(password, recruiter.password_hash):
        raise InvalidCredentialsError(email)

    recruiter.auth_token = generate_token()
    db.commit()
    db.refresh(recruiter)
    return recruiter


def logout(db: Session, recruiter: Recruiter) -> None:
    recruiter.auth_token = None
    db.commit()


def get_recruiter_by_token(db: Session, token: str) -> Recruiter:
    recruiter = db.query(Recruiter).filter_by(auth_token=token).first()
    if recruiter is None:
        raise InvalidTokenError(token)
    return recruiter
