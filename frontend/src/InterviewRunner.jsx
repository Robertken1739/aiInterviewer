import { useEffect, useRef, useState } from "react";
import {
  advanceSession,
  askHelper,
  endSession,
  getResults,
  markReady,
  submitAnswer,
  submitFollowup,
} from "./api";
import { Button, Card, ConfirmButton, ErrorBanner, HelperQuestions, LoadingLine, Pill } from "./ui";

// Positions only, no stage names: naming the current stage ("AI Trap") would
// tell the candidate the claim in front of them is flawed, which is exactly
// what that stage tests.
const STAGE_SEQUENCE = [
  { type: "anchor" },
  { type: "constraint" },
  { type: "contradiction" },
  { type: "ai_trap" },
  { type: "synthesis" },
];

function formatStageType(stageType) {
  return stageType ? stageType.replace(/_/g, " ") : "";
}

function StageRail({ currentOrderIndex }) {
  return (
    <div className="flex items-center gap-1 sm:gap-2">
      {STAGE_SEQUENCE.map((s, i) => {
        const position = i + 1;
        const isDone = position < currentOrderIndex;
        const isActive = position === currentOrderIndex;
        return (
          <div key={s.type} className="flex flex-1 items-center gap-1 sm:gap-2">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={
                  "flex h-6 w-6 items-center justify-center rounded-full border-2 font-mono text-[11px] " +
                  (isDone
                    ? "border-blue bg-blue/15 text-blue-dark"
                    : isActive
                    ? "border-red bg-red/15 text-red"
                    : "border-ink/25 text-ink-light")
                }
              >
                {isDone ? "✓" : position}
              </div>
            </div>
            {position < STAGE_SEQUENCE.length && (
              <div className={`h-0.5 flex-1 ${isDone ? "bg-blue/40" : "bg-ink/15"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function formatDuration(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function useCountdown(deadlineAt, onExpire) {
  const [remainingMs, setRemainingMs] = useState(() =>
    deadlineAt ? Date.parse(deadlineAt) - Date.now() : null
  );
  const expiredRef = useRef(false);
  const onExpireRef = useRef(onExpire);

  useEffect(() => {
    onExpireRef.current = onExpire;
  });

  useEffect(() => {
    expiredRef.current = false;
    if (!deadlineAt) return undefined;
    const tick = () => {
      const ms = Date.parse(deadlineAt) - Date.now();
      setRemainingMs(ms);
      if (ms <= 0 && !expiredRef.current) {
        expiredRef.current = true;
        onExpireRef.current?.();
      }
    };
    // The initial value comes from useState's lazy initializer (computed during
    // render); only fire ticks from the timer callback so the effect body itself
    // never calls setState synchronously.
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [deadlineAt]);

  return deadlineAt ? remainingMs : null;
}

function Timer({ deadlineAt, onExpire }) {
  const remainingMs = useCountdown(deadlineAt, onExpire);
  if (deadlineAt == null || remainingMs == null) return null;
  const clamped = Math.max(0, remainingMs);
  const critical = clamped <= 60_000;
  const warn = clamped <= 5 * 60_000;
  const tone = critical ? "text-red" : warn ? "text-yellow-dark" : "text-blue-dark";
  return (
    <div
      className={`flex items-center gap-2 border-2 border-ink bg-cream-light px-3 py-1.5 font-mono text-sm tabular-nums ${tone} ${
        critical ? "animate-pulse" : ""
      }`}
      role="timer"
      aria-live="polite"
    >
      <span aria-hidden>&#9679;</span>
      <span>{formatDuration(clamped)}</span>
    </div>
  );
}

function StageScreen({
  session,
  helperQuestion,
  setHelperQuestion,
  helperLog,
  onAskHelper,
  onReady,
  answerText,
  setAnswerText,
  onSubmitAnswer,
  pendingFollowupQuestion,
  resumedMidStage,
  followupText,
  setFollowupText,
  onSubmitFollowup,
  helperCoolingDown,
}) {
  const stage = session.current_stage;

  return (
    <div className="space-y-5">
      <Card className="space-y-3 p-5">
        <div className="flex items-center justify-between">
          <Pill tone="progress">
            Stage {stage.order_index} of 5
          </Pill>
        </div>
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-ink">{stage.prompt_text}</p>
        {stage.trap_claim_text && (
          <div className="border-2 border-yellow-dark bg-yellow/15 px-4 py-3 text-sm text-ink">
            <div className="mb-1 font-mono text-[11px] uppercase tracking-wide text-yellow-dark">
              Copilot response
            </div>
            <p className="whitespace-pre-wrap">{stage.trap_claim_text}</p>
          </div>
        )}
      </Card>

      {!stage.helper_locked && (
        <Card className="space-y-3 p-5">
          <h3 className="font-display text-sm uppercase tracking-tight text-ink">Ask the Helper for hints</h3>
          {helperLog.length > 0 && (
            <div className="space-y-3 border-b-2 border-ink/15 pb-3">
              {helperLog.map((entry, i) => (
                <div key={i} className="space-y-1 text-sm">
                  <div className="text-ink-light">You: {entry.question}</div>
                  <div className="whitespace-pre-wrap text-ink">Helper: {entry.answer}</div>
                </div>
              ))}
            </div>
          )}
          <form onSubmit={onAskHelper} className="flex gap-2">
            <input
              className="flex-1 border-2 border-ink bg-cream-light px-3 py-2 text-sm text-ink outline-none focus:border-blue focus:ring-2 focus:ring-blue/30"
              value={helperQuestion}
              onChange={(e) => setHelperQuestion(e.target.value)}
              placeholder="Ask a question..."
            />
            <Button variant="secondary" type="submit" disabled={helperCoolingDown}>
              {helperCoolingDown ? "Wait..." : "Ask"}
            </Button>
          </form>
          <p className="text-xs text-ink-light">
            Once you're ready to answer, the Helper locks for the rest of this stage.
          </p>
          <Button onClick={onReady}>I'm ready to answer</Button>
        </Card>
      )}

      {stage.helper_locked && !pendingFollowupQuestion && !resumedMidStage && (
        <Card className="space-y-3 p-5">
          <form onSubmit={onSubmitAnswer} className="space-y-3">
            <h3 className="font-display text-sm uppercase tracking-tight text-ink">Your answer</h3>
            <textarea
              className="w-full border-2 border-ink bg-cream-light px-3 py-2 text-sm text-ink outline-none focus:border-blue focus:ring-2 focus:ring-blue/30"
              rows={6}
              required
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
            />
            <Button type="submit">Submit answer</Button>
          </form>
        </Card>
      )}

      {stage.helper_locked && (pendingFollowupQuestion || resumedMidStage) && (
        <Card className="space-y-3 p-5">
          <form onSubmit={onSubmitFollowup} className="space-y-3">
            <h3 className="font-display text-sm uppercase tracking-tight text-ink">Follow-up question</h3>
            {pendingFollowupQuestion ? (
              <p className="whitespace-pre-wrap text-ink">{pendingFollowupQuestion}</p>
            ) : (
              <p className="text-sm text-ink-light">
                This stage has a pending follow-up from before you resumed (its exact text isn't
                stored client-side) -- respond below to continue.
              </p>
            )}
            <textarea
              className="w-full border-2 border-ink bg-cream-light px-3 py-2 text-sm text-ink outline-none focus:border-blue focus:ring-2 focus:ring-blue/30"
              rows={4}
              required
              value={followupText}
              onChange={(e) => setFollowupText(e.target.value)}
            />
            <Button type="submit">Submit response</Button>
          </form>
        </Card>
      )}
    </div>
  );
}

function ResultsScreen({ result, endedEarly, onRestart, restartLabel }) {
  return (
    <div className="space-y-5">
      <Card className="space-y-2 p-6">
        <h2 className="font-display text-xl uppercase tracking-tight text-ink">Final results</h2>
        {endedEarly && (
          <Pill tone="danger">Ended early -- not every stage may have been scored</Pill>
        )}
        <div className="font-mono text-sm text-ink-light">
          Overall score:{" "}
          <span className="text-ink">{result.overall_score ?? "—"} / 5</span>
        </div>
        {result.overall_feedback && (
          <p className="whitespace-pre-wrap text-sm text-ink">{result.overall_feedback}</p>
        )}
      </Card>

      <Card className="space-y-4 p-6">
        <h3 className="font-display text-sm uppercase tracking-tight text-ink">Per-stage scores</h3>
        {(result.stage_results || []).map((r) => (
          <div
            key={r.order_index}
            className="space-y-1 border-t-2 border-ink/15 pt-3 text-sm first:border-t-0 first:pt-0"
          >
            <div className="text-ink-light">
              Stage {r.order_index} &middot; {formatStageType(r.stage_type)} &middot; {r.axis}
            </div>
            <div className="text-ink">Score: {r.score ?? "—"} / 5</div>
            <HelperQuestions questions={r.helper_questions} />
            {r.score_rationale && <p className="whitespace-pre-wrap text-ink">{r.score_rationale}</p>}
          </div>
        ))}
      </Card>

      <Card className="space-y-2 p-6">
        <h3 className="font-display text-sm uppercase tracking-tight text-ink">
          AI-Steering Efficiency: {result.ai_steering_score ?? "—"} / 5
        </h3>
        {result.ai_steering_rationale && (
          <p className="whitespace-pre-wrap text-sm text-ink">{result.ai_steering_rationale}</p>
        )}
      </Card>

      <Button variant="secondary" onClick={onRestart}>
        {restartLabel}
      </Button>
    </div>
  );
}

// Candidate-facing completion screen -- deliberately carries no score. Grading
// happens recruiter-side, after the fact, from the assessment's results table.
function SubmittedScreen({ endedEarly, onRestart, restartLabel }) {
  return (
    <Card className="space-y-4 p-8 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border-2 border-blue bg-blue/10 text-blue-dark">
        &#10003;
      </div>
      <div className="space-y-1">
        <h2 className="font-display text-xl uppercase tracking-tight text-ink">
          {endedEarly ? "Assessment ended" : "Assessment submitted"}
        </h2>
        <p className="text-sm text-ink-light">
          Your responses have been recorded. The recruiter will review your results.
        </p>
      </div>
      <Button variant="secondary" onClick={onRestart}>
        {restartLabel}
      </Button>
    </Card>
  );
}

// Owns the full lifecycle of a single interview session: helper Q&A, ready/lock,
// answer + follow-up submission, advancing stages, and a whole-session countdown
// with auto-submit-then-end on expiry and a manual "End Test" escape hatch.
//
// revealScores controls whether this instance ever shows a score/rationale to
// whoever is looking at it -- false for the real candidate flow (evaluation is
// recruiter-side only, decided after the fact), true only for the dev entry
// point where seeing live scoring behavior is the point. This never changes
// what the *backend* sends on submit -- the API already never includes
// score/rationale on /answer, /followup, or /advance (see EvaluationOut /
// AdvanceOut) -- it only controls whether this component fetches the full
// GET /results afterward to display them.
//
// Mount with key={session.id} from callers so a fresh session always gets a
// fresh instance instead of stale internal state.
export function InterviewRunner({
  initialSession,
  showEndTest = false,
  revealScores = false,
  restartLabel,
  onRestart,
}) {
  const [session, setSession] = useState(initialSession);
  // Lazy initializer, not an effect: if we're handed an already-completed
  // session (e.g. resuming) and scores aren't revealed, the completion screen
  // is knowable synchronously from initialSession alone.
  const [result, setResult] = useState(() =>
    initialSession.status === "completed" && !revealScores ? { completed: true } : null
  );
  const [endedEarly, setEndedEarly] = useState(false);

  const [helperQuestion, setHelperQuestion] = useState("");
  const [helperLog, setHelperLog] = useState([]);
  const [answerText, setAnswerText] = useState("");
  const [followupText, setFollowupText] = useState("");
  const [pendingFollowupQuestion, setPendingFollowupQuestion] = useState(null);
  // Mirrors the backend's helper_cooldown_seconds (server-enforced, this is
  // just proactive UX so a candidate doesn't hit the 429 by double-clicking).
  const [helperCoolingDown, setHelperCoolingDown] = useState(false);
  // Derived once from the session this instance was mounted with -- callers key
  // InterviewRunner by session.id, so initialSession never changes under us and
  // a lazy initializer (not an effect) is the right place for this.
  const [resumedMidStage, setResumedMidStage] = useState(
    () =>
      initialSession.status !== "completed" &&
      Boolean(initialSession.current_stage?.helper_locked) &&
      Boolean(initialSession.current_stage?.answer_text) &&
      initialSession.current_stage?.score == null
  );

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Runs once for this session instance: the non-revealing case is already
    // handled by result's lazy initializer above (no async work needed there);
    // this only covers fetching the full results when scores ARE revealed.
    if (initialSession.status === "completed" && revealScores) {
      runAction(async () => setResult(await getResults(initialSession.id)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function resetStageState() {
    setHelperQuestion("");
    setHelperLog([]);
    setAnswerText("");
    setFollowupText("");
    setPendingFollowupQuestion(null);
    setResumedMidStage(false);
    setHelperCoolingDown(false);
  }

  async function runAction(action) {
    setError(null);
    setLoading(true);
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleAskHelper(e) {
    e.preventDefault();
    if (!helperQuestion.trim() || helperCoolingDown) return;
    runAction(async () => {
      const reply = await askHelper(session.id, helperQuestion);
      setHelperLog((log) => [...log, { question: helperQuestion, answer: reply.ai_response }]);
      setHelperQuestion("");
      setHelperCoolingDown(true);
      setTimeout(() => setHelperCoolingDown(false), 5000);
    });
  }

  function handleReady() {
    runAction(async () => setSession(await markReady(session.id)));
  }

  // No score is ever shown here: the candidate moves straight to the next
  // stage once a stage is scored, rather than seeing a score-then-click gate.
  async function doAdvance() {
    const adv = await advanceSession(session.id);
    if (adv.status === "completed") {
      setSession((s) => ({ ...s, status: "completed", current_stage: null }));
      setResult(revealScores ? await getResults(session.id) : { completed: true });
    } else {
      resetStageState();
      setSession((s) => ({ ...s, current_stage: adv.current_stage }));
    }
  }

  function handleAdvance() {
    runAction(doAdvance);
  }

  async function applyEvaluation(evalResult) {
    if (evalResult.status === "followup") {
      setPendingFollowupQuestion(evalResult.question);
      return;
    }
    setPendingFollowupQuestion(null);
    await doAdvance();
  }

  function handleSubmitAnswer(e) {
    e.preventDefault();
    if (!answerText.trim()) return;
    runAction(async () => applyEvaluation(await submitAnswer(session.id, answerText)));
  }

  function handleSubmitFollowup(e) {
    e.preventDefault();
    if (!followupText.trim()) return;
    runAction(async () => {
      const evalResult = await submitFollowup(session.id, followupText);
      setFollowupText("");
      setResumedMidStage(false);
      await applyEvaluation(evalResult);
    });
  }

  async function finalizeEnded() {
    await endSession(session.id);
    setEndedEarly(true);
    setSession((s) => ({ ...s, status: "completed" }));
    setResult(revealScores ? await getResults(session.id) : { completed: true });
  }

  // Timer expiry: best-effort auto-submit whatever the candidate has open (if
  // anything), then close the session out. A failed auto-submit still ends the
  // session -- time is up either way.
  async function handleExpire() {
    if (result || !session || session.status === "completed") return;
    try {
      const stage = session.current_stage;
      if (stage && stage.helper_locked) {
        if (pendingFollowupQuestion || resumedMidStage) {
          if (followupText.trim()) await submitFollowup(session.id, followupText);
        } else if (answerText.trim()) {
          await submitAnswer(session.id, answerText);
        }
      }
    } catch {
      // best effort -- fall through to ending the session regardless
    }
    runAction(finalizeEnded);
  }

  function handleEndTest() {
    runAction(finalizeEnded);
  }

  if (result) {
    return (
      <div className="space-y-4">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        {revealScores ? (
          <ResultsScreen
            result={result}
            endedEarly={endedEarly}
            onRestart={onRestart}
            restartLabel={restartLabel}
          />
        ) : (
          <SubmittedScreen endedEarly={endedEarly} onRestart={onRestart} restartLabel={restartLabel} />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-[220px] flex-1">
          <StageRail currentOrderIndex={session.current_stage?.order_index ?? 6} />
        </div>
        <div className="flex items-center gap-2">
          <Timer deadlineAt={session.deadline_at} onExpire={handleExpire} />
          {showEndTest && (
            <ConfirmButton onConfirm={handleEndTest} confirmLabel="End test now">
              End Test
            </ConfirmButton>
          )}
        </div>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}
      {loading && <LoadingLine />}

      {session.current_stage ? (
        <StageScreen
          session={session}
          helperQuestion={helperQuestion}
          setHelperQuestion={setHelperQuestion}
          helperLog={helperLog}
          onAskHelper={handleAskHelper}
          onReady={handleReady}
          answerText={answerText}
          setAnswerText={setAnswerText}
          onSubmitAnswer={handleSubmitAnswer}
          pendingFollowupQuestion={pendingFollowupQuestion}
          resumedMidStage={resumedMidStage}
          followupText={followupText}
          setFollowupText={setFollowupText}
          onSubmitFollowup={handleSubmitFollowup}
          helperCoolingDown={helperCoolingDown}
        />
      ) : (
        <Card className="space-y-3 p-5">
          <p className="text-sm text-ink">All stages answered. Finalizing...</p>
          <Button onClick={handleAdvance}>Get final results</Button>
        </Card>
      )}
    </div>
  );
}
