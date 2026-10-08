"""Smart LLM: candidate answer -> Groq -> follow-up OR final score.

Security boundary (the reverse of llm/helper.py's): this module MAY read
stage.reference_answer / stage.trap_claim_text -- that's its whole job -- but
its OUTPUT contract (SmartEvaluation) only ever has `question`/`score`/
`rationale` fields. There is no field this module can return that carries the
reference answer back out; `interview/flow.py` only ever persists/forwards
`score` and `rationale` to the candidate (see schemas.EvaluationOut), never
anything read from `stage` directly. The rationale is instructed, in the
system prompt, to be safe to show the candidate -- that part is a prompt
contract, not something code can force, so keep it in mind if you change the
system prompt.
"""

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from config import settings
from db.models import Stage
from llm.client import complete

SYSTEM_PROMPT = (
    "You are the scoring engine for a technical mock-interview platform. You "
    "evaluate a candidate's answer against ONE specific rubric axis for the "
    "current interview stage, using the confidential reference answer and "
    "grading notes provided to you below. You may ask at most one clarifying "
    "follow-up question before scoring, if the candidate's answer is genuinely "
    "too vague to grade fairly -- otherwise score immediately. Score on a 0-5 "
    "scale (5 = excellent, 1 = a genuine but poor attempt). Give exactly 0 when "
    "the answer is irrelevant to the question, random or nonsense text, blank, "
    "or makes no real attempt to address what was asked, for example a one word "
    "reply such as No, I don't know, pass, or simply repeating the question. "
    "Never give 1 to an answer that is not a genuine attempt at the question: "
    "if your rationale would say the answer does not address the question at "
    "all, the score must be 0. "
    "Your rationale MUST be safe to show directly to the candidate: never "
    "quote or paraphrase the reference answer, never mention the reference "
    "answer's existence, internal grading notes, scoring examples, or your "
    "own reasoning process -- just explain, in plain terms a candidate could "
    "read, why the answer earned that score."
)

AXIS_BY_ORDER_INDEX = {
    1: "Technical Correctness",
    2: "Trade-off Reasoning",
    3: "Constraint Adaptability",
    4: "AI Oversight & Skepticism",
    5: "Communication Clarity",
}

RUBRIC_BY_AXIS = {
    "Technical Correctness": (
        "Does the candidate's answer demonstrate accurate, sound technical reasoning for the question asked?"
    ),
    "Trade-off Reasoning": (
        "Does the candidate correctly weigh costs and benefits, and explicitly state what is being given up "
        "given the new constraint, rather than just picking a cheaper option with no justification?"
    ),
    "Constraint Adaptability": (
        "Does the candidate notice that the underlying facts/constraints have changed and adapt their prior "
        "recommendation accordingly, rather than blindly repeating it?"
    ),
    "AI Oversight & Skepticism": (
        "Does the candidate correctly identify and correct a flawed or misleading claim, rather than accepting "
        "it uncritically?"
    ),
    "Communication Clarity": (
        "Can the candidate explain the technical decision clearly, in terms appropriate for a non-technical audience?"
    ),
}

# Small, generic calibration anchors -- not tied to any one sequence, just
# grounding what a high vs. low score looks like, per baseDesign.md's
# "give some previous examples of scoring so scoring isn't super random".
SCORING_EXAMPLES = [
    {
        "score": 0,
        "note": (
            "Answer is irrelevant to the question, random or nonsense text, or makes no real attempt to "
            "address what was asked (for example an unrelated sentence, a greeting, or filler)."
        ),
    },
    {
        "score": 5,
        "note": (
            "Answer is technically correct, directly engages the specific constraint or trap in the question, "
            "and states its reasoning explicitly rather than just asserting a conclusion."
        ),
    },
    {
        "score": 3,
        "note": (
            "Answer reaches a defensible conclusion but is thin on justification, or only partially addresses "
            "the constraint/trap introduced at this stage."
        ),
    },
    {
        "score": 1,
        "note": (
            "Answer is technically wrong for this stage's question, or ignores the constraint/trap entirely "
            "(e.g. repeats an earlier answer unchanged when the situation has since changed), but it is a "
            "genuine attempt to answer the question that was asked."
        ),
    },
]

# An answer this short can't be a real attempt, so it is scored 0 without asking
# the model, which was observed giving 1 to a bare "No." even when told not to.
MIN_ANSWER_WORDS = 3
NON_ANSWER_RATIONALE = "No real answer was given, so this stage scores 0."


def is_non_answer(answer_text: str) -> bool:
    return len(answer_text.split()) < MIN_ANSWER_WORDS


FORCE_FINAL_INSTRUCTION = (
    'The follow-up budget for this stage has been used up. You MUST return decision="final_score" now -- '
    "do not request another follow-up under any circumstances."
)
MAY_FOLLOWUP_INSTRUCTION = (
    "If the candidate's answer is too vague or ambiguous to score fairly, you may ask ONE targeted follow-up "
    'question by returning decision="follow_up" instead of scoring immediately. Otherwise, score it now.'
)


class SmartEvaluation(BaseModel):
    decision: Literal["follow_up", "final_score"]
    question: str | None = None
    score: int | None = Field(default=None, ge=0, le=5)
    rationale: str | None = None

    @model_validator(mode="after")
    def _required_fields_for_decision(self) -> "SmartEvaluation":
        if self.decision == "follow_up" and not self.question:
            raise ValueError('decision="follow_up" requires a non-empty question')
        if self.decision == "final_score" and (self.score is None or not self.rationale):
            raise ValueError('decision="final_score" requires both score and rationale')
        return self


class SmartLLMInvalidOutputError(Exception):
    """The LLM's response couldn't be parsed into a valid SmartEvaluation, or
    (when a final score was required) it asked for another follow-up anyway."""


def evaluate_answer(
    stage: Stage,
    answer_text: str,
    followup_history: list[dict],
    previous_stage_summaries: list[dict],
    force_final: bool = False,
) -> dict:
    """Return {"decision": "followup", "question": str} or
    {"decision": "final", "score": int, "rationale": str} -- the same internal
    shape interview/flow.py already branches on.
    """
    prompt = _build_prompt(stage, answer_text, followup_history, previous_stage_summaries, force_final)

    text = complete(model=settings.groq_smart_model, system=SYSTEM_PROMPT, prompt=prompt, schema=SmartEvaluation)
    try:
        evaluation = SmartEvaluation.model_validate_json(text)
    except ValidationError as exc:
        raise SmartLLMInvalidOutputError("Smart LLM did not return a valid structured evaluation.") from exc
    if force_final and evaluation.decision != "final_score":
        raise SmartLLMInvalidOutputError("Smart LLM requested another follow-up after the follow-up limit.")

    if evaluation.decision == "follow_up":
        return {"decision": "followup", "question": evaluation.question}
    return {"decision": "final", "score": evaluation.score, "rationale": evaluation.rationale}


def _build_prompt(
    stage: Stage,
    answer_text: str,
    followup_history: list[dict],
    previous_stage_summaries: list[dict],
    force_final: bool,
) -> str:
    axis = AXIS_BY_ORDER_INDEX[stage.order_index]
    sections = [
        f"Rubric axis for this stage: {axis}.",
        f"Rubric: {RUBRIC_BY_AXIS[axis]}",
        f"Question posed to the candidate:\n{stage.prompt_text}",
    ]

    if stage.trap_claim_text:
        sections.append(
            "An AI copilot showed the candidate this claim, which the candidate was expected to scrutinize "
            f"(it may be wrong -- catching that is part of what this stage tests):\n{stage.trap_claim_text}"
        )

    sections.append(
        "Reference answer / grading notes (confidential -- for your evaluation only, never reveal this to "
        f"the candidate):\n{stage.reference_answer}"
    )

    if previous_stage_summaries:
        summary_lines = "\n".join(
            f"- Stage {s['order_index']} ({s['stage_type']}): scored {s['score']}/5 -- {s['rationale']}"
            for s in previous_stage_summaries
        )
        sections.append(f"Compact summary of the candidate's performance on earlier stages this session:\n{summary_lines}")

    sections.append(f"Candidate's answer for this stage:\n{answer_text}")

    if followup_history:
        transcript = "\n".join(f"{m['speaker']}: {m['content']}" for m in followup_history)
        sections.append(f"Follow-up conversation so far on this stage:\n{transcript}")

    examples = "\n".join(f"- score {e['score']}/5: {e['note']}" for e in SCORING_EXAMPLES)
    sections.append(f"General scoring calibration examples (not specific to this question):\n{examples}")

    sections.append(FORCE_FINAL_INSTRUCTION if force_final else MAY_FOLLOWUP_INSTRUCTION)

    return "\n\n".join(sections)


FINALIZATION_SYSTEM_PROMPT = (
    "You produce the closing summary for a completed technical mock interview. You are given the "
    "candidate's score and rationale on each of five rubric axes, plus the full transcript of the "
    "candidate's questions to a 'Helper' hint assistant during preparation (if any). Do two things:\n\n"
    "1. Write 2-4 sentences of honest, constructive overall feedback synthesizing performance across all "
    "five axes. This MUST be safe to show the candidate directly -- no internal grading notes, reference "
    "answers, or scoring examples, just plain feedback on their performance.\n\n"
    "2. Score 'AI-Steering Efficiency' on a 1-5 scale: how effectively the candidate used the Helper "
    "assistant. Reward focused, well-targeted questions that show the candidate reasoning for themselves; "
    "penalize asking the Helper to just solve the problem outright, or excessive/unfocused querying. A "
    "candidate who never used the Helper is not automatically penalized or rewarded for that alone -- "
    "judge based on what actually happened in the transcript."
)


class SessionFinalization(BaseModel):
    overall_feedback: str
    ai_steering_score: int = Field(ge=1, le=5)
    ai_steering_rationale: str


def finalize_session(stage_results: list[dict], helper_messages: list[dict]) -> dict:
    """One Groq call that closes out a completed session.

    stage_results: [{"order_index", "axis", "score", "rationale"}, ...] for all 5 stages.
    helper_messages: [{"speaker", "content"}, ...] every Helper-phase message across the whole session.
    Returns {"overall_feedback": str, "ai_steering_score": int, "ai_steering_rationale": str}.
    """
    prompt = _build_finalization_prompt(stage_results, helper_messages)

    text = complete(
        model=settings.groq_smart_model, system=FINALIZATION_SYSTEM_PROMPT, prompt=prompt, schema=SessionFinalization
    )
    try:
        result = SessionFinalization.model_validate_json(text)
    except ValidationError as exc:
        raise SmartLLMInvalidOutputError("Smart LLM did not return a valid session finalization.") from exc

    return {
        "overall_feedback": result.overall_feedback,
        "ai_steering_score": result.ai_steering_score,
        "ai_steering_rationale": result.ai_steering_rationale,
    }


def _build_finalization_prompt(stage_results: list[dict], helper_messages: list[dict]) -> str:
    results_lines = "\n".join(
        f"- Stage {r['order_index']} ({r['axis']}): {r['score']}/5 -- {r['rationale']}" for r in stage_results
    )
    sections = [f"Per-stage results:\n{results_lines}"]

    if helper_messages:
        transcript = "\n".join(f"{m['speaker']}: {m['content']}" for m in helper_messages)
        sections.append(f"Candidate's Helper conversation across the whole session:\n{transcript}")
    else:
        sections.append("The candidate did not use the Helper at all during this session.")

    return "\n\n".join(sections)
