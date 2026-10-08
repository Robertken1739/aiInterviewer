
import pytest

import config
from db.models import Message, Stage, StageAttempt
from llm.smart import SmartEvaluation, SmartLLMInvalidOutputError, evaluate_answer
from tests.conftest import seed_sequence


def _stage(**overrides) -> Stage:
    defaults = dict(
        id=1,
        sequence_id=1,
        order_index=1,
        stage_type="anchor",
        prompt_text="Recommend a shielding gas for carbon steel.",
        trap_claim_text=None,
        reference_answer="SECRET-REFERENCE-Ar-CO2-blend",
    )
    defaults.update(overrides)
    return Stage(**defaults)


def _create_session(client, sequence_id: int) -> str:
    response = client.post("/api/sessions", json={"sequence_id": sequence_id})
    assert response.status_code == 201
    return response.json()["id"]


def _stage_1_attempt(db_session, session_id: str) -> StageAttempt:
    """All 5 stage_attempts are pre-created per session -- these tests only
    ever touch stage 1, so fetch it specifically rather than assuming there's
    just one row."""
    return (
        db_session.query(StageAttempt)
        .filter(StageAttempt.session_id == session_id)
        .join(StageAttempt.stage)
        .filter_by(order_index=1)
        .one()
    )


# ---- unit-level: llm.smart.evaluate_answer() directly ------------------


def test_answer_and_reference_answer_are_sent_to_smart_llm(mock_llm):
    """1 & 2: the candidate's answer AND the stage's reference answer both
    reach the Smart LLM's prompt -- that's the whole point of grading."""
    stage = _stage()

    evaluate_answer(stage, "I would use an argon-CO2 blend.", [], [])

    sent_prompt = mock_llm.calls[-1]["contents"]
    assert "I would use an argon-CO2 blend." in sent_prompt
    assert stage.reference_answer in sent_prompt


def test_trap_claim_included_only_when_present(mock_llm):
    stage = _stage(
        order_index=4, stage_type="ai_trap", trap_claim_text="SECRET-TRAP-higher ionization potential"
    )

    evaluate_answer(stage, "That's wrong, it's thermal conductivity.", [], [])

    assert "SECRET-TRAP-higher ionization potential" in mock_llm.calls[-1]["contents"]


def test_rubric_axis_matches_stage_order_index(mock_llm):
    stage = _stage(order_index=3, stage_type="contradiction")

    evaluate_answer(stage, "some answer", [], [])

    assert "Constraint Adaptability" in mock_llm.calls[-1]["contents"]


def test_previous_stage_summaries_are_compact_not_full_transcripts(mock_llm):
    """Earlier stages only contribute order_index/stage_type/score/rationale --
    never their raw answer text (that's the difference from the current stage,
    which does get its full answer + follow-up transcript)."""
    stage = _stage(order_index=2, stage_type="constraint")
    previous_summaries = [{"order_index": 1, "stage_type": "anchor", "score": 4, "rationale": "Solid reasoning."}]
    raw_answer_marker = "SECRET-STAGE-1-RAW-ANSWER-TEXT"

    evaluate_answer(stage, "answer", [], previous_summaries)

    sent_prompt = mock_llm.calls[-1]["contents"]
    assert "Solid reasoning." in sent_prompt
    assert raw_answer_marker not in sent_prompt


def test_smart_model_config_is_used(mock_llm, monkeypatch):
    monkeypatch.setattr(config.settings, "groq_smart_model", "groq-smart-test-model")
    stage = _stage()

    evaluate_answer(stage, "answer", [], [])

    assert mock_llm.calls[-1]["model"] == "groq-smart-test-model"


def test_structured_followup_decision_is_handled(mock_llm):
    """4. A structured follow_up decision from the LLM becomes the internal
    {"decision": "followup", "question": ...} shape flow.py branches on."""
    mock_llm.queue_smart_response(
        SmartEvaluation(decision="follow_up", question="Can you say more about the trade-off?")
    )

    result = evaluate_answer(_stage(), "answer", [], [])

    assert result == {"decision": "followup", "question": "Can you say more about the trade-off?"}


def test_final_score_decision_is_handled(mock_llm):
    """7. A structured final_score decision becomes the internal final shape."""
    mock_llm.queue_smart_response(
        SmartEvaluation(decision="final_score", score=4, rationale="Correct and well justified.")
    )

    result = evaluate_answer(_stage(), "answer", [], [])

    assert result == {"decision": "final", "score": 4, "rationale": "Correct and well justified."}


def test_forced_final_raises_if_llm_still_requests_followup(mock_llm):
    """6, safety net: once the follow-up cap is hit, flow.py demands a forced
    final decision -- if the model disobeys and asks for another follow-up
    anyway, that must be treated as invalid output, not silently allowed
    (which would let a candidate's stage stay stuck in evaluation forever)."""
    mock_llm.queue_smart_response(SmartEvaluation(decision="follow_up", question="One more thing..."))

    with pytest.raises(SmartLLMInvalidOutputError):
        evaluate_answer(_stage(), "answer", [], [], force_final=True)


def test_invalid_llm_output_raises_instead_of_silently_scoring(mock_llm, monkeypatch):
    """8. If the LLM's reply can't be parsed into SmartEvaluation at all, that must surface as a
    specific, catchable error -- not an AttributeError deep in flow.py, and
    never a silently accepted/garbage score."""

    monkeypatch.setattr("llm.smart.complete", lambda **kwargs: "not valid json")

    with pytest.raises(SmartLLMInvalidOutputError):
        evaluate_answer(_stage(), "answer", [], [])


def test_transient_smart_llm_failure_leaves_the_stage_retryable(client, db_session, mock_llm, monkeypatch):
    """A raw/unexpected exception from the LLM call (e.g. a transient
    upstream 503) must not permanently strand the stage: answer_text must not
    be committed until scoring actually succeeds, or every retry path
    (another /answer -> "already answered"; /followup -> "nothing pending")
    would reject forever."""
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    client.post(f"/api/sessions/{session_id}/ready")

    def _flaky_complete(**kwargs):
        raise RuntimeError("simulated transient upstream failure")

    with monkeypatch.context() as m:
        m.setattr("llm.smart.complete", _flaky_complete)
        with pytest.raises(RuntimeError):
            client.post(f"/api/sessions/{session_id}/answer", json={"text": "my first full attempt here"})

    attempt = _stage_1_attempt(db_session, session_id)
    assert attempt.answer_text is None  # rolled back, not stuck half-answered
    assert attempt.score is None

    retry = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my retry answer here now"})
    assert retry.status_code == 200  # the same stage can just be answered again


# ---- integration-level: through the API ---------------------------------


def test_followup_question_and_response_are_stored_in_message_table(client, db_session, mock_llm):
    """5. Follow-up exchanges are persisted, with their actual content."""
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    client.post(f"/api/sessions/{session_id}/ready")

    mock_llm.queue_smart_response(
        SmartEvaluation(decision="follow_up", question="What about oxidation risk?")
    )
    client.post(f"/api/sessions/{session_id}/answer", json={"text": "Use pure CO2, it's cheap."})
    client.post(f"/api/sessions/{session_id}/followup", json={"response": "It's cheaper but oxidizes more."})

    attempt = _stage_1_attempt(db_session, session_id)
    followups = (
        db_session.query(Message)
        .filter(Message.stage_attempt_id == attempt.id, Message.phase == "followup")
        .order_by(Message.id)
        .all()
    )
    assert [(m.speaker, m.content) for m in followups[:2]] == [
        ("ai", "What about oxidation risk?"),
        ("user", "It's cheaper but oxidizes more."),
    ]


def test_final_score_and_rationale_are_stored_correctly(client, db_session, mock_llm):
    """7, DB-level: the score/rationale land in stage_attempt even though the
    candidate-facing response never carries them (evaluation is recruiter-side
    only -- see EvaluationOut)."""
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    client.post(f"/api/sessions/{session_id}/ready")

    mock_llm.queue_smart_response(
        SmartEvaluation(decision="final_score", score=2, rationale="Missed the oxidation trade-off.")
    )
    response = client.post(f"/api/sessions/{session_id}/answer", json={"text": "Use pure CO2."})

    assert response.status_code == 200
    assert response.json() == {"status": "scored", "question": None}

    attempt = _stage_1_attempt(db_session, session_id)
    assert attempt.score == 2
    assert attempt.score_rationale == "Missed the oxidation trade-off."


def test_invalid_llm_output_returns_502_and_writes_nothing(client, db_session, mock_llm, monkeypatch):
    """8, API-level: a bad LLM response fails cleanly and leaves no partial
    state -- including rolling back the candidate's answer_text itself, so
    the stage stays retryable instead of getting stuck "answered but never
    scored" with no way to submit again."""
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    client.post(f"/api/sessions/{session_id}/ready")

    monkeypatch.setattr("llm.smart.complete", lambda **kwargs: "garbage")

    response = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my full answer here"})

    assert response.status_code == 502
    attempt = _stage_1_attempt(db_session, session_id)
    assert attempt.answer_text is None  # rolled back -- not stuck half-answered
    assert attempt.score is None
    assert (
        db_session.query(Message).filter(Message.stage_attempt_id == attempt.id, Message.phase == "followup").count()
        == 0
    )

    retry = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my retry answer here now"})
    assert retry.status_code == 502  # still broken, but rejected the same clean way, not 409 "already answered"


def test_candidate_response_never_includes_reference_answer(client, db_session, mock_llm):
    """9. The API response for a scored stage carries neither the confidential
    reference answer nor the score/rationale itself -- the candidate is never
    evaluated in front of them; only status/question, per EvaluationOut."""
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    client.post(f"/api/sessions/{session_id}/ready")

    mock_llm.queue_smart_response(
        SmartEvaluation(decision="final_score", score=5, rationale="Nailed the trade-off.")
    )
    response = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my full answer to this question"})

    assert set(response.json().keys()) == {"status", "question"}
    assert "Reference answer for stage 1" not in response.text  # seed_sequence's stage 1 reference_answer


def test_advance_on_completion_never_embeds_scores(client, db_session, mock_llm):
    """Same boundary as above, at the /advance response on session completion --
    the candidate must never see scores there either (see AdvanceOut)."""
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    for _ in range(5):
        client.post(f"/api/sessions/{session_id}/ready")
        mock_llm.queue_smart_response(SmartEvaluation(decision="final_score", score=4, rationale="ok"))
        client.post(f"/api/sessions/{session_id}/answer", json={"text": "my full answer to this question"})
        response = client.post(f"/api/sessions/{session_id}/advance")

    assert response.json() == {"status": "completed", "current_stage": None}


def test_stage_cannot_be_scored_twice(client, db_session, mock_llm):
    """10. Once scored, a second /answer is rejected and the Smart LLM is never
    called again for that stage -- the stored score doesn't change."""
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    client.post(f"/api/sessions/{session_id}/ready")

    mock_llm.queue_smart_response(SmartEvaluation(decision="final_score", score=3, rationale="Ok."))
    client.post(f"/api/sessions/{session_id}/answer", json={"text": "my first full answer here"})
    calls_before = len(mock_llm.calls)

    second = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my second full answer here"})

    assert second.status_code == 409
    assert len(mock_llm.calls) == calls_before  # Smart LLM not invoked for the rejected attempt
    attempt = _stage_1_attempt(db_session, session_id)
    assert attempt.score == 3
    assert attempt.answer_text == "my first full answer here"


def test_zero_score_is_accepted_and_the_prompt_defines_it(mock_llm):
    mock_llm.queue_smart_response(SmartEvaluation(decision="final_score", score=0, rationale="Irrelevant."))

    result = evaluate_answer(_stage(), "banana", [], [])

    assert result == {"decision": "final", "score": 0, "rationale": "Irrelevant."}
    assert "exactly 0" in mock_llm.calls[-1]["system"]


def test_zero_score_is_stored_not_treated_as_unscored(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    client.post(f"/api/sessions/{session_id}/ready")
    mock_llm.queue_smart_response(SmartEvaluation(decision="final_score", score=0, rationale="Irrelevant."))

    result = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my favourite food is pizza"}).json()

    assert result["status"] == "scored"
    attempt = _stage_1_attempt(db_session, session_id)
    assert attempt.score == 0
    assert client.post(f"/api/sessions/{session_id}/advance").status_code == 200  # 0 still counts as scored


def test_one_word_answer_scores_zero_without_calling_the_llm(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    client.post(f"/api/sessions/{session_id}/ready")
    calls_before = len(mock_llm.calls)

    result = client.post(f"/api/sessions/{session_id}/answer", json={"text": "No."}).json()

    assert result["status"] == "scored"
    attempt = _stage_1_attempt(db_session, session_id)
    assert attempt.score == 0
    assert len(mock_llm.calls) == calls_before  # no Smart LLM call was made
    assert client.post(f"/api/sessions/{session_id}/advance").status_code == 200


def test_prompt_names_one_word_replies_as_zero_scores(mock_llm):
    mock_llm.queue_smart_response(SmartEvaluation(decision="final_score", score=0, rationale="Not an attempt."))

    evaluate_answer(_stage(), "I really have no idea what to say here", [], [])

    assert "No, I don't know, pass" in mock_llm.calls[-1]["system"]
