import { useEffect, useRef, useState } from "react";
import { CandidateApp } from "./CandidateApp";
import { DevFlow } from "./DevFlow";
import { RecruiterApp } from "./RecruiterApp";
import { Mark, Page } from "./ui";

function RoleCard({ tone, eyebrow, title, description, cta, onClick }) {
  const toneClasses = tone === "red" ? "hover:border-red" : "hover:border-blue";
  const ctaTone = tone === "red" ? "text-red" : "text-blue";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`button-brutal group flex flex-col items-start gap-4 border-2 border-ink bg-cream-light p-6 text-left ${toneClasses}`}
    >
      <span className="font-mono text-xs uppercase tracking-widest text-ink-light">{eyebrow}</span>
      <h2 className="font-display text-xl uppercase tracking-tight text-ink">{title}</h2>
      <p className="text-sm leading-relaxed text-ink-light">{description}</p>
      <span className={`mt-2 flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide ${ctaTone}`}>
        {cta}
        <span className="transition-transform duration-200 group-hover:translate-x-1">&rarr;</span>
      </span>
    </button>
  );
}

function Landing({ onPick, onDev }) {
  return (
    <div className="bg-grid min-h-screen">
      <Page maxWidth="max-w-3xl">
        <div className="reveal flex items-center gap-2 pb-10">
          <Mark size="lg" />
          <span className="font-mono text-xs uppercase tracking-widest text-ink-light">
            idolHire
          </span>
        </div>

        <div className="reveal reveal-delay-1 space-y-4 pb-12">
          <h1 className="max-w-xl font-display text-4xl uppercase leading-tight tracking-tight text-ink sm:text-5xl">
            Practice the interview an AI can&rsquo;t talk you through.
          </h1>
          <p className="max-w-lg text-base leading-relaxed text-ink-light">
            Five stages, one fixed sequence: anchor, constraint, contradiction, AI trap, synthesis.
            Each one tests a different way of thinking under pressure.
          </p>
        </div>

        <div className="reveal reveal-delay-2 grid gap-5 sm:grid-cols-2">
          <RoleCard
            tone="red"
            eyebrow="Recruiter"
            title="Run an assessment"
            description="Pick a question sequence, set a time limit, and share a link. Review scores as candidates finish."
            cta="Continue as recruiter"
            onClick={() => onPick("recruiter")}
          />
          <RoleCard
            tone="blue"
            eyebrow="Candidate"
            title="Take an assessment"
            description="Join with the token your recruiter sent you, then work through the interview against the clock."
            cta="Continue as candidate"
            onClick={() => onPick("candidate")}
          />
        </div>

        {/* <div className="reveal reveal-delay-2 mt-12 border-t-2 border-ink pt-6">
          <button
            type="button"
            onClick={onDev}
            className="text-xs text-ink-light transition-colors hover:text-red"
          >
            Dev: start a session directly by sequence ID &rarr;
          </button>
        </div> */}
      </Page>
    </div>
  );
}

// The screen lives in browser history so the browser's back/forward buttons work.
// While a timed interview is running, back is swallowed: leaving would unmount
// the interview and lose the candidate's place in it.
function App() {
  const [screen, setScreen] = useState(() => window.history.state?.screen ?? "landing");
  const screenRef = useRef(screen);
  const interviewLocked = useRef(false);

  useEffect(() => {
    window.history.replaceState({ screen: screenRef.current }, "");
    function onPopState(e) {
      if (interviewLocked.current) {
        window.history.pushState({ screen: screenRef.current }, "");
        return;
      }
      const next = e.state?.screen ?? "landing";
      screenRef.current = next;
      setScreen(next);
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function go(next) {
    if (next === screenRef.current) return;
    window.history.pushState({ screen: next }, "");
    screenRef.current = next;
    setScreen(next);
  }
  const goHome = () => go("landing");
  const setLocked = (locked) => {
    interviewLocked.current = locked;
  };

  if (screen === "recruiter") return <RecruiterApp onHome={goHome} />;
  if (screen === "candidate") return <CandidateApp onHome={goHome} onInterviewActive={setLocked} />;
  if (screen === "dev") return <DevFlow onHome={goHome} />;

  return <Landing onPick={go} onDev={() => go("dev")} />;
}

export default App;
