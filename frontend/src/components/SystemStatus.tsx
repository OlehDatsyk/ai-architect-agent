import { type ReactNode, useEffect, useState } from "react";

import type { HealthState } from "../hooks/useHealth";
import { ApiError, verifyClaude } from "../services/api";
import type { ClaudeVerification } from "../types/api";
import type { BlenderStatus } from "../types/api";

type Tone = "ok" | "warn" | "error" | "pending";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  error: "bg-revision",
  pending: "bg-line",
};

const BLENDER_LABEL: Record<BlenderStatus, { text: string; tone: Tone; help?: string }> = {
  found: { text: "Executable found", tone: "ok" },
  not_configured: { text: "Not set up yet", tone: "pending", help: "Set BLENDER_EXECUTABLE in .env to build designs in Blender." },
  missing: { text: "Path not found", tone: "error", help: "BLENDER_EXECUTABLE does not point to a Blender executable." },
};

function StatusRow({ label, value, tone, help, action }: { label: string; value: string; tone: Tone; help?: string; action?: ReactNode }) {
  return (
    <li className="flex gap-3 py-2.5">
      <span aria-hidden="true" className={`mt-1.5 size-2.5 shrink-0 ${TONE_CLASS[tone]}`} />
      <div className="min-w-0">
        <p className="text-[15px] font-medium">{label}</p>
        <p className="text-[13px] text-muted">{value}</p>
        {help && <p className="mt-0.5 text-[13px] leading-snug text-muted">{help}</p>}
        {action}
      </div>
    </li>
  );
}

export function SystemStatus({ state, onRetry }: { state: HealthState; onRetry: () => void }) {
  return (
    <section aria-labelledby="system-heading" className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between">
        <h2 id="system-heading" className="text-[17px] font-semibold">System</h2>
        <button
          type="button"
          onClick={onRetry}
          disabled={state.kind === "loading"}
          className="text-[13px] font-medium text-muted underline-offset-2 hover:text-ink hover:underline disabled:opacity-50"
        >
          Check again
        </button>
      </div>

      <ul className="divide-y divide-line" aria-live="polite" aria-busy={state.kind === "loading"}>
        {state.kind === "loading" && <StatusRow label="Backend API" value="Checking..." tone="pending" />}

        {state.kind === "error" && (
          <StatusRow
            label="Backend API"
            value="Unreachable"
            tone="error"
            help={`${state.message} Start it with: uvicorn app.main:app --reload`}
          />
        )}

        {state.kind === "ready" && (
          <>
            <StatusRow label="Backend API" value={`Connected, version ${state.data.version}`} tone="ok" />
            <StatusRow
              label="Claude API key"
              value={state.data.checks.anthropic.configured ? "Configured on the server" : "Not set"}
              tone={state.data.checks.anthropic.configured ? "ok" : "warn"}
              help={state.data.checks.anthropic.configured ? `Model: ${state.data.checks.anthropic.model}` : "Add ANTHROPIC_API_KEY to .env and restart the backend."}
            />
            {state.data.checks.anthropic.configured && <ClaudeRow initial={state.data.checks.anthropic.verification} />}
            <StatusRow label="Blender" {...blenderProps(state.data.checks.blender.status)} />
          </>
        )}
      </ul>
    </section>
  );
}

function blenderProps(status: BlenderStatus) {
  const { text, tone, help } = BLENDER_LABEL[status];
  return { value: text, tone, help };
}

const VERIFICATION_LABEL = {
  verified: { text: "Verified: requests and structured output accepted", tone: "ok" },
  failed: { text: "Failed", tone: "error" },
  not_checked: { text: "Not checked", tone: "pending" },
} as const;

/** Whether Anthropic actually accepts requests. Verifying sends two tiny requests (a fraction of a cent). */
function ClaudeRow({ initial }: { initial: ClaudeVerification }) {
  const [result, setResult] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setResult(initial), [initial]);

  const verify = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await verifyClaude(true));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The check could not be run.");
    } finally {
      setBusy(false);
    }
  };
  const label = VERIFICATION_LABEL[result.status];
  return (
    <StatusRow
      label="Claude API"
      value={busy ? "Checking..." : label.text}
      tone={busy ? "pending" : label.tone}
      help={error ?? (result.status === "failed" ? result.message ?? undefined : undefined)}
      action={
        <button type="button" onClick={() => void verify()} disabled={busy}
          className="mt-1 text-[13px] font-medium underline-offset-2 hover:underline disabled:opacity-50">
          {result.status === "not_checked" ? "Verify" : "Verify again"}
        </button>
      }
    />
  );
}
