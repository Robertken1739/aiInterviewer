import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Recruiter(Base):
    """An account that can own sequences and (later) share them with candidates."""

    __tablename__ = "recruiter"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    auth_token: Mapped[str | None] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Candidate(Base):
    """An account a person uses to join and take assessments."""

    __tablename__ = "candidate"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    auth_token: Mapped[str | None] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Sequence(Base):
    """One interview track: a title plus the background reading the Helper LLM may show."""

    __tablename__ = "sequence"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: seeded sequences have no owning recruiter. Set once a recruiter
    # creates/claims a sequence to share as an OA (that flow isn't built yet).
    recruiter_id: Mapped[int | None] = mapped_column(ForeignKey("recruiter.id"))
    title: Mapped[str]
    source_material: Mapped[str] = mapped_column(Text)

    stages: Mapped[list["Stage"]] = relationship(back_populates="sequence", order_by="Stage.order_index")


class Assessment(Base):
    """A recruiter's posting of one sequence as an OA — a shareable, timed instance."""

    __tablename__ = "assessment"

    id: Mapped[int] = mapped_column(primary_key=True)
    recruiter_id: Mapped[int] = mapped_column(ForeignKey("recruiter.id"))
    sequence_id: Mapped[int] = mapped_column(ForeignKey("sequence.id"))
    share_token: Mapped[str] = mapped_column(unique=True)
    duration_minutes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]

    recruiter: Mapped["Recruiter"] = relationship()
    sequence: Mapped["Sequence"] = relationship()


class Stage(Base):
    """One of the 5 fixed questions inside a sequence."""

    __tablename__ = "stage"
    __table_args__ = (UniqueConstraint("sequence_id", "order_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sequence_id: Mapped[int] = mapped_column(ForeignKey("sequence.id"))
    order_index: Mapped[int]
    stage_type: Mapped[str]
    prompt_text: Mapped[str] = mapped_column(Text)
    trap_claim_text: Mapped[str | None] = mapped_column(Text)
    reference_answer: Mapped[str] = mapped_column(Text)

    sequence: Mapped["Sequence"] = relationship(back_populates="stages")


class InterviewSession(Base):
    """One candidate's run through a sequence."""

    __tablename__ = "interview_session"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sequence_id: Mapped[int] = mapped_column(ForeignKey("sequence.id"))
    # Set together when a session is created via POST /assessments/join. Left
    # null for the older direct-by-sequence_id path (kept for dev/testing),
    # which still uses candidate_email alone.
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("assessment.id"))
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidate.id"))
    candidate_email: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="in_progress")
    ai_steering_score: Mapped[int | None]
    ai_steering_rationale: Mapped[str | None] = mapped_column(Text)
    overall_feedback: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]

    sequence: Mapped["Sequence"] = relationship()
    assessment: Mapped["Assessment | None"] = relationship()
    candidate: Mapped["Candidate | None"] = relationship()
    stage_attempts: Mapped[list["StageAttempt"]] = relationship(
        back_populates="session", order_by="StageAttempt.id"
    )


class StageAttempt(Base):
    """One candidate's attempt at one stage. 5 rows are created per session, up front."""

    __tablename__ = "stage_attempt"
    __table_args__ = (UniqueConstraint("session_id", "stage_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_session.id"))
    stage_id: Mapped[int] = mapped_column(ForeignKey("stage.id"))
    ready_at: Mapped[datetime | None]
    answer_text: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None]
    score_rationale: Mapped[str | None] = mapped_column(Text)

    session: Mapped["InterviewSession"] = relationship(back_populates="stage_attempts")
    stage: Mapped["Stage"] = relationship()
    messages: Mapped[list["Message"]] = relationship(back_populates="stage_attempt", order_by="Message.id")


class Message(Base):
    """One chat message, either a Helper-phase hint exchange or a Smart-LLM follow-up."""

    __tablename__ = "message"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_attempt_id: Mapped[int] = mapped_column(ForeignKey("stage_attempt.id"))
    phase: Mapped[str]
    speaker: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    stage_attempt: Mapped["StageAttempt"] = relationship(back_populates="messages")
