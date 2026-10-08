# idolHire — Backend

FastAPI backend for the idolHire MVP. Architecture and design rationale live in [`DESIGN.md`](DESIGN.md); this file is just "how do I run it."

The flow: create a session → prepare each of 5 stages with the Groq-backed Helper (hints only, retrieval over a small Chroma vector store) → click ready (permanently locks the Helper for that stage) → submit an answer → Groq Smart LLM scores it (with up to `MAX_FOLLOWUPS` bounded follow-up questions) → advance → after stage 5, get a final result with all 5 rubric scores, an overall score/feedback, and an AI-Steering Efficiency score.

## Prerequisites

- Python 3.12+
- Docker (for Postgres — or point `DATABASE_URL` at any Postgres 14+ you already have running)
- A Groq API key ([console.groq.com](https://console.groq.com))

## 1. Start PostgreSQL

```bash
docker run -d --name aiinterviewer-postgres \
  -e POSTGRES_USER=aiinterviewer -e POSTGRES_PASSWORD=aiinterviewer -e POSTGRES_DB=aiinterviewer \
  -p 5432:5432 postgres:16-alpine
```

(If you already have Postgres running some other way, just make sure `DATABASE_URL` below points at it.)

## 2. Set up the Python environment

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows: .venv\Scripts\Activate.ps1 in PowerShell
pip install -r requirements-dev.txt
```

## 3. Configure environment variables

```bash
cp .env.example .env
```

Then edit `backend/.env`:

```text
DATABASE_URL=postgresql+psycopg://aiinterviewer:aiinterviewer@localhost:5432/aiinterviewer
GROQ_API_KEY=your-key-here            # required — never commit this file, it's gitignored
GROQ_MODEL=openai/gpt-oss-20b      # Helper LLM (cheap/fast tier)
GROQ_SMART_MODEL=openai/gpt-oss-120b  # Smart LLM (grading — more capable tier)
```

`GROQ_API_KEY` is the only one you must set yourself; the rest have working defaults. If it's missing, the app still starts — only Helper/Smart LLM calls fail, with a clear `500 GROQ_API_KEY missing` response rather than a crash.

## 4. Run migrations

```bash
alembic upgrade head
```

Creates the 5 tables (`sequence`, `stage`, `interview_session`, `stage_attempt`, `message`).

## 5. Seed the question bank (and the vector store)

```bash
python -m seed.seed_materials_joining
```

Loads the 5 real interview sequences (materials-joining/manufacturing domain, from `rawData/`) into `sequence`/`stage`, and indexes each sequence's background material into the Helper's vector store. It's idempotent — safe to run again; it skips sequences that already exist and prints the `sequence_id` values it created (or already has):

```text
added sequence 2: 'Shielding Gas Selection for a Robotic Welding Cell' (4 chunks indexed)
...
Seeded 5 new sequence(s). Use one of these sequence_id values with POST /sessions:
  2: Shielding Gas Selection for a Robotic Welding Cell
  ...
```

Note the vector store itself (Chroma, in-memory) isn't persisted between server restarts — it doesn't need to be, since `POST /sessions/{id}/helper` re-indexes a sequence's material on first use every time. Running the seed script is what gets the `sequence`/`stage` rows into Postgres and gives you `sequence_id` values to test with; re-priming the vector store on restart is automatic and requires no action from you.

## 6. Start the API

```bash
uvicorn main:app --reload --port 8000
```

Check it's up: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`.

## 7. Test the API

Using a `sequence_id` printed by the seed script (e.g. `2`):

```bash
# Create a session
curl -s -X POST http://127.0.0.1:8000/api/sessions \
  -H "Content-Type: application/json" -d '{"sequence_id": 2}'
# -> {"id": "<session_id>", ..., "current_stage": {"order_index": 1, "prompt_text": "...", ...}}

SID=<session_id from above>

# Ask the Helper for hints (only works before /ready)
curl -s -X POST http://127.0.0.1:8000/api/sessions/$SID/helper \
  -H "Content-Type: application/json" -d '{"question": "any high-level hints?"}'

# Lock the Helper and start answering
curl -s -X POST http://127.0.0.1:8000/api/sessions/$SID/ready

# Submit an answer -> Smart LLM returns either a follow-up or a final score
curl -s -X POST http://127.0.0.1:8000/api/sessions/$SID/answer \
  -H "Content-Type: application/json" -d '{"text": "your answer here"}'

# If status was "followup", respond to it (repeat until status is "scored")
curl -s -X POST http://127.0.0.1:8000/api/sessions/$SID/followup \
  -H "Content-Type: application/json" -d '{"response": "more detail"}'

# Move to the next stage (repeat the whole loop for stages 2-5)
curl -s -X POST http://127.0.0.1:8000/api/sessions/$SID/advance

# After stage 5's /advance, get the final result
curl -s http://127.0.0.1:8000/api/sessions/$SID/results
```

Or open **http://127.0.0.1:8000/docs** for interactive Swagger UI — every endpoint below is there with request/response schemas.

### API reference

| Method | Path | Notes |
|---|---|---|
| POST | `/api/sessions` | `{sequence_id, candidate_email?}` → creates a session + all 5 stage attempts |
| GET | `/api/sessions/{id}` | Full current state — safe to re-poll any time, including after a restart |
| POST | `/api/sessions/{id}/helper` | `{question}` → `{ai_response, raw_chunks, source_labels}`. **403 once `/ready` is called** |
| POST | `/api/sessions/{id}/ready` | Permanently locks the Helper for the current stage |
| POST | `/api/sessions/{id}/answer` | `{text}` → `{status: "followup"|"scored", question?, score?, rationale?}` |
| POST | `/api/sessions/{id}/followup` | `{response}` → same shape as `/answer`; capped at `MAX_FOLLOWUPS` (default 2) |
| POST | `/api/sessions/{id}/advance` | Moves to the next stage, or (after stage 5) finalizes the session |
| GET | `/api/sessions/{id}/results` | Available once the session is `completed`: per-axis scores, `overall_score`, `overall_feedback`, `ai_steering_score`/`ai_steering_rationale` |

## Running the automated test suite

Tests mock the LLM entirely (no API key or network calls needed) and run against a separate `aiinterviewer_test` database so they never touch your dev data:

```bash
docker exec aiinterviewer-postgres psql -U aiinterviewer -d aiinterviewer -c "CREATE DATABASE aiinterviewer_test;"  # once
pytest -q
```

These tests cover business rules (state transitions, the security boundary, bounded follow-ups, structured-output validation) — they're not a substitute for you exercising the real flow with a real Groq key per steps 1-7 above.

## Troubleshooting

- **A `POST /answer` or `/followup` call intermittently fails with a `500`**: Groq occasionally returns a transient `503` or `429` rate-limit error under high demand. This is upstream, not a bug — just retry the same call; nothing is written until scoring actually succeeds, so retrying is always safe (see `DESIGN.md`'s note on this in `interview/flow.py`).
- **`alembic upgrade head` fails to connect**: check Postgres is running (`docker ps`) and `DATABASE_URL` in `.env` matches how you started it.
- **Seed script says a sequence already exists but you want to reload it**: the seed script never deletes/overwrites — if you need to change seeded content, edit the row directly or drop the affected `sequence` row yourself (cascades to its `stage` rows) before re-running.
