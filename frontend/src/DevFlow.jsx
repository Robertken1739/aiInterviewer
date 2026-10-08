import { useState } from "react";
import { createSession, getSession } from "./api";
import { InterviewRunner } from "./InterviewRunner";
import { Button, Card, ErrorBanner, Field, Input, LoadingLine, Page, TopBar } from "./ui";

// The original direct-by-sequence-id start/resume screen, kept as a secondary
// entry point for quick testing without going through recruiter/candidate
// accounts. No timer, no End Test -- those are OA-specific.
export function DevFlow({ onHome }) {
  const [session, setSession] = useState(null);
  const [sequenceIdInput, setSequenceIdInput] = useState("");
  const [candidateEmail, setCandidateEmail] = useState("");
  const [resumeIdInput, setResumeIdInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

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

  function handleCreate(e) {
    e.preventDefault();
    runAction(async () => setSession(await createSession(Number(sequenceIdInput), candidateEmail)));
  }

  function handleResume(e) {
    e.preventDefault();
    runAction(async () => setSession(await getSession(resumeIdInput.trim())));
  }

  return (
    <Page>
      <TopBar onHome={onHome} subtitle="Dev entry" />
      <div className="mt-8 space-y-6">
        {!session && (
          <>
            <div className="space-y-1">
              <h1 className="font-display text-2xl uppercase tracking-tight text-ink">Start by sequence ID</h1>
              <p className="text-sm text-ink-light">
                Skips accounts and OAs entirely -- for quickly exercising the interview flow.
              </p>
            </div>

            <ErrorBanner>{error}</ErrorBanner>
            {loading && <LoadingLine />}

            <Card className="space-y-4 p-6">
              <h2 className="font-display text-sm uppercase tracking-tight text-ink">Start a new session</h2>
              <form onSubmit={handleCreate} className="space-y-4">
                <Field label="Sequence ID" hint="See backend seed script output.">
                  <Input
                    type="number"
                    required
                    value={sequenceIdInput}
                    onChange={(e) => setSequenceIdInput(e.target.value)}
                  />
                </Field>
                <Field label="Candidate email (optional)">
                  <Input
                    type="email"
                    value={candidateEmail}
                    onChange={(e) => setCandidateEmail(e.target.value)}
                  />
                </Field>
                <Button type="submit">Create session</Button>
              </form>
            </Card>

            <Card className="space-y-4 p-6">
              <h2 className="font-display text-sm uppercase tracking-tight text-ink">Resume an existing session</h2>
              <form onSubmit={handleResume} className="space-y-4">
                <Field label="Session ID">
                  <Input
                    type="text"
                    required
                    value={resumeIdInput}
                    onChange={(e) => setResumeIdInput(e.target.value)}
                  />
                </Field>
                <Button variant="secondary" type="submit">
                  Resume
                </Button>
              </form>
            </Card>
          </>
        )}

        {session && (
          <InterviewRunner
            key={session.id}
            initialSession={session}
            revealScores
            restartLabel="Start a new session"
            onRestart={() => setSession(null)}
          />
        )}
      </div>
    </Page>
  );
}
