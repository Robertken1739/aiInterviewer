# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Philosophy

This is an MVP.

Prefer the simplest implementation that satisfies the requirements.

Follow YAGNI:

- Do not implement future requirements.
- Do not introduce abstractions without a current use case.
- Do not introduce a framework/library when a simple Python implementation is sufficient.
- Prefer a small number of understandable modules.
- Prefer explicit code over excessive abstraction.
- Do not create repositories/services/factories/interfaces merely because they are considered "best practice".
- Do not optimize for scale that the MVP does not need.

Before introducing:

- a new dependency
- an abstraction layer
- a design pattern
- a background worker
- caching
- a queue
- a separate service
- LangGraph

first ask whether the same requirement can be solved more simply.

When there are multiple valid designs, choose the simplest one that is maintainable and testable.

Do not build for hypothetical future requirements.

## Repository state

This is an early-stage project with two independent apps and no shared build tooling between them:

- `frontend/` — a Vite + React 19 + Tailwind v4 SPA. Currently just the default scaffold (`App.jsx` renders a placeholder).
- `backend/` — planned FastAPI service. `backend/main.py` is currently empty; nothing is implemented yet. The full intended design lives in `backend/DESIGN.md` (see below) — read it before writing backend code, since it documents specific decisions about what _not_ to build.

There is no root-level build/test command; each app is developed from its own directory.

## Commands

Frontend (run from `frontend/`):

```
npm install
npm run dev       # Vite dev server
npm run build     # production build
npm run lint      # eslint
npm run preview   # preview a production build
```

Backend: no dependency manifest or run command exists yet (`backend/` has no `requirements.txt`/`pyproject.toml`). Follow `backend/DESIGN.md`'s proposed structure when scaffolding it.

## Product concept

An AI interview practice tool. A candidate works through a fixed **sequence** of 5 **stages** (anchor → constraint → contradiction → AI trap → synthesis), each testing one rubric axis (Technical Correctness, Trade-off Reasoning, Constraint Adaptability, AI Oversight & Skepticism, Communication Clarity), plus a transcript-wide AI-Steering Efficiency score. Two LLM roles are involved:

- **Helper LLM** — a cheap model the candidate can query for hints while preparing an answer, scoped to neutral source material only.
- **Smart LLM** — a capable model that delivers the stage prompt, asks a bounded number of follow-ups, and scores the answer.

The original product requirements are in `baseDesign.md`. The concrete question bank (5 seeded sequences, materials-joining/manufacturing domain, with model answers and seeded AI-trap claims) is in `rawData/idolhire-question-bank-materials-joining-v1.md` and its companion `-ANSWERS.md`.

## Backend architecture (per `backend/DESIGN.md`)

Read the full doc before implementing — it explains _why_ each simplification was made, not just what to build. Key points that span multiple files/decisions:

- **Directory layout**: `main.py`, `config.py`, `db/` (SQLAlchemy engine + all models in one `models.py`), `routes/interview.py` (thin HTTP layer), `interview/flow.py` (all orchestration logic as plain functions, no service/repository classes), `llm/` (`helper.py`, `smart.py`, direct Anthropic SDK calls, no provider abstraction), `seed/` (one-off script loading the question bank into the DB).
- **5 DB tables total**: `sequence`, `stage`, `interview_session`, `stage_attempt`, `message`. No vector store, no separate `interviewee`/`scoring_example` tables — those were deliberately collapsed or moved to code constants.
- **Hard data separation**: `sequence.source_material` is the only thing the Helper LLM ever reads; `stage.reference_answer` and `stage.trap_claim_text` are read exclusively from the Smart LLM path (`llm/smart.py`). This separation is structural (which file touches which column), not just a prompt instruction — don't blur it when implementing.
- **No `status` enum for stage progress.** A stage's phase is derived from which of `stage_attempt.ready_at` / `answer_text` / `score` are set (see the table in DESIGN.md §2). Server-side Helper lockout is enforced by checking `ready_at IS NOT NULL` — this is the mechanism that makes the Helper LLM permanently unavailable once a candidate starts answering.
- **All 5 `stage_attempt` rows are created upfront** at session creation (not lazily as the candidate advances), which is what lets "current stage" and "advance" stay simple queries instead of a tracked counter.
- Deliberately **not** used in the MVP, and shouldn't be reintroduced without a reason documented in DESIGN.md's "Deferred Complexity" section: LangGraph, a separate vector store/embeddings, Redis, an admin API, optimistic-locking/version columns, a multi-provider LLM abstraction, and prior-stage summarization (raw stage history is passed instead, since a session is capped at 5 stages).
