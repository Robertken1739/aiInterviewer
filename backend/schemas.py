import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

_EMAIL_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9._%+-]{0,62}[a-z0-9])?"  # local part: no leading/trailing dot or symbol
    r"@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$"  # domain with a real TLD
)

# Typos of the big providers: they pass any syntax check, so an exact lookup is
# the only cheap way to stop a signup that could never receive mail.
_MISSPELLED_DOMAINS = {
    "gmeel.com": "gmail.com", "gmial.com": "gmail.com", "gmai.com": "gmail.com",
    "gmal.com": "gmail.com", "gamil.com": "gmail.com", "gmil.com": "gmail.com",
    "gnail.com": "gmail.com", "gmeil.com": "gmail.com", "gmaill.com": "gmail.com",
    "gmail.con": "gmail.com", "gmail.co": "gmail.com", "gmail.cm": "gmail.com",
    "hotmial.com": "hotmail.com", "hotmal.com": "hotmail.com", "hotmail.con": "hotmail.com",
    "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com", "yahoo.con": "yahoo.com",
    "outlok.com": "outlook.com", "outlook.con": "outlook.com", "outloook.com": "outlook.com",
    "iclod.com": "icloud.com", "icloud.con": "icloud.com",
}


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _validated_signup_email(value: str) -> str:
    email = _normalize_email(value)
    if len(email) > 254 or ".." in email or not _EMAIL_PATTERN.match(email):
        raise ValueError("enter a valid email address, like name@example.com")
    suggestion = _MISSPELLED_DOMAINS.get(email.rsplit("@", 1)[1])
    if suggestion:
        raise ValueError(f"that domain looks misspelled, did you mean {suggestion}?")
    return email


class RecruiterSignupRequest(BaseModel):
    email: str
    password: str

    _check_email = field_validator("email")(_validated_signup_email)


class RecruiterLoginRequest(BaseModel):
    email: str
    password: str

    # Login only normalizes; strict checks belong to signup, so a login can
    # never be blocked by a rule that was added after the account existed.
    _normalize_email = field_validator("email")(_normalize_email)


class RecruiterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    auth_token: str | None


class CandidateSignupRequest(BaseModel):
    email: str
    password: str

    _check_email = field_validator("email")(_validated_signup_email)


class CandidateLoginRequest(BaseModel):
    email: str
    password: str

    _normalize_email = field_validator("email")(_normalize_email)


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    auth_token: str | None


class SequenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str


class AssessmentCreateRequest(BaseModel):
    sequence_id: int
    duration_minutes: int


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence_id: int
    sequence_title: str
    share_token: str
    duration_minutes: int
    created_at: datetime
    closed_at: datetime | None


class AssessmentJoinRequest(BaseModel):
    share_token: str


class AssessmentSessionSummaryOut(BaseModel):
    session_id: uuid.UUID
    candidate_email: str | None
    status: str
    overall_score: float | None
    ai_steering_score: int | None
    started_at: datetime
    completed_at: datetime | None


class SessionCreateRequest(BaseModel):
    sequence_id: int
    candidate_email: str | None = None


class CurrentStageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_index: int
    stage_type: str
    prompt_text: str
    trap_claim_text: str | None
    helper_locked: bool
    answer_text: str | None
    score: int | None
    score_rationale: str | None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence_id: int
    candidate_email: str | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    deadline_at: datetime | None
    current_stage: CurrentStageOut | None


class HelperRequest(BaseModel):
    question: str


class HelperReplyOut(BaseModel):
    ai_response: str
    raw_chunks: list[str]
    source_labels: list[str]


class AnswerRequest(BaseModel):
    text: str


class FollowupRequest(BaseModel):
    response: str


class EvaluationOut(BaseModel):
    # Deliberately no score/rationale: the candidate is never shown a grade
    # during the session -- evaluation is recruiter-side only, after the fact.
    status: str  # "followup" | "scored"
    question: str | None = None


class StageResultOut(BaseModel):
    order_index: int
    stage_type: str
    axis: str
    answer_text: str | None
    score: int | None
    score_rationale: str | None
    # What the candidate typed to the Helper on this stage, in order (their
    # questions only, not the Helper's replies).
    helper_questions: list[str] = []


class ResultOut(BaseModel):
    session_id: uuid.UUID
    status: str
    stage_results: list[StageResultOut]
    overall_score: float | None
    overall_feedback: str | None
    ai_steering_score: int | None
    ai_steering_rationale: str | None


class AdvanceOut(BaseModel):
    # No embedded ResultOut on completion, for the same reason as EvaluationOut
    # -- the candidate isn't shown scores. Recruiters fetch the full ResultOut
    # separately via GET /sessions/{id}/results using the session_id from
    # their assessment's session list.
    status: str  # "in_progress" | "completed"
    current_stage: CurrentStageOut | None = None
