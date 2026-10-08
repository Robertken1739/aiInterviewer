"""Groq chat client, built from config.

Raises a clear, specific error immediately if GROQ_API_KEY isn't set,
instead of letting the SDK fail with an opaque error deep inside a
chat-completion call.
"""

import json

from groq import Groq
from pydantic import BaseModel

from config import settings


class GroqNotConfiguredError(Exception):
    """GROQ_API_KEY is not set."""


def get_groq_client() -> Groq:
    if not settings.groq_api_key:
        raise GroqNotConfiguredError(
            "GROQ_API_KEY is not set. Add it to backend/.env to use the Helper LLM."
        )
    return Groq(api_key=settings.groq_api_key)


def complete(*, model: str, system: str, prompt: str, schema: type[BaseModel] | None = None) -> str:
    """One chat completion; returns the reply text.

    With `schema`, Groq's JSON mode is switched on and the schema is spelled out
    in the system prompt, so the reply is a JSON string the caller validates
    against that pydantic model.
    """
    kwargs = {}
    if schema is not None:
        system = (
            f"{system}\n\nRespond with a single JSON object matching this JSON schema, and nothing else:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        kwargs["response_format"] = {"type": "json_object"}

    response = get_groq_client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        **kwargs,
    )
    return response.choices[0].message.content or ""
