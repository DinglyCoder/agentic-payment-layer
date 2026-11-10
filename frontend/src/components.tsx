import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";

export function CopyButton({
  value,
  label = "Copy",
  showLabel = false,
}: {
  value: string;
  label?: string;
  showLabel?: boolean;
}) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");

  useEffect(() => {
    if (state === "idle") return;
    const timer = window.setTimeout(() => setState("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [state]);

  const feedback =
    state === "copied"
      ? "Copied"
      : state === "error"
        ? "Copy unavailable"
        : label;
  return (
    <span className="copy-control">
      <button
        className={`copy-button ${state === "copied" ? "copied" : ""}`}
        type="button"
        aria-label={feedback}
        title={feedback}
        onClick={async (event) => {
          event.stopPropagation();
          try {
            await navigator.clipboard.writeText(value);
            setState("copied");
          } catch {
            setState("error");
          }
        }}
      >
        {state === "copied" ? <Check size={14} /> : <Copy size={14} />}
        {showLabel && feedback}
      </button>
      <span className="sr-only" role="status">
        {state !== "idle" ? feedback : ""}
      </span>
    </span>
  );
}

export function BrandMark() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5 20V4h8a5 5 0 0 1 0 10H9"
        stroke="currentColor"
        strokeWidth="3"
      />
      <path
        d="M9 8h4a1 1 0 0 1 0 2H9v10"
        stroke="currentColor"
        strokeWidth="2"
      />
    </svg>
  );
}
