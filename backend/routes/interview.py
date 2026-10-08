import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.models import InterviewSession
from db.session import get_db
from interview import flow
from schemas import (
    AdvanceOut,
    AnswerRequest,
    CurrentStageOut,
    EvaluationOut,
    FollowupRequest,
    HelperReplyOut,
    HelperRequest,
    ResultOut,
    SessionCreateRequest,
    SessionOut,
    StageResultOut,
)
from time_utils import as_utc

router = APIRouter()


def _current_stage_out(db: Session, session: InterviewSession) -> CurrentStageOut | None:
    attempt = flow.current_stage_attempt(db, session)
    if attempt is None:
        return None
    return CurrentStageOut(
        order_index=attempt.stage.order_index,
        stage_type=attempt.stage.stage_type,
        prompt_text=attempt.stage.prompt_text,
        trap_claim_text=attempt.stage.trap_claim_text,
        helper_locked=attempt.ready_at is not None,
        answer_text=attempt.answer_text,
        score=attempt.score,
        score_rationale=attempt.score_rationale,
    )


def session_out(db: Session, session: InterviewSession) -> SessionOut:
    return SessionOut(
        id=session.id,
        sequence_id=session.sequence_id,
        candidate_email=session.candidate_email,
        status=session.status,
        started_at=as_utc(session.started_at),
        completed_at=as_utc(session.completed_at),
        deadline_at=as_utc(flow.deadline_at(session)),
        current_stage=_current_stage_out(db, session),
    )


def _result_out(session: InterviewSession) -> ResultOut:
    sorted_attempts = sorted(session.stage_attempts, key=lambda a: a.stage.order_index)
    stage_results = [
        StageResultOut(
            order_index=attempt.stage.order_index,
            stage_type=attempt.stage.stage_type,
            axis=flow.axis_for_order_index(attempt.stage.order_index),
            answer_text=attempt.answer_text,
            score=attempt.score,
            score_rationale=attempt.score_rationale,
            helper_questions=[m.content for m in attempt.messages if m.phase == "helper" and m.speaker == "user"],
        )
        for attempt in sorted_attempts
    ]
    scores = [attempt.score for attempt in sorted_attempts if attempt.score is not None]
    overall_score = round(sum(scores) / len(scores), 1) if scores else None
    return ResultOut(
        session_id=session.id,
        status=session.status,
        stage_results=stage_results,
        overall_score=overall_score,
        overall_feedback=session.overall_feedback,
        ai_steering_score=session.ai_steering_score,
        ai_steering_rationale=session.ai_steering_rationale,
    )


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreateRequest, db: Session = Depends(get_db)) -> SessionOut:
    session = flow.create_session(db, body.sequence_id, body.candidate_email)
    return session_out(db, session)


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)) -> SessionOut:
    session = flow.get_session(db, session_id)
    return session_out(db, session)


@router.post("/sessions/{session_id}/helper", response_model=HelperReplyOut)
def ask_helper(session_id: uuid.UUID, body: HelperRequest, db: Session = Depends(get_db)) -> HelperReplyOut:
    session = flow.get_session(db, session_id)
    result = flow.ask_helper(db, session, body.question)
    return HelperReplyOut(**result)


@router.post("/sessions/{session_id}/ready", response_model=SessionOut)
def mark_ready(session_id: uuid.UUID, db: Session = Depends(get_db)) -> SessionOut:
    session = flow.get_session(db, session_id)
    flow.mark_ready(db, session)
    return session_out(db, session)


@router.post("/sessions/{session_id}/answer", response_model=EvaluationOut)
def submit_answer(session_id: uuid.UUID, body: AnswerRequest, db: Session = Depends(get_db)) -> EvaluationOut:
    session = flow.get_session(db, session_id)
    result = flow.submit_answer(db, session, body.text)
    return EvaluationOut(**result)


@router.post("/sessions/{session_id}/followup", response_model=EvaluationOut)
def submit_followup(
    session_id: uuid.UUID, body: FollowupRequest, db: Session = Depends(get_db)
) -> EvaluationOut:
    session = flow.get_session(db, session_id)
    result = flow.submit_followup(db, session, body.response)
    return EvaluationOut(**result)


@router.post("/sessions/{session_id}/advance", response_model=AdvanceOut)
def advance(session_id: uuid.UUID, db: Session = Depends(get_db)) -> AdvanceOut:
    session = flow.get_session(db, session_id)
    result = flow.advance(db, session)
    if result["status"] == "completed":
        return AdvanceOut(status="completed")
    return AdvanceOut(status="in_progress", current_stage=_current_stage_out(db, session))


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
def end_session(session_id: uuid.UUID, db: Session = Depends(get_db)) -> SessionOut:
    session = flow.get_session(db, session_id)
    flow.end_session(db, session)
    return session_out(db, session)


@router.get("/sessions/{session_id}/results", response_model=ResultOut)
def get_results(session_id: uuid.UUID, db: Session = Depends(get_db)) -> ResultOut:
    session = flow.get_session(db, session_id)
    session = flow.get_results(db, session)
    return _result_out(session)
