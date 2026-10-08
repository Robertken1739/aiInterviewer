import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import llm.helper as helper_llm
import llm.smart as smart_llm
from config import settings
from db.models import InterviewSession, Message, Sequence, Stage, StageAttempt


class SequenceNotFoundError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


class SessionCompletedError(Exception):
    """Raised for any per-stage action (helper/ready/answer/followup) once all 5 stages are scored."""


class HelperLockedError(Exception):
    """The current stage's ready_at is set — Helper is permanently unavailable for it."""


class HelperRateLimitedError(Exception):
    """A Helper question came in less than helper_cooldown_seconds after the previous one."""


class StageNotReadyError(Exception):
    """POST /answer called before POST /ready for the current stage."""


class AlreadyAnsweredError(Exception):
    """POST /answer called twice for the same stage."""


class NoPendingFollowupError(Exception):
    """POST /followup called with no outstanding follow-up question to respond to."""


class StageNotScoredError(Exception):
    """POST /advance called while the current stage is answered but not yet scored."""


class SessionNotCompletedError(Exception):
    """GET /results called before the session has finished all 5 stages."""


class SessionExpiredError(Exception):
    """The session's assessment timer has run out -- no new work (helper/ready) may start."""


def deadline_at(session: InterviewSession) -> datetime | None:
    """The session-wide timer deadline, or None if this session has no assessment (no timer)."""
    if session.assessment is None:
        return None
    return session.started_at + timedelta(minutes=session.assessment.duration_minutes)


def _check_not_expired(session: InterviewSession) -> None:
    deadline = deadline_at(session)
    if deadline is not None and datetime.utcnow() > deadline:
        raise SessionExpiredError(session.id)


def create_session(
    db: Session,
    sequence_id: int,
    candidate_email: str | None = None,
    assessment_id: int | None = None,
    candidate_id: int | None = None,
) -> InterviewSession:
    """Create a session and pre-create all 5 stage_attempt rows for its sequence."""
    sequence = db.get(Sequence, sequence_id)
    if sequence is None:
        raise SequenceNotFoundError(sequence_id)

    session = InterviewSession(
        sequence_id=sequence_id,
        candidate_email=candidate_email,
        assessment_id=assessment_id,
        candidate_id=candidate_id,
    )
    db.add(session)
    db.flush()  # assigns session.id before the stage_attempts reference it

    for stage in sequence.stages:
        db.add(StageAttempt(session_id=session.id, stage_id=stage.id))

    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: uuid.UUID) -> InterviewSession:
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    return session


def current_stage_attempt(
    db: Session, session: InterviewSession, for_update: bool = False
) -> StageAttempt | None:
    """The first not-yet-scored stage_attempt, in stage order. None once all 5 are scored.

    Every helper/ready/answer/followup action is derived from THIS session's own
    rows only (filtered by session.id) — there is no endpoint that accepts a raw
    stage_attempt_id from the client, so a request can never reach another
    session's stages.
    """
    query = (
        db.query(StageAttempt)
        .join(Stage)
        .filter(StageAttempt.session_id == session.id, StageAttempt.score.is_(None))
        .order_by(Stage.order_index)
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def ask_helper(db: Session, session: InterviewSession, question: str) -> dict:
    _check_not_expired(session)
    attempt = current_stage_attempt(db, session, for_update=True)
    if attempt is None:
        raise SessionCompletedError(session.id)
    if attempt.ready_at is not None:
        raise HelperLockedError(attempt.id)

    # Cooldown keyed off the last helper-phase message's timestamp rather than
    # a new column -- Message.created_at already exists and is set server-side
    # at insert time, so there's nothing new to store or keep in sync.
    last_helper_message = (
        db.query(Message)
        .filter(Message.stage_attempt_id == attempt.id, Message.phase == "helper")
        .order_by(Message.id.desc())
        .first()
    )
    if last_helper_message is not None:
        elapsed = (datetime.utcnow() - last_helper_message.created_at).total_seconds()
        if elapsed < settings.helper_cooldown_seconds:
            raise HelperRateLimitedError(attempt.id)

    # Only ever pass the stage's plain prompt text -- never the Stage object
    # itself -- so llm/helper.py has no attribute path to reference_answer or
    # trap_claim_text.
    result = helper_llm.ask_helper(session.sequence, attempt.stage.prompt_text, question)

    db.add(Message(stage_attempt_id=attempt.id, phase="helper", speaker="user", content=question))
    db.add(Message(stage_attempt_id=attempt.id, phase="helper", speaker="ai", content=result["ai_response"]))
    db.commit()

    return result


def mark_ready(db: Session, session: InterviewSession) -> StageAttempt:
    _check_not_expired(session)
    attempt = current_stage_attempt(db, session, for_update=True)
    if attempt is None:
        raise SessionCompletedError(session.id)
    if attempt.ready_at is None:
        attempt.ready_at = datetime.utcnow()
        db.commit()
        db.refresh(attempt)
    return attempt


def submit_answer(db: Session, session: InterviewSession, text: str) -> dict:
    attempt = current_stage_attempt(db, session, for_update=True)
    if attempt is None:
        raise SessionCompletedError(session.id)
    if attempt.ready_at is None:
        raise StageNotReadyError(attempt.id)
    if attempt.answer_text is not None:
        raise AlreadyAnsweredError(attempt.id)

    # Not committed here on purpose: _evaluate() calls the Smart LLM, which can
    # fail (rate limit, transient upstream error, invalid output). If it does,
    # this attribute assignment is never committed and rolls back when the
    # request's DB session closes -- so answer_text is still NULL afterwards
    # and the candidate can just call /answer again. Committing it immediately
    # here would instead permanently strand the stage: answer_text would be
    # set with no score and no pending follow-up, and every retry path
    # (another /answer, or /followup) would reject.
    attempt.answer_text = text
    return _evaluate(db, session, attempt, followup_count=0)


def submit_followup(db: Session, session: InterviewSession, response_text: str) -> dict:
    attempt = current_stage_attempt(db, session, for_update=True)
    if attempt is None:
        raise SessionCompletedError(session.id)
    if attempt.answer_text is None or attempt.score is not None:
        raise NoPendingFollowupError(attempt.id)

    followup_messages = _followup_messages(db, attempt)
    if not followup_messages or followup_messages[-1].speaker != "ai":
        raise NoPendingFollowupError(attempt.id)

    # Same reasoning as submit_answer: left uncommitted so a failed Smart LLM
    # call in _evaluate() rolls this back too, instead of leaving a
    # user-authored followup message on top with nothing responding to it
    # (which would then make every retry look like "no pending question").
    db.add(Message(stage_attempt_id=attempt.id, phase="followup", speaker="user", content=response_text))

    asked_count = sum(1 for m in followup_messages if m.speaker == "ai")
    return _evaluate(db, session, attempt, followup_count=asked_count)


def _followup_messages(db: Session, attempt: StageAttempt) -> list[Message]:
    """Always a fresh query, never `attempt.messages` -- that relationship is
    cached per-object for the lifetime of the SQLAlchemy Session, and rows
    added here go in via an explicit `stage_attempt_id` (not through the
    relationship), so the cached collection can go stale relative to what's
    actually committed.
    """
    return (
        db.query(Message)
        .filter(Message.stage_attempt_id == attempt.id, Message.phase == "followup")
        .order_by(Message.id)
        .all()
    )


def _previous_stage_summaries(db: Session, session: InterviewSession, before_order_index: int) -> list[dict]:
    """Compact {order_index, stage_type, score, rationale} for already-scored
    stages earlier in this session -- never the full answer/follow-up transcript.
    """
    scored_attempts = (
        db.query(StageAttempt)
        .join(Stage)
        .filter(
            StageAttempt.session_id == session.id,
            StageAttempt.score.is_not(None),
            Stage.order_index < before_order_index,
        )
        .order_by(Stage.order_index)
        .all()
    )
    return [
        {
            "order_index": a.stage.order_index,
            "stage_type": a.stage.stage_type,
            "score": a.score,
            "rationale": a.score_rationale,
        }
        for a in scored_attempts
    ]


def _evaluate(db: Session, session: InterviewSession, attempt: StageAttempt, followup_count: int) -> dict:
    followup_history = [{"speaker": m.speaker, "content": m.content} for m in _followup_messages(db, attempt)]
    previous_stage_summaries = _previous_stage_summaries(db, session, attempt.stage.order_index)
    force_final = followup_count >= settings.max_followups

    try:
        if smart_llm.is_non_answer(attempt.answer_text):
            decision = {"decision": "final", "score": 0, "rationale": smart_llm.NON_ANSWER_RATIONALE}
        else:
            decision = smart_llm.evaluate_answer(
                attempt.stage,
                attempt.answer_text,
                followup_history,
                previous_stage_summaries,
                force_final=force_final,
            )
    except Exception:
        # Explicit rollback, not just relying on the request's DB session
        # eventually closing: discards the caller's uncommitted answer_text /
        # followup-response write so the stage isn't left half-answered with
        # no way to retry. See submit_answer/submit_followup for why those
        # writes are deliberately left uncommitted until this call succeeds.
        db.rollback()
        raise

    if decision["decision"] == "followup":
        db.add(Message(stage_attempt_id=attempt.id, phase="followup", speaker="ai", content=decision["question"]))
        db.commit()
        return {"status": "followup", "question": decision["question"]}

    attempt.score = decision["score"]
    attempt.score_rationale = decision["rationale"]
    db.commit()
    db.refresh(attempt)
    return {"status": "scored", "score": attempt.score, "rationale": attempt.score_rationale}


def _all_stage_results(db: Session, session: InterviewSession) -> list[dict]:
    attempts = (
        db.query(StageAttempt)
        .join(Stage)
        .filter(StageAttempt.session_id == session.id)
        .order_by(Stage.order_index)
        .all()
    )
    return [
        {
            "order_index": a.stage.order_index,
            "axis": axis_for_order_index(a.stage.order_index),
            "score": a.score,
            "rationale": a.score_rationale,
        }
        for a in attempts
    ]


def _all_helper_messages(db: Session, session: InterviewSession) -> list[dict]:
    """Every phase='helper' message across ALL 5 stages of this session --
    the full input to the AI-Steering Efficiency evaluation."""
    messages = (
        db.query(Message)
        .join(StageAttempt)
        .filter(StageAttempt.session_id == session.id, Message.phase == "helper")
        .order_by(Message.id)
        .all()
    )
    return [{"speaker": m.speaker, "content": m.content} for m in messages]


def axis_for_order_index(order_index: int) -> str:
    return smart_llm.AXIS_BY_ORDER_INDEX[order_index]


def advance(db: Session, session: InterviewSession) -> dict:
    attempt = current_stage_attempt(db, session, for_update=True)
    if attempt is not None:
        if attempt.answer_text is not None and attempt.score is None:
            raise StageNotScoredError(attempt.id)
        return {"status": "in_progress"}

    # All 5 stages scored — finalize the session: overall feedback + AI-Steering
    # Efficiency, both from one Groq call over the stage results and the
    # candidate's full Helper conversation.
    stage_results = _all_stage_results(db, session)
    helper_messages = _all_helper_messages(db, session)
    finalization = smart_llm.finalize_session(stage_results, helper_messages)

    session.status = "completed"
    session.overall_feedback = finalization["overall_feedback"]
    session.ai_steering_score = finalization["ai_steering_score"]
    session.ai_steering_rationale = finalization["ai_steering_rationale"]
    session.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return {"status": "completed"}


def end_session(db: Session, session: InterviewSession) -> InterviewSession:
    """Candidate-driven early end: force-complete immediately with whatever's
    scored so far. No Smart LLM finalization call -- overall_feedback and
    ai_steering stay unset, since the transcript is incomplete by definition.
    """
    if session.status == "completed":
        raise SessionCompletedError(session.id)

    session.status = "completed"
    session.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session


def get_results(db: Session, session: InterviewSession) -> InterviewSession:
    if session.status != "completed":
        raise SessionNotCompletedError(session.id)
    return session
