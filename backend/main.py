from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from groq import APIError as GroqAPIError

import assessment.flow as assessment_flow
from candidate import auth as candidate_auth
from interview import flow
from llm.client import GroqNotConfiguredError
from llm.smart import SmartLLMInvalidOutputError
from recruiter import auth as recruiter_auth
from routes.assessment import router as assessment_router
from routes.candidate import router as candidate_router
from routes.interview import router as interview_router
from routes.recruiter import router as recruiter_router

app = FastAPI(title="idolHire")

# MVP has one frontend, always run locally against the Vite dev server -- no
# need for an env-configurable origin list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(interview_router, prefix="/api")
app.include_router(recruiter_router, prefix="/api")
app.include_router(candidate_router, prefix="/api")
app.include_router(assessment_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Every state-transition rule flow.py enforces (plus a missing Groq config)
# raises one of these; map them to HTTP status codes here instead of
# repeating try/except in every route.
_ERROR_RESPONSES: dict[type[Exception], tuple[int, str]] = {
    flow.SequenceNotFoundError: (404, "sequence not found"),
    flow.SessionNotFoundError: (404, "session not found"),
    flow.SessionCompletedError: (409, "session already completed"),
    flow.HelperLockedError: (403, "helper is locked for this stage"),
    flow.HelperRateLimitedError: (429, "please wait a few seconds before asking the helper again"),
    flow.StageNotReadyError: (409, "call /ready before submitting an answer"),
    flow.AlreadyAnsweredError: (409, "this stage has already been answered"),
    flow.NoPendingFollowupError: (409, "no follow-up question is pending"),
    flow.StageNotScoredError: (409, "current stage is not scored yet"),
    flow.SessionNotCompletedError: (409, "session is not completed yet"),
    flow.SessionExpiredError: (409, "the timer for this assessment has run out"),
    GroqNotConfiguredError: (500, "Groq API is not configured (GROQ_API_KEY missing)"),
    SmartLLMInvalidOutputError: (502, "Smart LLM returned an invalid evaluation — please try again"),
    # Covers Groq server errors (overloaded/unavailable), rate limiting and
    # connection failures alike -- all mean "the Groq call itself failed,"
    # not a bug in our request. Without this, these fall
    # through as unhandled 500s, which Starlette serves with no CORS headers
    # at all -- the browser reports that as a CORS error, hiding the real
    # (transient, retry-worthy) cause.
    GroqAPIError: (502, "the AI model is temporarily unavailable — please try again"),
    recruiter_auth.EmailAlreadyRegisteredError: (409, "an account with this email already exists"),
    recruiter_auth.InvalidCredentialsError: (401, "invalid email or password"),
    recruiter_auth.InvalidTokenError: (401, "invalid or expired auth token"),
    candidate_auth.EmailAlreadyRegisteredError: (409, "an account with this email already exists"),
    candidate_auth.InvalidCredentialsError: (401, "invalid email or password"),
    candidate_auth.InvalidTokenError: (401, "invalid or expired auth token"),
    assessment_flow.SequenceNotFoundError: (404, "sequence not found"),
    assessment_flow.AssessmentNotFoundError: (404, "assessment not found"),
    assessment_flow.NotAssessmentOwnerError: (403, "you do not own this assessment"),
    assessment_flow.AssessmentClosedError: (409, "this assessment is closed to new candidates"),
}

for _exc_type, (_status_code, _message) in _ERROR_RESPONSES.items():

    def _make_handler(status_code: int, message: str):
        def _handler(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=status_code, content={"detail": message})

        return _handler

    app.add_exception_handler(_exc_type, _make_handler(_status_code, _message))
