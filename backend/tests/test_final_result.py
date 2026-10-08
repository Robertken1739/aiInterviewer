
from db.models import InterviewSession
from llm.smart import SessionFinalization, SmartEvaluation
from tests.conftest import seed_sequence


def _create_session(client, sequence_id: int) -> str:
    response = client.post("/api/sessions", json={"sequence_id": sequence_id})
    assert response.status_code == 201
    return response.json()["id"]


def _score_stage(client, mock_llm, session_id: str, score: int, rationale: str = "ok") -> None:
    """Ready + answer a stage with an immediate final score (no follow-up), then advance."""
    client.post(f"/api/sessions/{session_id}/ready")
    mock_llm.queue_smart_response(SmartEvaluation(decision="final_score", score=score, rationale=rationale))
    result = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my full answer to this question"}).json()
    assert result["status"] == "scored"
    assert client.post(f"/api/sessions/{session_id}/advance").status_code == 200


def _finalization_calls(mock_llm) -> list[dict]:
    return [
        c for c in mock_llm.calls if c["schema"] is SessionFinalization
    ]


def test_overall_score_is_average_of_the_five_stage_scores(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    for score in [5, 4, 3, 2, 1]:
        _score_stage(client, mock_llm, session_id, score)

    body = client.get(f"/api/sessions/{session_id}/results").json()

    assert body["overall_score"] == 3.0
    assert [sr["score"] for sr in body["stage_results"]] == [5, 4, 3, 2, 1]


def test_stage_results_include_rubric_axis_labels(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    for score in [3, 3, 3, 3, 3]:
        _score_stage(client, mock_llm, session_id, score)

    body = client.get(f"/api/sessions/{session_id}/results").json()

    assert [sr["axis"] for sr in body["stage_results"]] == [
        "Technical Correctness",
        "Trade-off Reasoning",
        "Constraint Adaptability",
        "AI Oversight & Skepticism",
        "Communication Clarity",
    ]


def test_final_result_includes_overall_feedback_and_ai_steering(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    mock_llm.queue_finalization(
        SessionFinalization(
            overall_feedback="Strong technical reasoning throughout; work on tailoring explanations for non-technical audiences.",
            ai_steering_score=4,
            ai_steering_rationale="Asked focused questions without requesting the answer outright.",
        )
    )

    for score in [4, 4, 4, 4, 4]:
        _score_stage(client, mock_llm, session_id, score)

    body = client.get(f"/api/sessions/{session_id}/results").json()

    assert body["overall_feedback"] == (
        "Strong technical reasoning throughout; work on tailoring explanations for non-technical audiences."
    )
    assert body["ai_steering_score"] == 4
    assert body["ai_steering_rationale"] == "Asked focused questions without requesting the answer outright."


def test_ai_steering_evaluation_sees_the_full_helper_conversation(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    client.post(f"/api/sessions/{session_id}/helper", json={"question": "any hints on stage 1?"})
    for score in [3, 3, 3, 3, 3]:
        _score_stage(client, mock_llm, session_id, score)

    calls = _finalization_calls(mock_llm)
    assert len(calls) == 1
    assert "any hints on stage 1?" in calls[0]["contents"]


def test_ai_steering_evaluation_notes_when_helper_was_never_used(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    for score in [3, 3, 3, 3, 3]:
        _score_stage(client, mock_llm, session_id, score)

    calls = _finalization_calls(mock_llm)
    assert "did not use the Helper" in calls[0]["contents"]


def test_invalid_finalization_output_is_handled_safely(client, db_session, mock_llm, monkeypatch):
    """A bad finalization response must not leave the session half-completed."""
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    for score in [3, 3, 3, 3]:
        _score_stage(client, mock_llm, session_id, score)  # stages 1-4

    client.post(f"/api/sessions/{session_id}/ready")
    mock_llm.queue_smart_response(SmartEvaluation(decision="final_score", score=5, rationale="ok"))
    result = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my full answer to this question"}).json()
    assert result["status"] == "scored"  # stage 5 scored, session not yet finalized

    original_complete = mock_llm.complete

    def _broken_complete(*, model, system, prompt, schema=None):
        if schema is SessionFinalization:
            return "garbage"
        return original_complete(model=model, system=system, prompt=prompt, schema=schema)

    monkeypatch.setattr("llm.smart.complete", _broken_complete)

    response = client.post(f"/api/sessions/{session_id}/advance")

    assert response.status_code == 502
    session = db_session.query(InterviewSession).filter(InterviewSession.id == session_id).one()
    assert session.status == "in_progress"  # finalization failed -- session NOT marked completed
    assert session.overall_feedback is None
    assert session.ai_steering_score is None


def test_results_list_the_questions_the_candidate_asked_the_helper(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    client.post(f"/api/sessions/{session_id}/helper", json={"question": "which gas is cheaper?"})
    for score in [3, 3, 3, 3, 3]:
        _score_stage(client, mock_llm, session_id, score)

    stages = client.get(f"/api/sessions/{session_id}/results").json()["stage_results"]
    assert stages[0]["helper_questions"] == ["which gas is cheaper?"]  # questions only, not the AI reply
    assert all(s["helper_questions"] == [] for s in stages[1:])
