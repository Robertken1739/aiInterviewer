import { useEffect, useState } from "react";
import {
  closeAssessment,
  createAssessment,
  getAssessment,
  getAssessmentSessions,
  getResults,
  listAssessments,
  listSequences,
  recruiterLogin,
  recruiterLogout,
  recruiterSignup,
} from "./api";
import { AuthForm } from "./AuthForm";
import {
  Button,
  Card,
  ConfirmButton,
  ErrorBanner,
  Field,
  HelperQuestions,
  Input,
  LoadingLine,
  Page,
  Pill,
  Select,
  TopBar,
} from "./ui";

function formatStageType(stageType) {
  return stageType ? stageType.replace(/_/g, " ") : "";
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function CopyToken({ token }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="inline-flex items-center gap-2 border-2 border-ink bg-cream-dark px-2.5 py-1 font-mono text-xs text-ink transition-colors hover:border-red"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(token);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // clipboard access denied -- token is still visible and selectable
        }
      }}
      title="Copy share token"
    >
      {token}
      <span className="text-ink-light">{copied ? "copied" : "copy"}</span>
    </button>
  );
}

function CreateAssessmentForm({ token, onCreated, onCancel }) {
  const [sequences, setSequences] = useState([]);
  const [sequenceId, setSequenceId] = useState("");
  const [duration, setDuration] = useState(45);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    listSequences(token)
      .then((seqs) => {
        setSequences(seqs);
        if (seqs.length > 0) setSequenceId(String(seqs[0].id));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [token]);

  function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    createAssessment(token, Number(sequenceId), Number(duration))
      .then(onCreated)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  return (
    <Card className="space-y-4 p-6">
      <h2 className="font-display text-lg uppercase tracking-tight text-ink">New assessment</h2>
      <ErrorBanner>{error}</ErrorBanner>
      {loading && sequences.length === 0 ? (
        <LoadingLine>Loading question sequences...</LoadingLine>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Question sequence">
            <Select value={sequenceId} onChange={(e) => setSequenceId(e.target.value)} required>
              {sequences.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Duration (minutes)">
            <Input
              type="number"
              min={1}
              required
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
            />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={loading || sequences.length === 0}>
              Create assessment
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function AssessmentCard({ assessment, onView }) {
  const isOpen = !assessment.closed_at;
  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-base uppercase tracking-tight text-ink">
            {assessment.sequence_title}
          </h3>
          <p className="mt-1 font-mono text-xs text-ink-light">{assessment.duration_minutes} min</p>
        </div>
        <Pill tone={isOpen ? "open" : "closed"}>{isOpen ? "Open" : "Closed"}</Pill>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <CopyToken token={assessment.share_token} />
        <span className="text-xs text-ink-light">created {formatDate(assessment.created_at)}</span>
      </div>
      <Button variant="secondary" onClick={() => onView(assessment.id)}>
        View results
      </Button>
    </Card>
  );
}

function statusTone(status) {
  return status === "completed" ? "done" : "progress";
}

// The candidate's own answer text alongside the score/rationale -- this is the
// actual evaluation surface for this product: recruiters read what the
// candidate wrote, not just a number, since scoring is never shown to the
// candidate live (see InterviewRunner's revealScores).
function CandidateDetail({ sessionId, onBack }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getResults(sessionId)
      .then((r) => {
        if (!cancelled) setResult(r);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return (
    <div className="space-y-5">
      <button type="button" onClick={onBack} className="text-sm text-ink-light hover:text-red">
        &larr; Back to candidates
      </button>

      <ErrorBanner>{error}</ErrorBanner>
      {loading && <LoadingLine />}

      {result && (
        <>
          <Card className="space-y-2 p-6">
            <h2 className="font-display text-xl uppercase tracking-tight text-ink">Candidate results</h2>
            <div className="font-mono text-sm text-ink-light">
              Overall score: <span className="text-ink">{result.overall_score ?? "—"} / 5</span>
            </div>
            {result.overall_feedback && (
              <p className="whitespace-pre-wrap text-sm text-ink">{result.overall_feedback}</p>
            )}
          </Card>

          <Card className="space-y-5 p-6">
            <h3 className="font-display text-sm uppercase tracking-tight text-ink">Per-stage responses</h3>
            {(result.stage_results || []).map((r) => (
              <div
                key={r.order_index}
                className="space-y-2 border-t-2 border-ink/15 pt-4 text-sm first:border-t-0 first:pt-0"
              >
                <div className="flex items-center justify-between gap-2 text-ink-light">
                  <span>
                    Stage {r.order_index} &middot; {formatStageType(r.stage_type)} &middot; {r.axis}
                  </span>
                  <span className="font-mono text-ink">{r.score ?? "—"} / 5</span>
                </div>
                {r.answer_text && (
                  <p className="whitespace-pre-wrap border-2 border-ink bg-cream-dark p-3 text-ink">
                    {r.answer_text}
                  </p>
                )}
                <HelperQuestions questions={r.helper_questions} />
                {r.score_rationale && (
                  <p className="whitespace-pre-wrap text-ink-light">{r.score_rationale}</p>
                )}
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
        </>
      )}
    </div>
  );
}

function AssessmentResults({ token, assessmentId, onBack }) {
  const [assessment, setAssessment] = useState(null);
  const [sessions, setSessions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [viewingSessionId, setViewingSessionId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getAssessment(token, assessmentId), getAssessmentSessions(token, assessmentId)])
      .then(([a, s]) => {
        if (cancelled) return;
        setAssessment(a);
        setSessions(s);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, assessmentId]);

  function handleClose() {
    setError(null);
    closeAssessment(token, assessmentId)
      .then(setAssessment)
      .catch((err) => setError(err.message));
  }

  if (viewingSessionId) {
    return <CandidateDetail sessionId={viewingSessionId} onBack={() => setViewingSessionId(null)} />;
  }

  return (
    <div className="space-y-5">
      <button type="button" onClick={onBack} className="text-sm text-ink-light hover:text-red">
        &larr; Back to assessments
      </button>

      <ErrorBanner>{error}</ErrorBanner>

      {loading && !assessment ? (
        <LoadingLine />
      ) : (
        assessment && (
          <Card className="space-y-3 p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-xl uppercase tracking-tight text-ink">
                  {assessment.sequence_title}
                </h2>
                <p className="mt-1 text-sm text-ink-light">
                  {assessment.duration_minutes} min &middot; {sessions ? sessions.length : "—"}{" "}
                  candidate{sessions?.length === 1 ? "" : "s"}
                </p>
              </div>
              <Pill tone={assessment.closed_at ? "closed" : "open"}>
                {assessment.closed_at ? "Closed" : "Open"}
              </Pill>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <CopyToken token={assessment.share_token} />
              {!assessment.closed_at && (
                <ConfirmButton onConfirm={handleClose} confirmLabel="Close it">
                  Close assessment
                </ConfirmButton>
              )}
            </div>
          </Card>
        )
      )}

      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead>
            <tr className="border-b-2 border-ink text-xs uppercase tracking-wide text-ink-light">
              <th className="px-4 py-3 font-semibold">Candidate</th>
              <th className="px-4 py-3 font-semibold">Status</th>
              <th className="px-4 py-3 font-semibold">Overall</th>
              <th className="px-4 py-3 font-semibold">AI-steering</th>
              <th className="px-4 py-3 font-semibold">Started</th>
              <th className="px-4 py-3 font-semibold">Completed</th>
              <th className="px-4 py-3 font-semibold"></th>
            </tr>
          </thead>
          <tbody>
            {sessions && sessions.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-ink-light">
                  No candidates have joined yet.
                </td>
              </tr>
            )}
            {sessions?.map((s) => (
              <tr key={s.session_id} className="border-b-2 border-ink/15 last:border-0">
                <td className="px-4 py-3 text-ink">{s.candidate_email}</td>
                <td className="px-4 py-3">
                  <Pill tone={statusTone(s.status)}>
                    {s.status === "completed" ? "Completed" : "In progress"}
                  </Pill>
                </td>
                <td className="px-4 py-3 font-mono text-ink">
                  {s.overall_score != null ? `${s.overall_score} / 5` : "—"}
                </td>
                <td className="px-4 py-3 font-mono text-ink">
                  {s.ai_steering_score != null ? `${s.ai_steering_score} / 5` : "—"}
                </td>
                <td className="px-4 py-3 text-ink-light">{formatDate(s.started_at)}</td>
                <td className="px-4 py-3 text-ink-light">{formatDate(s.completed_at)}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => setViewingSessionId(s.session_id)}
                    className="text-xs font-bold uppercase tracking-wide text-red hover:underline"
                  >
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

export function RecruiterApp({ onHome }) {
  const [auth, setAuth] = useState(null);
  const [assessments, setAssessments] = useState(null);
  const [view, setView] = useState("dashboard"); // dashboard | create | results
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!auth) return;
    listAssessments(auth.auth_token)
      .then(setAssessments)
      .catch((err) => setError(err.message));
  }, [auth]);

  function handleLogout() {
    if (auth) recruiterLogout(auth.auth_token).catch(() => {});
    setAuth(null);
    setAssessments(null);
    setView("dashboard");
  }

  function handleCreated(assessment) {
    setAssessments((list) => [assessment, ...(list || [])]);
    setView("dashboard");
  }

  return (
    <Page maxWidth="max-w-4xl">
      <TopBar
        onHome={onHome}
        subtitle="Recruiter"
        right={
          auth && (
            <>
              <span className="hidden text-sm text-ink-light sm:inline">{auth.email}</span>
              <Button variant="ghost" onClick={handleLogout}>
                Log out
              </Button>
            </>
          )
        }
      />

      <div className="mt-8 space-y-6">
        {!auth && (
          <AuthForm
            roleLabel="Recruiter account"
            signupFn={recruiterSignup}
            loginFn={recruiterLogin}
            onAuthenticated={setAuth}
          />
        )}

        {auth && view === "dashboard" && (
          <div className="space-y-5">
            <div className="flex items-center justify-between">
              <h1 className="font-display text-2xl uppercase tracking-tight text-ink">Assessments</h1>
              <Button onClick={() => setView("create")}>New assessment</Button>
            </div>

            <ErrorBanner>{error}</ErrorBanner>

            {assessments == null && <LoadingLine />}
            {assessments && assessments.length === 0 && (
              <Card className="p-8 text-center text-sm text-ink-light">
                No assessments yet. Create one to get a shareable link for candidates.
              </Card>
            )}
            {assessments && assessments.length > 0 && (
              <div className="grid gap-4 sm:grid-cols-2">
                {assessments.map((a) => (
                  <AssessmentCard
                    key={a.id}
                    assessment={a}
                    onView={(id) => {
                      setSelectedId(id);
                      setView("results");
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {auth && view === "create" && (
          <CreateAssessmentForm
            token={auth.auth_token}
            onCreated={handleCreated}
            onCancel={() => setView("dashboard")}
          />
        )}

        {auth && view === "results" && selectedId != null && (
          <AssessmentResults
            token={auth.auth_token}
            assessmentId={selectedId}
            onBack={() => setView("dashboard")}
          />
        )}
      </div>
    </Page>
  );
}
