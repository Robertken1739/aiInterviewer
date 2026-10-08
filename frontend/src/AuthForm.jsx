import { useState } from "react";
import { Button, Card, ErrorBanner, Field, Input } from "./ui";

// Cheap client-side check for fast feedback; the backend re-validates (and also
// catches misspelled provider domains like gmeel.com).
const EMAIL_RE = /^[^\s@]+@([a-z0-9-]+\.)+[a-z]{2,}$/i;

// Shared signup/login form for both roles. Signup returns auth_token: null per
// the API contract, so after a successful signup we drop the candidate/recruiter
// into the login form (prefilled) rather than pretending we're authenticated.
export function AuthForm({ roleLabel, signupFn, loginFn, onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (mode === "signup" && !EMAIL_RE.test(email.trim())) {
      setError("Enter a valid email address, like name@example.com");
      return;
    }
    setLoading(true);
    try {
      if (mode === "signup") {
        await signupFn(email, password);
        setNotice("Account created. Log in below to continue.");
        setMode("login");
        setPassword("");
      } else {
        const auth = await loginFn(email, password);
        onAuthenticated(auth);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="mx-auto max-w-sm space-y-5 p-6">
      <div className="space-y-1">
        <h2 className="font-display text-lg uppercase tracking-tight text-ink">
          {mode === "login" ? "Log in" : "Create your account"}
        </h2>
        <p className="text-sm text-ink-light">{roleLabel}</p>
      </div>

      {notice && (
        <div className="border-2 border-blue bg-blue/10 px-4 py-3 text-sm text-blue-dark">
          {notice}
        </div>
      )}
      <ErrorBanner>{error}</ErrorBanner>

      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Email">
          <Input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            required
            minLength={8}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Working..." : mode === "login" ? "Log in" : "Sign up"}
        </Button>
      </form>

      <button
        type="button"
        className="text-sm text-ink-light transition-colors hover:text-red"
        onClick={() => {
          setError(null);
          setNotice(null);
          setMode((m) => (m === "login" ? "signup" : "login"));
        }}
      >
        {mode === "login" ? "Need an account? Sign up" : "Already have an account? Log in"}
      </button>
    </Card>
  );
}
