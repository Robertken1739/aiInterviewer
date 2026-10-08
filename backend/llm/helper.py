"""Helper LLM: user question -> embedding -> vector search -> top-K neutral
chunks -> Groq -> ai_response + raw chunks + source labels.

Security boundary: this module only ever receives a `Sequence` and a plain
`stage_prompt_text` string -- never a `Stage` object -- so there is no code
path here that could reach `stage.reference_answer` or `stage.trap_claim_text`.
Nothing here ever sees Smart LLM scoring, candidate scores, or grading
rationale either -- those don't exist anywhere in this call chain.
"""

import re
import unicodedata

import vector_store
from config import settings
from db.models import Sequence
from llm.client import complete

SYSTEM_PROMPT = (
    "You are a technical interview coach helping a candidate prepare to answer "
    "an interview question. Use ONLY the background material provided below. "
    "Reply in 2 to 3 short plain sentences that point the candidate toward the "
    "relevant idea. Stay strictly on what the candidate asked. Do not elaborate, "
    "do not list options, and never name the recommended choice or conclusion, "
    "only hint at the reasoning. "
    "Write plain text only. No markdown, no bullet points, no bold, no headings, "
    "no emojis, no quotation marks, no parentheses, no dashes, no colons and no "
    "semicolons. Use only commas and full stops. "
    "You never score, grade, or evaluate the candidate."
)


def ask_helper(sequence: Sequence, stage_prompt_text: str, question: str, k: int = 3) -> dict:
    """Return {"ai_response": str, "raw_chunks": list[str], "source_labels": list[str]}."""
    chunks = vector_store.split_into_chunks(sequence.source_material)
    vector_store.index_chunks(sequence.id, chunks)
    retrieved = vector_store.search(sequence.id, question, k=k)
    source_labels = [f"{sequence.title} (chunk {chunks.index(chunk) + 1})" for chunk in retrieved]

    ai_response = _generate_reply(stage_prompt_text, question, retrieved)

    return {"ai_response": ai_response, "raw_chunks": retrieved, "source_labels": source_labels}


def _generate_reply(stage_prompt_text: str, question: str, chunks: list[str]) -> str:
    context = "\n\n".join(chunks) if chunks else "(no relevant background material found)"
    prompt = (
        f"Interview question the candidate is preparing to answer:\n{stage_prompt_text}\n\n"
        f"Background material:\n{context}\n\n"
        f"Candidate's question to you:\n{question}"
    )

    return _plain_text(complete(model=settings.groq_model, system=SYSTEM_PROMPT, prompt=prompt))


def _plain_text(text: str) -> str:
    """Enforce the prompt's punctuation rule in code, since models don't always obey it.

    Normalizes look-alike characters (subscript 2, non-breaking hyphen), turns
    dashes and slashes into spaces, then keeps only letters, digits, spaces,
    commas, full stops, apostrophes and percent signs.
    """
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[-‐-―/]", " ", text)
    text = re.sub(r"[^\w\s,.'%]|_", "", text)
    return re.sub(r"\s+", " ", text).strip()
