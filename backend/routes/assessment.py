from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

import assessment.flow as assessment_flow
from db.models import Assessment, Candidate, Recruiter, Sequence
from db.session import get_db
from routes.candidate import get_current_candidate
from routes.interview import session_out
from routes.recruiter import get_current_recruiter
from schemas import (
    AssessmentCreateRequest,
    AssessmentJoinRequest,
    AssessmentOut,
    AssessmentSessionSummaryOut,
    SequenceOut,
    SessionOut,
)
from time_utils import as_utc

router = APIRouter()


def _assessment_out(assessment: Assessment) -> AssessmentOut:
    return AssessmentOut(
        id=assessment.id,
        sequence_id=assessment.sequence_id,
        sequence_title=assessment.sequence.title,
        share_token=assessment.share_token,
        duration_minutes=assessment.duration_minutes,
        created_at=as_utc(assessment.created_at),
        closed_at=as_utc(assessment.closed_at),
    )


@router.get("/sequences", response_model=list[SequenceOut])
def list_sequences(db: Session = Depends(get_db), recruiter: Recruiter = Depends(get_current_recruiter)):
    return db.query(Sequence).order_by(Sequence.id).all()


@router.post("/assessments", response_model=AssessmentOut, status_code=201)
def create_assessment(
    body: AssessmentCreateRequest,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
) -> AssessmentOut:
    assessment = assessment_flow.create_assessment(db, recruiter, body.sequence_id, body.duration_minutes)
    return _assessment_out(assessment)


@router.get("/assessments", response_model=list[AssessmentOut])
def list_assessments(db: Session = Depends(get_db), recruiter: Recruiter = Depends(get_current_recruiter)):
    assessments = assessment_flow.list_assessments_for_recruiter(db, recruiter)
    return [_assessment_out(a) for a in assessments]


@router.get("/assessments/{assessment_id}", response_model=AssessmentOut)
def get_assessment(
    assessment_id: int, db: Session = Depends(get_db), recruiter: Recruiter = Depends(get_current_recruiter)
) -> AssessmentOut:
    assessment = assessment_flow.get_owned_assessment(db, recruiter, assessment_id)
    return _assessment_out(assessment)


@router.post("/assessments/{assessment_id}/close", response_model=AssessmentOut)
def close_assessment(
    assessment_id: int, db: Session = Depends(get_db), recruiter: Recruiter = Depends(get_current_recruiter)
) -> AssessmentOut:
    assessment = assessment_flow.get_owned_assessment(db, recruiter, assessment_id)
    assessment = assessment_flow.close_assessment(db, assessment)
    return _assessment_out(assessment)


@router.get("/assessments/{assessment_id}/sessions", response_model=list[AssessmentSessionSummaryOut])
def list_assessment_sessions(
    assessment_id: int, db: Session = Depends(get_db), recruiter: Recruiter = Depends(get_current_recruiter)
):
    assessment = assessment_flow.get_owned_assessment(db, recruiter, assessment_id)
    sessions = assessment_flow.list_sessions_for_assessment(db, assessment)
    return [
        AssessmentSessionSummaryOut(
            session_id=s.id,
            candidate_email=s.candidate_email,
            status=s.status,
            overall_score=_overall_score(s),
            ai_steering_score=s.ai_steering_score,
            started_at=as_utc(s.started_at),
            completed_at=as_utc(s.completed_at),
        )
        for s in sessions
    ]


def _overall_score(session) -> float | None:
    scores = [a.score for a in session.stage_attempts if a.score is not None]
    return round(sum(scores) / len(scores), 1) if scores else None


@router.post("/assessments/join", response_model=SessionOut, status_code=201)
def join_assessment(
    body: AssessmentJoinRequest,
    db: Session = Depends(get_db),
    candidate: Candidate = Depends(get_current_candidate),
) -> SessionOut:
    assessment = db.query(Assessment).filter_by(share_token=body.share_token).first()
    if assessment is None:
        raise assessment_flow.AssessmentNotFoundError(body.share_token)
    session = assessment_flow.join_assessment(db, assessment, candidate)
    return session_out(db, session)
