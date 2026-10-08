import uuid
from datetime import datetime, timedelta

from config import settings
from db.models import Message, StageAttempt
from tests.conftest import seed_sequence


def _create_session(client, sequence_id: int) -> str:
    response = client.post("/api/sessions", json={"sequence_id": sequence_id})
    assert response.status_code == 201
    return response.json()["id"]


def _complete_current_stage(client, session_id: str) -> dict:
    """Drive one stage through ready -> answer -> the bounded follow-up loop -> scored."""
    assert client.post(f"/api/sessions/{session_id}/ready").status_code == 200

    result = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my full answer here"}).json()
    while result["status"] == "followup":
        response = client.post(f"/api/sessions/{session_id}/followup", json={"response": "more detail"})
        assert response.status_code == 200
        result = response.json()
    assert result["status"] == "scored"
    return result


def test_happy_path_full_five_stage_walkthrough(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    for stage_number in range(1, 6):
        state = client.get(f"/api/sessions/{session_id}").json()
        assert state["current_stage"]["order_index"] == stage_number
        assert state["current_stage"]["helper_locked"] is False

        helper_response = client.post(f"/api/sessions/{session_id}/helper", json={"question": "any hints?"})
        assert helper_response.status_code == 200
        helper_body = helper_response.json()
        assert helper_body["ai_response"] == mock_llm._text
        assert helper_body["raw_chunks"] == ["Neutral background reading."]
        assert len(helper_body["source_labels"]) == 1

        assert client.post(f"/api/sessions/{session_id}/ready").status_code == 200
        locked_state = client.get(f"/api/sessions/{session_id}").json()
        assert locked_state["current_stage"]["helper_locked"] is True

        locked_helper_response = client.post(
            f"/api/sessions/{session_id}/helper", json={"question": "any hints?"}
        )
        assert locked_helper_response.status_code == 403

        answer = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my full answer here"}).json()
        assert answer["status"] == "followup"

        followup1 = client.post(
            f"/api/sessions/{session_id}/followup", json={"response": "more detail 1"}
        ).json()
        assert followup1["status"] == "followup"

        scored = client.post(
            f"/api/sessions/{session_id}/followup", json={"response": "more detail 2"}
        ).json()
        assert scored["status"] == "scored"
        # Deliberately no score/rationale here -- the candidate is never shown
        # a grade during the session (see EvaluationOut).
        assert "score" not in scored
        assert "rationale" not in scored

        advance = client.post(f"/api/sessions/{session_id}/advance")
        assert advance.status_code == 200
        body = advance.json()
        if stage_number < 5:
            assert body["status"] == "in_progress"
            assert body["current_stage"]["order_index"] == stage_number + 1
        else:
            assert body["status"] == "completed"
            assert "result" not in body  # candidate-facing response, no embedded scores

    results = client.get(f"/api/sessions/{session_id}/results")
    assert results.status_code == 200
    assert results.json()["status"] == "completed"
    assert len(results.json()["stage_results"]) == 5
    assert all(sr["score"] == 3 for sr in results.json()["stage_results"])
    assert results.json()["ai_steering_score"] == 3


def test_followup_flow_is_bounded_by_max_followups(client, db_session, mock_llm):
    """The mock scorer always wants another follow-up — the server, not the mock,
    must cut it off at MAX_FOLLOWUPS (2)."""
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    client.post(f"/api/sessions/{session_id}/ready")
    first = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my full answer to this question"}).json()
    assert first["status"] == "followup"

    second = client.post(f"/api/sessions/{session_id}/followup", json={"response": "r1"}).json()
    assert second["status"] == "followup"

    third = client.post(f"/api/sessions/{session_id}/followup", json={"response": "r2"}).json()
    assert third["status"] == "scored"

    attempts = db_session.query(StageAttempt).filter(StageAttempt.session_id == session_id).all()
    scored_attempt = next(a for a in attempts if a.stage.order_index == 1)
    followup_messages = (
        db_session.query(Message)
        .filter(Message.stage_attempt_id == scored_attempt.id, Message.phase == "followup")
        .all()
    )
    assert len(followup_messages) == 4  # ai q1, user r1, ai q2, user r2 -- exactly 2 rounds, no more


def test_helper_conversation_is_logged_to_message_table(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    client.post(f"/api/sessions/{session_id}/helper", json={"question": "what gas should I use?"})

    attempt = (
        db_session.query(StageAttempt)
        .filter(StageAttempt.session_id == session_id)
        .join(StageAttempt.stage)
        .filter_by(order_index=1)
        .one()
    )
    messages = db_session.query(Message).filter(Message.stage_attempt_id == attempt.id).order_by(Message.id).all()

    assert len(messages) == 2
    assert messages[0].phase == "helper"
    assert messages[0].speaker == "user"
    assert messages[0].content == "what gas should I use?"
    assert messages[1].phase == "helper"
    assert messages[1].speaker == "ai"
    assert messages[1].content == mock_llm._text


def test_second_helper_question_within_cooldown_is_rejected(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    first = client.post(f"/api/sessions/{session_id}/helper", json={"question": "hint 1?"})
    assert first.status_code == 200

    second = client.post(f"/api/sessions/{session_id}/helper", json={"question": "hint 2?"})
    assert second.status_code == 429


def test_helper_question_allowed_again_once_cooldown_has_passed(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    assert client.post(f"/api/sessions/{session_id}/helper", json={"question": "hint 1?"}).status_code == 200

    # Backdate the last helper message instead of sleeping in the test.
    last_message = db_session.query(Message).order_by(Message.id.desc()).first()
    last_message.created_at = datetime.utcnow() - timedelta(seconds=settings.helper_cooldown_seconds + 1)
    db_session.commit()

    response = client.post(f"/api/sessions/{session_id}/helper", json={"question": "hint 2?"})
    assert response.status_code == 200


def test_helper_rejected_once_stage_is_ready(client, db_session):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    client.post(f"/api/sessions/{session_id}/ready")
    response = client.post(f"/api/sessions/{session_id}/helper", json={"question": "hint?"})

    assert response.status_code == 403


def test_answer_rejected_before_ready(client, db_session):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    response = client.post(f"/api/sessions/{session_id}/answer", json={"text": "answer submitted too early"})

    assert response.status_code == 409


def test_answering_a_stage_twice_is_rejected(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    client.post(f"/api/sessions/{session_id}/ready")
    first = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my first full answer here"})
    assert first.status_code == 200

    second = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my second full answer here"})
    assert second.status_code == 409


def test_advance_rejected_before_current_stage_is_scored(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    client.post(f"/api/sessions/{session_id}/ready")
    answer = client.post(f"/api/sessions/{session_id}/answer", json={"text": "my full answer to this question"}).json()
    assert answer["status"] == "followup"  # not yet scored

    response = client.post(f"/api/sessions/{session_id}/advance")

    assert response.status_code == 409


def test_followup_rejected_when_no_answer_submitted_yet(client, db_session):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    client.post(f"/api/sessions/{session_id}/ready")
    response = client.post(f"/api/sessions/{session_id}/followup", json={"response": "nothing to respond to"})

    assert response.status_code == 409


def test_followup_rejected_once_stage_is_scored(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)
    _complete_current_stage(client, session_id)

    response = client.post(f"/api/sessions/{session_id}/followup", json={"response": "too late"})

    assert response.status_code == 409


def test_results_rejected_before_session_completed(client, db_session):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    response = client.get(f"/api/sessions/{session_id}/results")

    assert response.status_code == 409


def test_actions_rejected_once_session_is_completed(client, db_session, mock_llm):
    sequence = seed_sequence(db_session)
    session_id = _create_session(client, sequence.id)

    for _ in range(5):
        _complete_current_stage(client, session_id)
        client.post(f"/api/sessions/{session_id}/advance")

    state = client.get(f"/api/sessions/{session_id}").json()
    assert state["status"] == "completed"
    assert state["current_stage"] is None

    assert client.post(f"/api/sessions/{session_id}/helper", json={"question": "?"}).status_code == 409
    assert client.post(f"/api/sessions/{session_id}/ready").status_code == 409
    assert client.post(f"/api/sessions/{session_id}/answer", json={"text": "some longer answer text"}).status_code == 409


def test_unknown_session_id_returns_404(client, db_session):
    random_id = uuid.uuid4()

    assert client.get(f"/api/sessions/{random_id}").status_code == 404
    assert client.post(f"/api/sessions/{random_id}/ready").status_code == 404
    assert client.post(f"/api/sessions/{random_id}/helper", json={"question": "?"}).status_code == 404
    assert client.post(f"/api/sessions/{random_id}/answer", json={"text": "some longer answer text"}).status_code == 404


def test_sessions_cannot_reach_each_others_stages(client, db_session, mock_llm):
    """Two independent sessions on the same sequence share Stage rows via FK but
    must never share stage_attempt state."""
    sequence = seed_sequence(db_session)
    session_a = _create_session(client, sequence.id)
    session_b = _create_session(client, sequence.id)

    _complete_current_stage(client, session_a)
    client.post(f"/api/sessions/{session_a}/advance")

    state_a = client.get(f"/api/sessions/{session_a}").json()
    state_b = client.get(f"/api/sessions/{session_b}").json()

    assert state_a["current_stage"]["order_index"] == 2
    assert state_b["current_stage"]["order_index"] == 1
    assert state_b["current_stage"]["score"] is None
    assert state_b["current_stage"]["helper_locked"] is False

    attempts_b = db_session.query(StageAttempt).filter(StageAttempt.session_id == session_b).all()
    assert all(a.score is None and a.ready_at is None for a in attempts_b)
