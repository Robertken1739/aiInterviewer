import { useEffect, useState } from "react";
import {
  candidateLogin,
  candidateLogout,
  candidateSignup,
  joinAssessment,
} from "./api";
import { AuthForm } from "./AuthForm";
import { InterviewRunner } from "./InterviewRunner";
import { Button, Card, ErrorBanner, Field, Input, Page, TopBar } from "./ui";

export function CandidateApp({ onHome, onInterviewActive }) {
  const [auth, setAuth] = useState(null);
  const [session, setSession] = useState(null);
  const [shareToken, setShareToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function handleLogout() {
    if (auth) candidateLogout(auth.auth_token).catch(() => {});
    setAuth(null);
    setSession(null);
  }

  function handleJoin(e) {
    e.preventDefault();
    if (!shareToken.trim()) return;
    setError(null);
    setLoading(true);
    joinAssessment(auth.auth_token, shareToken.trim())
      .then(setSession)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  // Hide the home/wordmark link while a timed session is actively in progress
  // so a stray click can't strand the candidate without a way back in.
  const inActiveInterview = session && session.status !== "completed";

  // Also tells the app shell to ignore the browser's back button mid-interview.
  useEffect(() => {
    onInterviewActive?.(Boolean(inActiveInterview));
    return () => onInterviewActive?.(false);
  }, [inActiveInterview, onInterviewActive]);

  return (
    <Page maxWidth={session ? "max-w-4xl" : "max-w-3xl"}>
      <TopBar
        onHome={inActiveInterview ? undefined : onHome}
        subtitle="Candidate"
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
            roleLabel="Candidate account"
            signupFn={candidateSignup}
            loginFn={candidateLogin}
            onAuthenticated={setAuth}
          />
        )}

        {auth && !session && (
          <Card className="mx-auto max-w-sm space-y-4 p-6">
            <div className="space-y-1">
              <h2 className="font-display text-lg uppercase tracking-tight text-ink">Join an assessment</h2>
              <p className="text-sm text-ink-light">
                Enter the share token your recruiter sent you.
              </p>
            </div>
            <ErrorBanner>{error}</ErrorBanner>
            <form onSubmit={handleJoin} className="space-y-4">
              <Field label="Share token">
                <Input
                  className="font-mono"
                  required
                  value={shareToken}
                  onChange={(e) => setShareToken(e.target.value)}
                  placeholder="e.g. 8F2KQ1"
                />
              </Field>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Joining..." : "Join and begin"}
              </Button>
            </form>
          </Card>
        )}

        {auth && session && (
          <InterviewRunner
            key={session.id}
            initialSession={session}
            showEndTest
            revealScores={false}
            restartLabel="Done"
            onRestart={() => setSession(null)}
          />
        )}
      </div>
    </Page>
  );
}
