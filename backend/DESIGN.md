# Backend Design — idolHire (MVP)

Source of truth for requirements: `baseDesign.md` (product loop) + `rawData/idolhire-question-bank-materials-joining-v1*.md` (concrete shape of the content: 5-stage sequences, one rubric axis per stage, model answers, seeded AI traps).

This revision replaces the earlier draft, which over-built for scale the product doesn't need yet (LangGraph, a separate vector store, optimistic locking, admin CRUD, 10 tables). Everything here is scoped to: **get the 12-step loop working, persisted, with one developer able to read the whole backend in one sitting.**

---

## 0. The 12-step loop this backend implements

1. Create interview session.
2. Select a fixed question sequence.
3. Show current stage/question.
4. User asks Helper for hints while preparing.
5. User clicks ready.
6. Server permanently disables Helper for that stage.
7. User submits answer.
8. Smart LLM evaluates it.
9. Smart LLM may ask a small bounded number of follow-ups.
10. Final score is stored.
11. Move to next stage.
12. After the final stage, produce the overall result.

Content shape (unchanged from the question bank): a **sequence** has 5 **stages** — anchor / constraint / contradiction / ai_trap / synthesis — each testing one axis (Technical Correctness, Trade-off Reasoning, Constraint Adaptability, AI Oversight & Skepticism, Communication Clarity). A 6th axis, AI-Steering Efficiency, is scored once per session from how the candidate used the Helper LLM across all 5 stages.

---

## 1. Backend architecture

```
backend/
  main.py            FastAPI app, mounts the router, creates tables on startup (dev)
  config.py           env-driven settings: DATABASE_URL, ANTHROPIC_API_KEY,
                       HELPER_MODEL, SMART_MODEL, MAX_FOLLOWUPS
  vector_store.py      Chroma-backed chunk store for Helper retrieval (see §5) —
                        chunking, embedding, indexing, top-K search. Isolated from
                        everything else: no other module's data can reach it.
  db/
    session.py         SQLAlchemy engine + SessionLocal + get_db() dependency
    models.py            all 5 ORM models (one file — see §2)
  routes/
    interview.py          every HTTP endpoint (see §3) — thin: parse request,
                           call a function in interview/flow.py, return it
  interview/
    flow.py                orchestration as plain functions (create_session,
                            get_state, ask_helper, mark_ready, submit_answer,
                            submit_followup, advance, get_results). Each takes
                            a DB session and does its own queries inline —
                            no repository/service class layer.
  llm/
    client.py                one function: build an Anthropic client from config
    helper.py                 ask_helper(sequence, question) -> list[str] — the
                               retrieve half of retrieve -> generate (see §5);
                               takes a Sequence, never a Stage
    smart.py                    evaluate_answer(...), score_ai_steering(...)
                                 (few-shot scoring examples live here as a constant)
  seed/
    seed_materials_joining.py    one-off script that loads the 5 sequences from
                                  the question bank into sequence/stage rows
```

~12 files. No `services/`, no `repositories/`, no dependency-injection container. `interview/flow.py` talks to SQLAlchemy directly; routes talk to `interview/flow.py`; `llm/*` is called from `interview/flow.py` when a stage transition needs it.

Deliberate choices baked into this shape:

- **No LangGraph.** The Helper LLM's retrieve step is one function call: embed the question, search Chroma, return the top-K chunks — see §5. There's no multi-step graph to model because there's no branching control flow, just a straight line.
- **A vector store, but the smallest one that does the job.** Semantic retrieval turned out to be needed even at MVP scale (see §5's revision note) — Chroma, running in-memory in the same process, with a dependency-free local embedding (no model download, no API key, nothing to configure).
- **No Redis.** All session state is in Postgres and read fresh on every request; there's no live in-memory cache to keep warm. (The vector store is a different kind of state — see §5 — and doesn't change this.)
- **No admin API.** The question bank is loaded once via `python -m seed.seed_materials_joining`, run by hand. Nothing about authoring sequences needs an HTTP surface yet.
- **No optimistic locking / version columns.** One candidate uses one session in one browser tab; a mutating endpoint does its check-then-write inside one DB transaction, which is enough concurrency safety for that access pattern (see §4 for the specific guard).
- **No provider abstraction.** `llm/helper.py` and `llm/smart.py` call the Anthropic SDK directly with two model names from config. There is exactly one provider; an interface for swapping it has no MVP payoff.
- **No summarization pipeline.** A session is capped at 5 stages. The Smart LLM gets the raw text of prior stages (prompt + answer + score), not a compressed summary — see §6.

---

## 2. Database schema

```
sequence 1───* stage
sequence 1───* interview_session
interview_session 1───* stage_attempt *───1 stage
stage_attempt 1───* message
```

5 tables. `sequence`/`stage` use plain integer PKs (static seed data — easy to write literal IDs in the seed script). `interview_session` uses a UUID PK because it doubles as the unguessable "resume this session" token the client holds onto; `stage_attempt`/`message` are internal rows always reached through a session, so plain integers are fine there too.

### `sequence`

| column | type | notes |
|---|---|---|
| id | integer pk | |
| title | text | e.g. "Shielding Gas Selection for a Robotic Welding Cell" |
| source_material | text | neutral lecture-note excerpt for this sequence — **all** the Helper LLM's retrieval step ever draws from |

This column is still the only place source material lives *durably* — it's the source of truth. What changed from the original draft: it's no longer sent to the Helper LLM as one blob. It gets split into paragraph chunks and indexed into a vector store for retrieval — see §5. That index is a rebuildable cache, not a second system of record, which is why it doesn't get a Postgres table of its own (see "Not a table: chunk embeddings" below) — adding one would mean keeping two stores in sync for data Postgres already owns.

### `stage`

| column | type | notes |
|---|---|---|
| id | integer pk | |
| sequence_id | integer fk → sequence | |
| order_index | int | 1–5, fixed order |
| stage_type | text | `anchor` / `constraint` / `contradiction` / `ai_trap` / `synthesis` — informational label, not a DB enum |
| prompt_text | text | shown to the candidate |
| trap_claim_text | text, nullable | only set for the `ai_trap` stage — the wrong copilot statement to present |
| reference_answer | text | grading notes — **Smart LLM only**, read exclusively from `interview/flow.py`'s evaluation path, never from the helper path |

`axis_tested` isn't a column: for this fixed 5-stage template the axis is a pure function of `order_index` (1→Technical Correctness, 2→Trade-off Reasoning, 3→Constraint Adaptability, 4→AI Oversight & Skepticism, 5→Communication Clarity), so it's a small constant dict in `llm/smart.py` instead of a second column that could drift out of sync with `stage_type`.

No `helper_disclosure_mode` column: the "hints only" policy is one hardcoded instruction string in `llm/helper.py`. If it ever needs to vary per stage, that's a one-line code change, not a reason to carry a DB column and an enum through the MVP.

### `interview_session`

| column | type | notes |
|---|---|---|
| id | uuid pk | the resume token — client stores this to reload state after a restart |
| sequence_id | integer fk → sequence | fixed at creation, never changes |
| candidate_email | text, nullable | free-text identifier, no auth in MVP |
| status | text | `in_progress` / `completed` |
| ai_steering_score | int, nullable | set once, at completion — see §6 |
| ai_steering_rationale | text, nullable | |
| started_at | timestamptz | |
| completed_at | timestamptz, nullable | |

All 5 `stage_attempt` rows for a session are created up front, at session creation, from the sequence's 5 stages. That single decision removes a whole layer of bookkeeping the previous design needed:

- No `current_stage_order` counter to keep in sync — "current stage" is just `SELECT * FROM stage_attempt JOIN stage ... WHERE session_id = ? AND score IS NULL ORDER BY stage.order_index LIMIT 1`.
- No "does the next stage_attempt exist yet" race on advance — it already exists, empty, waiting.
- `/advance` becomes close to a no-op (see §3) instead of a state transition to get right.

No `status = 'abandoned'`: nothing in the 12-step loop produces that state, and adding it now would just be a value nothing writes.

### `stage_attempt`

One row per (session, stage), all 5 created together.

| column | type | notes |
|---|---|---|
| id | integer pk | |
| session_id | uuid fk → interview_session | |
| stage_id | integer fk → stage | |
| ready_at | timestamptz, nullable | **set once, permanently, by `POST /ready`. Non-null = Helper is locked for this stage. This is the server-side enforcement point.** |
| answer_text | text, nullable | set by `POST /answer` |
| score | int, nullable | 1–5, set once evaluation finishes |
| score_rationale | text, nullable | |

Unique constraint: `(session_id, stage_id)`.

There's no `status` enum. The stage's phase is fully determined by which of the three nullable fields are filled, so there's nothing to keep in sync with them:

| `ready_at` | `answer_text` | `score` | phase |
|---|---|---|---|
| null | — | — | preparing (Helper available) |
| set | null | — | answering (Helper locked, no answer yet) |
| set | set | null | evaluating (Smart LLM may still be asking follow-ups) |
| set | set | set | done |

This table replaces the old 4-value `status` enum *and* removes the risk of `status` disagreeing with the data — a bug can't leave `status='scored'` next to `score IS NULL`, because there is no separate `status` to get out of sync.

### `message`

Every Helper-phase and follow-up-phase exchange, in one table.

| column | type | notes |
|---|---|---|
| id | integer pk | |
| stage_attempt_id | integer fk → stage_attempt | |
| phase | text | `helper` / `followup` |
| speaker | text | `user` / `ai` |
| content | text | |
| created_at | timestamptz | ordering is by `id`/`created_at` — no separate turn-index counter to race on |

This one table replaces the old `helper_turn` and `followup_turn` tables. They had near-identical shapes once retrieval (and its `retrieved_chunk_ids` column) was removed; splitting them bought nothing. `phase='helper'` rows across a session are exactly the input to the AI-Steering Efficiency score (§6); `phase='followup'` rows for a stage are exactly the evaluation conversation for that stage.

### Not a table: chunk embeddings

Chunked source material and its embeddings live only in the vector store (§5), keyed by `sequence_id`, never in Postgres. Two reasons: (1) it's fully derivable from `sequence.source_material`, which Postgres already owns — a `knowledge_chunk` table would just be a second copy that could drift out of sync; (2) keeping it out of Postgres means there's no ID-mirroring between two databases to keep consistent, which was the actual complexity cost the original draft's `knowledge_chunk` table + separate vector store carried. `sequence_id` alone is enough to look chunks up.

### Not a table: few-shot scoring examples

The calibration examples that ground Smart LLM scoring ("give some previous examples of scoring so scoring isn't super random" — `baseDesign.md`) are static content, never mutated at runtime. They live as a constant in `llm/smart.py`, not a `scoring_example` table — one less table, one less query on every scoring call, and they sit right next to the prompt code that uses them.

### Not a table: interviewee

No `interviewee` table. `interview_session.candidate_email` is a plain nullable column. There's no login, no "list my past sessions" requirement in the 12-step loop — a session is reached by its UUID, full stop. A real user/account table is exactly the kind of Future feature this doc shouldn't be shaped around (see Deferred Complexity).

---

## 3. API endpoints

All under `/api`. Blocking calls throughout — an endpoint that needs an LLM response `await`s it and returns.

| Method | Path | Purpose |
|---|---|---|
| GET | `/sequences` | list seeded sequences (id, title) so the caller can pick one |
| POST | `/sessions` | body `{sequence_id, candidate_email?}` → creates `interview_session` + all 5 `stage_attempt` rows, returns session state |
| GET | `/sessions/{id}` | full current state: status, current stage's prompt (+ trap claim if applicable), whether Helper is locked, messages so far for the current stage. **This one endpoint is what makes a page reload/server restart resumable** — the client only needs to remember the session id. |
| POST | `/sessions/{id}/helper` | body `{message}` → Helper LLM reply. **403 if the current stage's `ready_at` is set.** |
| POST | `/sessions/{id}/ready` | sets `ready_at = now()` on the current stage_attempt if not already set (idempotent — calling it twice is a no-op, not an error) |
| POST | `/sessions/{id}/answer` | body `{text}` → requires `ready_at` set and `answer_text` null; stores the answer, calls the Smart LLM, returns either a follow-up question or the final score |
| POST | `/sessions/{id}/followup` | body `{response}` → requires the stage to be mid-evaluation (`answer_text` set, `score` null); logs the response, calls the Smart LLM again, returns another follow-up or the final score |
| POST | `/sessions/{id}/advance` | requires the current stage to be scored; if another stage_attempt still has `score IS NULL`, just returns its prompt (nothing to write — the next row already exists); if none remain, computes the AI-Steering Efficiency score, marks the session `completed`, and returns the full results |
| GET | `/sessions/{id}/results` | per-stage scores/rationale + `ai_steering_score`/`ai_steering_rationale`; meaningful once `status = completed` |

8 endpoints. No `/admin/*`, no streaming variants, no pause/resume endpoint (a session is just re-fetched via `GET /sessions/{id}` — there's no separate "paused" state to enter or leave).

---

## 4. Interview session state flow

One flat progression per stage, enforced by `interview/flow.py`, not by a stored state machine:

```
 preparing  ──POST /ready──►  answering  ──POST /answer──►  evaluating  ──final_score──►  done
(Helper OK)                  (Helper 403)                  (may loop on
                                                              POST /followup,
                                                              capped at
                                                              MAX_FOLLOWUPS)
```

- `POST /sessions/{id}/helper` and `POST /sessions/{id}/ready` both start by loading the current stage_attempt row; `helper` rejects if `ready_at is not None`, matching the "Helper LLM unavailable once you start answering" requirement directly off that one column.
- The evaluating→done step is a loop only in the sense that `POST /answer` and `POST /followup` both call the same `evaluate_answer()` function in `llm/smart.py`, which returns either `("followup", question)` or `("final", score, rationale)`. `interview/flow.py` counts existing `phase='followup'` messages for the stage and forces `final` once `MAX_FOLLOWUPS` is hit, regardless of what the model would have asked.
- **Concurrency guard, without a version column**: the mutating endpoints (`helper`, `ready`, `answer`, `followup`) each load the stage_attempt row with `SELECT ... FOR UPDATE` inside one transaction, check the relevant field is still in the expected state, then write. That's enough for "one candidate, one tab" — two genuinely simultaneous requests on the same stage serialize on the row lock instead of racing. No optimistic-locking column, no retry logic.
- Session-level status (`in_progress`/`completed`) is a plain column, written exactly once, in `POST /advance`, at the single well-defined moment all 5 stages are scored — not derived on every read, because it only ever transitions one way, one time.
- **Restart recovery**: every one of the above writes commits before the endpoint returns. There is no server-held in-memory session state at all — `GET /sessions/{id}` after a restart reads the same rows a live server would have, so "resume after restart" isn't a separate feature, it's just what the persistence already guarantees.

---

## 5. Helper LLM architecture

> **Revision note.** The original draft of this section stuffed a sequence's entire `source_material` into every Helper prompt and skipped retrieval, reasoning the corpus was too small to need it. That was wrong: semantic retrieval over the source material is a real MVP requirement, not a later-scale concern, so this section now describes an actual `retrieve` step against a vector store. What's still deferred is the `generate` half — turning retrieved chunks into a written reply via a cheap model call. `llm/helper.ask_helper()` currently returns the raw top-K chunks; wiring it to an actual model call is separate follow-up work (see Deferred Complexity) once an LLM provider dependency and API key are actually being introduced.

```
user question
     │
     ▼
llm/helper.ask_helper(sequence, question, k=3):
     │
     ├─► vector_store.split_into_chunks(sequence.source_material)
     │        (paragraph-level split)
     │
     ├─► vector_store.index_chunks(sequence.id, chunks)
     │        (delete-then-add — idempotent, always re-run, no "is this
     │         stale" bookkeeping)
     │
     └─► vector_store.search(sequence.id, question, k)
              │
              ▼
        embed question  ──►  Chroma similarity search,
        (local hashing      filtered to this sequence_id
         embedding,
         no model download,
         no API call)
              │
              ▼
        top-K neutral chunks  ──[not yet wired]──►  cheap Helper LLM  ──►  written reply
              │
              ▼
        return chunks   (this is the current return value — the reply half
                          of "response + raw retrieved chunks" is pending)
```

One retrieval function, no graph. LangGraph's value is branching/looping control flow; this doesn't branch — embed, search, return — so a plain function is the whole implementation.

**Why an in-memory vector store is enough.** `vector_store.py` runs a Chroma `EphemeralClient` (in-process, nothing written to disk) instead of a persistent store. This works *because* the index is always rebuilt from `sequence.source_material` before every search (`index_chunks` is called unconditionally, not just once) — Postgres is the only durable copy of the source material, so there's nothing to lose on restart. This is different from the session-state persistence guarantee in §4 (which is about not losing a candidate's *progress*); the vector index is a derived cache, not a system of record, so it doesn't need the same guarantee.

**Why a hashing embedding instead of a real model.** `vector_store._embed_one()` is a deterministic bag-of-words hash into a fixed-size vector — no ONNX/sentence-transformers model download, no embedding API, no API key. It's a real trade-off (worse semantic recall than a trained embedding model, especially on paraphrases), but it's enough to rank a handful of lecture-note paragraphs per sequence, keeps the whole retrieval path runnable offline, and the swap point is a single function — nothing calling `vector_store.search()` would need to change. This is exactly the kind of "simplest thing that satisfies the requirement" call `CLAUDE.md` asks for; revisit it if retrieval quality actually becomes a problem, not before.

**Security boundary**, enforced structurally rather than by a runtime check: `vector_store.py` and `llm/helper.py` only ever handle `Sequence.source_material` and the chunks derived from it. `ask_helper()`'s signature takes a `Sequence`, not a `Stage` — there is no code path in either module that could reach `stage.reference_answer` or `stage.trap_claim_text`, because neither module ever receives a `Stage` object at all. `tests/test_helper_boundary.py` asserts this structurally (parses each module's AST and checks neither field is ever accessed as an attribute) as well as behaviorally.

Disclosure policy (hints only, never the direct answer) and the actual generation call both still belong to the not-yet-built `generate` step — see the revision note above.

---

## 6. Smart LLM architecture

```
POST /sessions/{id}/answer {text}  or  POST /sessions/{id}/followup {response}
        │
        ▼
llm/smart.evaluate_answer(stage, prior_stage_history, followup_messages, answer_text):
    context =
      • stage.prompt_text (+ stage.trap_claim_text if this is the ai_trap stage)
      • stage.reference_answer          (grading notes — never shown to the candidate)
      • FEW_SHOT_EXAMPLES for stage's axis   (constant in this file)
      • prior_stage_history: raw {prompt_text, answer_text, score} for each
        already-scored stage in this session — no summarization, 5 stages max
      • this stage's answer_text + any followup_turns so far
    structured output (one of):
      { decision: "followup", question: str }
      { decision: "final",   score: int, rationale: str }
```

- **Bounded follow-ups**: `interview/flow.py` holds `MAX_FOLLOWUPS` (config, e.g. 2) and counts `phase='followup'` messages for the stage before calling `evaluate_answer`; once the cap is hit it asks for a final decision only. This is a plain counter check, not a modeled state.
- **No summarization pipeline**: prior-stage context is the raw prompt/answer/score for up to 4 previous stages — small enough to pass as-is. The original design's "always summarize with a cheap model" step is cut; if sequences grow past 5 stages or answers get long enough to matter, add summarization then (see Deferred Complexity), not preemptively.
- **Structured output** via a Pydantic response model, so `interview/flow.py` can branch on `decision` without parsing free text.
- **AI-Steering Efficiency**, computed once in `POST /advance` when the 5th stage is scored: `llm/smart.score_ai_steering(all phase='helper' messages in the session) -> (score, rationale)`, written to `interview_session.ai_steering_score`/`ai_steering_rationale`.
- **Sequence selection**: fixed. `POST /sessions` takes a `sequence_id` chosen by the caller (or the client just always passes the one seeded sequence for the first demo); there's no adaptive "Smart LLM picks the next question" logic in MVP, even though `baseDesign.md` leaves that door open.

---

## Deferred Complexity

Everything below is a real, considered future direction — deliberately not built now, and nothing above depends on it existing:

- **Helper LLM generation** — `llm/helper.ask_helper()` currently returns retrieved chunks only; wiring the actual "cheap model turns chunks into a reply" call (plus the hints-only disclosure policy prompt) is the next increment, once an LLM provider dependency and API key are introduced.
- **A real embedding model or API** in place of `vector_store`'s deterministic hashing embedding — revisit if retrieval quality on paraphrased/indirect questions actually becomes a problem.
- **Persistent/shared vector index** — `vector_store` is in-memory per process and rebuilt from Postgres on every Helper call; move to a persistent or shared store if per-call re-indexing stops being cheap (e.g. much larger `source_material`, or many processes needing a shared index).
- **Logging Helper-phase turns to the `message` table** — deferred alongside generation, since there's no AI reply to log yet, only retrieved chunks.
- **LangGraph** — once the Helper LLM's flow actually branches (multi-hop lookup, tool use, re-ranking) rather than being a straight line.
- **Redis** — a live-session cache, needed once concurrency or multi-instance deployment makes a DB round-trip per request too slow.
- **Admin API** for authoring/editing sequences — replaces the manual seed script once non-developers need to add content.
- **Optimistic locking / version columns** — if usage moves beyond "one candidate, one tab" and row-level `FOR UPDATE` locking stops being sufficient.
- **Real auth** (accounts, passwords/OAuth, session listing) — `candidate_email` is a placeholder, not identity.
- **Resume / job-description ingestion and personalization** — explicitly out of scope per `baseDesign.md`; would add columns to a real interviewee/profile table and feed into both LLM prompts.
- **Adaptive sequence/question selection** — Smart LLM choosing the next sequence based on running performance, instead of a fixed pick per session.
- **Streaming responses** (SSE/websocket) for both Helper and Smart LLM turns, for a chat-like typing effect.
- **Per-stage disclosure-mode tuning** stored in the DB, if "hints vs. direct answer" ever needs to vary by stage without a code change.
- **Context summarization** for the Smart LLM, if sequences grow past 5 stages or answers get long enough that raw prior-stage history stops fitting comfortably in one prompt.
- **Provider abstraction**, if a second LLM provider is ever actually needed — not before.
- **Multi-domain / versioned question banks**, session `abandoned` state, pause/resume as an explicit state — none of these are exercised by the 12-step loop today.
