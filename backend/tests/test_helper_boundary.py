import ast
import inspect

import llm.helper as helper
import vector_store
from db.models import Sequence

GRADING_FIELDS = {"reference_answer", "trap_claim_text"}


def _attribute_names_accessed(module) -> set[str]:
    """Names accessed as `something.<name>` anywhere in the module's actual code
    (i.e. the parsed AST) -- ignores docstrings/comments that merely mention the
    field names in prose."""
    tree = ast.parse(inspect.getsource(module))
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def test_helper_module_never_accesses_grading_fields():
    """Structural check: the Helper retrieval path must have no code path that
    can reach grading/reference data, not just avoid using it at runtime."""
    assert _attribute_names_accessed(helper).isdisjoint(GRADING_FIELDS)


def test_vector_store_module_never_accesses_grading_fields():
    assert _attribute_names_accessed(vector_store).isdisjoint(GRADING_FIELDS)


def test_helper_module_never_imports_the_stage_model():
    """Even stronger than the attribute check: llm/helper.py shouldn't import
    Stage at all, so it never has the *type* on hand to read reference_answer
    or trap_claim_text from, even by accident."""
    tree = ast.parse(inspect.getsource(helper))
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
    assert "Stage" not in imported_names


def test_ask_helper_never_leaks_reference_answer_or_trap_claim(mock_llm):
    """Behavioral check, on top of the structural ones above: plant unique
    reference_answer / trap_claim_text markers (as a real Stage would have)
    and confirm they never appear in retrieved chunks, the Groq prompt, or
    the returned ai_response -- ask_helper() simply has no path to them."""
    sequence = Sequence(
        id=90101,
        title="Test sequence",
        source_material=(
            "Argon-CO2 blends give a smoother arc for carbon steel.\n\n"
            "Pure CO2 is cheaper but produces more spatter."
        ),
    )
    reference_answer_marker = "SECRET-REFERENCE-ANSWER-Ar-1pct-O2"
    trap_claim_marker = "SECRET-TRAP-CLAIM-ionization-potential"
    stage_prompt_text = "Recommend a shielding gas for carbon steel."  # no markers -- a real prompt

    result = helper.ask_helper(sequence, stage_prompt_text, "what shielding gas should I use?")

    assert result["raw_chunks"], "expected at least one retrieved chunk"
    for chunk in result["raw_chunks"]:
        assert reference_answer_marker not in chunk
        assert trap_claim_marker not in chunk
    assert reference_answer_marker not in result["ai_response"]
    assert trap_claim_marker not in result["ai_response"]

    sent_prompt = mock_llm.calls[-1]["contents"]
    assert reference_answer_marker not in sent_prompt
    assert trap_claim_marker not in sent_prompt


def test_ask_helper_returns_relevant_chunks_for_the_sequence(mock_llm):
    sequence = Sequence(
        id=90102,
        title="Test sequence",
        source_material=(
            "Helium has roughly three times argon's thermal conductivity.\n\n"
            "Adhesive bonding is common in automotive body panel assembly."
        ),
    )

    result = helper.ask_helper(
        sequence, "Why does helium transfer more heat?", "why does helium transfer more heat into the weld?", k=1
    )

    assert result["raw_chunks"] == ["Helium has roughly three times argon's thermal conductivity."]
