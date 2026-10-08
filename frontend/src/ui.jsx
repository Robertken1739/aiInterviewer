import { useState } from "react";

// Shared design-system primitives. Kept intentionally small -- plain components,
// no variant-management library, no CVA/clsx. Tailwind v4 tokens are registered
// in index.css (@theme): cream / cream-light / cream-dark / ink / ink-light /
// red / red-dark / blue / blue-dark / yellow / yellow-dark, plus font-display
// (Archivo Black) / font-body (Space Grotesk) / font-mono.

export function Mark({ size = "sm" }) {
  const dims = size === "lg" ? "h-3.5 w-3.5" : "h-2.5 w-2.5";
  return <span className={`inline-block shrink-0 border-2 border-ink bg-red ${dims}`} />;
}

export function Wordmark({ onClick, subtitle }) {
  const content = (
    <span className="flex items-center gap-2 font-display text-base uppercase tracking-tight text-ink">
      <Mark />
      idolHire
    </span>
  );
  return (
    <div className="flex items-baseline gap-3">
      {onClick ? (
        <button type="button" onClick={onClick} className="transition-opacity hover:opacity-70">
          {content}
        </button>
      ) : (
        content
      )}
      {subtitle && (
        <span className="hidden font-mono text-xs uppercase tracking-widest text-ink-light sm:inline">
          {subtitle}
        </span>
      )}
    </div>
  );
}

export function TopBar({ onHome, subtitle, right }) {
  return (
    <div className="flex items-center justify-between border-b-2 border-ink px-4 py-4 sm:px-8">
      <Wordmark onClick={onHome} subtitle={subtitle} />
      <div className="flex items-center gap-3">{right}</div>
    </div>
  );
}

// The questions a candidate typed to the Helper on one stage (recruiter view).
export function HelperQuestions({ questions }) {
  if (!questions?.length) return null;
  return (
    <div className="space-y-1">
      <div className="font-mono text-[11px] uppercase tracking-wide text-ink-light">
        Asked the Helper
      </div>
      <ul className="space-y-1">
        {questions.map((q, i) => (
          <li key={i} className="whitespace-pre-wrap border-l-2 border-blue pl-3 text-ink">
            {q}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Page({ children, maxWidth = "max-w-3xl" }) {
  return (
    <div className="min-h-screen">
      <div className={`mx-auto w-full ${maxWidth} px-4 py-8 sm:px-8`}>{children}</div>
    </div>
  );
}

const cardTones = {
  default: "border-ink bg-cream-light",
  signal: "border-blue bg-blue/5",
};

export function Card({ className = "", tone = "default", children, ...props }) {
  return (
    <div className={`border-2 shadow-hard ${cardTones[tone]} ${className}`} {...props}>
      {children}
    </div>
  );
}

// Variant names kept identical to the previous theme so every call site
// across the app keeps working unchanged: primary / signal / secondary /
// danger / ghost. "signal" (candidate-side actions) now uses the blue accent
// instead of a teal one; "danger" is an outline that fills red on hover so it
// reads distinctly from the solid-red "primary".
const buttonVariants = {
  primary: "border-2 border-ink bg-red text-cream hover:bg-ink",
  signal: "border-2 border-ink bg-blue text-cream hover:bg-ink",
  secondary: "border-2 border-ink bg-transparent text-ink hover:bg-ink hover:text-cream",
  danger: "border-2 border-red bg-transparent text-red hover:bg-red hover:text-cream",
  ghost: "border-2 border-transparent bg-transparent text-ink-light hover:text-ink",
};

export function Button({ variant = "primary", className = "", ...props }) {
  const brutal = variant !== "ghost";
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 px-5 py-2.5 text-sm font-bold uppercase tracking-wide disabled:cursor-not-allowed disabled:opacity-40 ${
        brutal ? "button-brutal" : "transition-colors duration-150"
      } ${buttonVariants[variant]} ${className}`}
      {...props}
    />
  );
}

export function Field({ label, hint, children }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-semibold uppercase tracking-wide text-ink-light">{label}</span>
      {children}
      {hint && <span className="block text-xs text-ink-light/80">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full border-2 border-ink bg-cream-light px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-ink-light/50 focus:border-blue focus:ring-2 focus:ring-blue/30";

export function Input(props) {
  return <input className={inputClass} {...props} />;
}

export function Textarea(props) {
  return <textarea className={inputClass} {...props} />;
}

export function Select(props) {
  return <select className={inputClass} {...props} />;
}

const pillTones = {
  neutral: "border-ink/30 bg-cream-dark text-ink-light",
  open: "border-blue bg-blue/10 text-blue-dark",
  closed: "border-ink/30 bg-cream-dark text-ink-light",
  progress: "border-yellow-dark bg-yellow/20 text-ink",
  done: "border-blue bg-blue/10 text-blue-dark",
  danger: "border-red bg-red/10 text-red-dark",
};

export function Pill({ tone = "neutral", children }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 border-2 px-2.5 py-1 text-xs font-bold uppercase tracking-wide ${pillTones[tone]}`}
    >
      {children}
    </span>
  );
}

export function ErrorBanner({ children }) {
  if (!children) return null;
  return (
    <div className="border-2 border-red bg-red/10 px-4 py-3 text-sm text-red-dark">{children}</div>
  );
}

export function LoadingLine({ children = "Working..." }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-light">
      <span className="h-1.5 w-1.5 animate-pulse bg-red" />
      {children}
    </div>
  );
}

// Two-step inline confirm, used instead of window.confirm() / a modal component
// so destructive actions stay lightweight and match the rest of the design system.
export function ConfirmButton({ onConfirm, children, confirmLabel = "Really?", variant = "danger" }) {
  const [armed, setArmed] = useState(false);

  if (armed) {
    return (
      <span className="inline-flex items-center gap-2">
        <Button
          type="button"
          variant="danger"
          onClick={() => {
            setArmed(false);
            onConfirm();
          }}
        >
          {confirmLabel}
        </Button>
        <Button type="button" variant="ghost" onClick={() => setArmed(false)}>
          Cancel
        </Button>
      </span>
    );
  }

  return (
    <Button type="button" variant={variant} onClick={() => setArmed(true)}>
      {children}
    </Button>
  );
}
