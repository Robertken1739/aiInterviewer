from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from candidate import auth
from db.models import Candidate
from db.session import get_db
from schemas import CandidateLoginRequest, CandidateOut, CandidateSignupRequest

router = APIRouter()


def get_current_candidate(authorization: str = Header(...), db: Session = Depends(get_db)) -> Candidate:
    token = authorization.removeprefix("Bearer ").strip()
    return auth.get_candidate_by_token(db, token)


@router.post("/candidates/signup", response_model=CandidateOut, status_code=201)
def signup(body: CandidateSignupRequest, db: Session = Depends(get_db)) -> Candidate:
    return auth.signup(db, body.email, body.password)


@router.post("/candidates/login", response_model=CandidateOut)
def login(body: CandidateLoginRequest, db: Session = Depends(get_db)) -> Candidate:
    return auth.login(db, body.email, body.password)


@router.post("/candidates/logout", status_code=204)
def logout(db: Session = Depends(get_db), candidate: Candidate = Depends(get_current_candidate)) -> None:
    auth.logout(db, candidate)


@router.get("/candidates/me", response_model=CandidateOut)
def me(candidate: Candidate = Depends(get_current_candidate)) -> Candidate:
    return candidate
