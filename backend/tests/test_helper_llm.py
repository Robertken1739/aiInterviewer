import pytest

import config
import llm.helper as helper
from db.models import Sequence
from llm.client import GroqNotConfiguredError, get_groq_client


def _sequence() -> Sequence:
    return Sequence(
        id=90201,
        title="Shielding Gas Selection",
        source_material=(
            "Argon-CO2 blends give a smoother arc for welding carbon steel.\n\n"
            "Pure CO2 is cheaper but produces more spatter and oxidation."
        ),
    )


def test_ask_helper_retrieves_relevant_chunks(mock_llm):
    """1. Query embedding + vector retrieval: the top-K chunks returned by
    ask_helper() must be the ones vector_store actually ranks highest for the
    question, not just "some" chunks."""
    sequence = _sequence()

    result = helper.ask_helper(sequence, "stage prompt", "which gas is smoother for welding carbon steel?", k=1)

    assert result["raw_chunks"] == ["Argon-CO2 blends give a smoother arc for welding carbon steel."]


def test_relevant_chunks_are_passed_to_groq(mock_llm):
    """2. The retrieved chunks must actually appear in the prompt sent to Groq."""
    sequence = _sequence()

    helper.ask_helper(sequence, "Recommend a shielding gas.", "which gas is smoother for carbon steel?", k=1)

    sent_prompt = mock_llm.calls[-1]["contents"]
    assert "Argon-CO2 blends give a smoother arc for welding carbon steel." in sent_prompt
    assert "Recommend a shielding gas." in sent_prompt  # the stage question is included too
    assert "which gas is smoother for carbon steel?" in sent_prompt  # the candidate's own question


def test_groq_model_name_comes_from_config(mock_llm, monkeypatch):
    monkeypatch.setattr(config.settings, "groq_model", "groq-test-model")
    sequence = _sequence()

    helper.ask_helper(sequence, "stage prompt", "any hints?")

    assert mock_llm.calls[-1]["model"] == "groq-test-model"


def test_helper_response_is_returned_correctly(mock_llm):
    """3. The Groq-generated text is returned as ai_response."""
    mock_llm._text = "Consider the trade off between arc stability and cost."
    sequence = _sequence()

    result = helper.ask_helper(sequence, "stage prompt", "any hints?")

    assert result["ai_response"] == "Consider the trade off between arc stability and cost."


def test_raw_chunks_and_source_labels_are_returned(mock_llm):
    """4. Raw retrieved chunks (plus a label per chunk) come back alongside the AI reply."""
    sequence = _sequence()

    result = helper.ask_helper(sequence, "stage prompt", "which gas is smoother?", k=2)

    assert len(result["raw_chunks"]) == 2
    assert len(result["source_labels"]) == 2
    assert all(sequence.title in label for label in result["source_labels"])


def test_missing_groq_api_key_raises_clear_configuration_error(monkeypatch):
    """8. A missing GROQ_API_KEY must fail with a specific, clear error --
    not an opaque SDK error from deep inside a network call."""
    monkeypatch.setattr(config.settings, "groq_api_key", None)

    with pytest.raises(GroqNotConfiguredError, match="GROQ_API_KEY"):
        get_groq_client()


def test_ask_helper_surfaces_missing_api_key_error(monkeypatch):
    monkeypatch.setattr(config.settings, "groq_api_key", None)
    sequence = _sequence()

    with pytest.raises(GroqNotConfiguredError):
        helper.ask_helper(sequence, "stage prompt", "any hints?")


def test_helper_reply_is_stripped_to_plain_text(mock_llm):
    mock_llm._text = "**Argon‑CO₂ blends** give a smoother arc — see (cost): \"cheaper\"; lower spatter."

    result = helper.ask_helper(_sequence(), "stage prompt", "any hints?")

    assert result["ai_response"] == "Argon CO2 blends give a smoother arc see cost cheaper lower spatter."
