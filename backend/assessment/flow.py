"""Recruiter creates/manages assessments (OAs); candidates join them. Plain
functions, no service/repository classes -- mirrors interview/flow.py.
"""

import secrets
from datetime import datetime

from sqlalchemy.orm import Session

import interview.flow as interview_flow
from db.models import Assessment, Candidate, InterviewSession, Recruiter, Sequence


class SequenceNotFoundError(Exception):
    pass


class AssessmentNotFoundError(Exception):
    pass


class NotAssessmentOwnerError(Exception):
    """A recruiter tried to view/manage an assessment they don't own."""


class AssessmentClosedError(Exception):
    """A candidate tried to join an assessment the recruiter has closed."""


def create_assessment(db: Session, recruiter: Recruiter, sequence_id: int, duration_minutes: int) -> Assessment:
    if db.get(Sequence, sequence_id) is None:
        raise SequenceNotFoundError(sequence_id)

    assessment = Assessment(
        recruiter_id=recruiter.id,
        sequence_id=sequence_id,
        share_token=secrets.token_urlsafe(16),
        duration_minutes=duration_minutes,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


def list_assessments_for_recruiter(db: Session, recruiter: Recruiter) -> list[Assessment]:
    return db.query(Assessment).filter_by(recruiter_id=recruiter.id).order_by(Assessment.created_at.desc()).all()


def get_owned_assessment(db: Session, recruiter: Recruiter, assessment_id: int) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise AssessmentNotFoundError(assessment_id)
    if assessment.recruiter_id != recruiter.id:
        raise NotAssessmentOwnerError(assessment_id)
    return assessment


def close_assessment(db: Session, assessment: Assessment) -> Assessment:
    assessment.closed_at = datetime.utcnow()
    db.commit()
    db.refresh(assessment)
    return assessment


def list_sessions_for_assessment(db: Session, assessment: Assessment) -> list[InterviewSession]:
    return (
        db.query(InterviewSession)
        .filter_by(assessment_id=assessment.id)
        .order_by(InterviewSession.started_at)
        .all()
    )


def join_assessment(db: Session, assessment: Assessment, candidate: Candidate) -> InterviewSession:
    """Idempotent: returns the candidate's existing session for this assessment, if any."""
    existing = (
        db.query(InterviewSession)
        .filter_by(assessment_id=assessment.id, candidate_id=candidate.id)
        .first()
    )
    if existing is not None:
        return existing

    if assessment.closed_at is not None:
        raise AssessmentClosedError(assessment.id)

    return interview_flow.create_session(
        db,
        sequence_id=assessment.sequence_id,
        candidate_email=candidate.email,
        assessment_id=assessment.id,
        candidate_id=candidate.id,
    )
