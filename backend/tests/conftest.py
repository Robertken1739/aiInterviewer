import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from db.models import Base, Sequence, Stage
from db.session import get_db
from llm.smart import FORCE_FINAL_INSTRUCTION, SessionFinalization, SmartEvaluation
from main import app

TEST_DATABASE_URL = settings.database_url.rsplit("/", 1)[0] + "/aiinterviewer_test"

STAGE_TYPES = ["anchor", "constraint", "contradiction", "ai_trap", "synthesis"]


def seed_sequence(db_session, title: str = "Shielding Gas Selection") -> Sequence:
    """Insert one sequence with all 5 stages — shared fixture data for any test
    that needs a real sequence to create a session against."""
    sequence = Sequence(title=title, source_material="Neutral background reading.")
    db_session.add(sequence)
    db_session.flush()

    for i, stage_type in enumerate(STAGE_TYPES, start=1):
        db_session.add(
            Stage(
                sequence_id=sequence.id,
                order_index=i,
                stage_type=stage_type,
                prompt_text=f"Prompt for stage {i}",
                trap_claim_text="Wrong copilot claim" if stage_type == "ai_trap" else None,
                reference_answer=f"Reference answer for stage {i}",
            )
        )
    db_session.commit()
    db_session.refresh(sequence)
    return sequence


engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db_session():
    """Fresh schema per test — simplest correct isolation given the app code commits."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class FakeLLM:
    """Stands in for llm.client.complete and records every call so tests can
    inspect what was sent.

    Distinguishes call shapes by which structured `schema` was requested
    (identity match on the class object): Helper calls (plain text, no
    schema) get `_text`; per-stage Smart LLM calls get the next queued
    SmartEvaluation, or a sensible default that mimics "always ask one
    follow-up, then finalize once forced"; session finalization calls get
    the next queued SessionFinalization, or a sensible default. Defaults mean
    most tests don't need to queue a response for every single call.
    """

    def __init__(self, text: str = "Mocked Helper guidance."):
        self._text = text
        self.calls: list[dict] = []
        self._smart_queue: list = []
        self._finalization_queue: list = []

    def queue_smart_response(self, evaluation) -> None:
        self._smart_queue.append(evaluation)

    def queue_finalization(self, finalization) -> None:
        self._finalization_queue.append(finalization)

    def complete(self, *, model, system, prompt, schema=None) -> str:
        self.calls.append({"model": model, "system": system, "contents": prompt, "schema": schema})

        if schema is SessionFinalization:
            if self._finalization_queue:
                finalization = self._finalization_queue.pop(0)
            else:
                finalization = SessionFinalization(
                    overall_feedback="Mocked overall feedback.",
                    ai_steering_score=3,
                    ai_steering_rationale="Mocked AI-steering rationale.",
                )
            return finalization.model_dump_json()

        if schema is SmartEvaluation:
            if self._smart_queue:
                evaluation = self._smart_queue.pop(0)
            elif FORCE_FINAL_INSTRUCTION in prompt:
                evaluation = SmartEvaluation(decision="final_score", score=3, rationale="Mocked Smart LLM rationale.")
            else:
                evaluation = SmartEvaluation(decision="follow_up", question="Mocked Smart LLM follow-up question.")
            return evaluation.model_dump_json()

        return self._text


@pytest.fixture()
def mock_llm(monkeypatch):
    """Patches both llm.helper's and llm.smart's `complete` so tests never hit
    the real API."""
    fake = FakeLLM()
    monkeypatch.setattr("llm.helper.complete", fake.complete)
    monkeypatch.setattr("llm.smart.complete", fake.complete)
    return fake
