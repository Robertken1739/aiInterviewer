from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from db.models import Recruiter
from db.session import get_db
from recruiter import auth
from schemas import RecruiterLoginRequest, RecruiterOut, RecruiterSignupRequest

router = APIRouter()


def get_current_recruiter(authorization: str = Header(...), db: Session = Depends(get_db)) -> Recruiter:
    token = authorization.removeprefix("Bearer ").strip()
    return auth.get_recruiter_by_token(db, token)


@router.post("/recruiters/signup", response_model=RecruiterOut, status_code=201)
def signup(body: RecruiterSignupRequest, db: Session = Depends(get_db)) -> Recruiter:
    return auth.signup(db, body.email, body.password)


@router.post("/recruiters/login", response_model=RecruiterOut)
def login(body: RecruiterLoginRequest, db: Session = Depends(get_db)) -> Recruiter:
    return auth.login(db, body.email, body.password)


@router.post("/recruiters/logout", status_code=204)
def logout(db: Session = Depends(get_db), recruiter: Recruiter = Depends(get_current_recruiter)) -> None:
    auth.logout(db, recruiter)


@router.get("/recruiters/me", response_model=RecruiterOut)
def me(recruiter: Recruiter = Depends(get_current_recruiter)) -> Recruiter:
    return recruiter
