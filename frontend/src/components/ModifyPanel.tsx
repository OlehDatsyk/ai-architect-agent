import { useId, useState } from "react";

import type { ModificationRecord } from "../types/design";

interface Props {
  history: ModificationRecord[];
  busy: boolean;
  error: string | null;
  unavailableReason: string | null;
  onModify: (request: string) => Promise<boolean>;
}

/** Plain-English changes to the current design, and a record of what each one changed. */
export function ModifyPanel({ history, busy, error, unavailableReason, onModify }: Props) {
  const [request, setRequest] = useState("");
  const id = useId();
  const latest = history[history.length - 1];
  const canApply = !busy && request.trim().length >= 3 && unavailableReason === null;

  return (
    <section aria-labelledby={`${id}-title`} className="flex flex-col gap-3 border-b border-ink/70 px-6 py-5">
      <h3 id={`${id}-title`} className="text-[17px] font-semibold">Change this design</h3>
      <form className="flex flex-col gap-2 sm:flex-row" onSubmit={async (e) => {
        e.preventDefault();
        if (canApply && (await onModify(request.trim()))) setRequest("");
      }}>
        <label htmlFor={`${id}-input`} className="sr-only">Describe a change</label>
        <input id={`${id}-input`} value={request} onChange={(e) => setRequest(e.target.value)} maxLength={1000} readOnly={busy}
          placeholder="For example: make the living room 1 metre wider, or change the roof to a hip roof"
          className="flex-1 rounded-[3px] border border-line bg-surface px-3 py-2 text-[15px] focus:border-ink focus:outline-none" />
        <button type="submit" disabled={!canApply}
          className="rounded-[3px] bg-ink px-3.5 py-2 text-[15px] font-medium text-surface hover:bg-ink/85 disabled:cursor-not-allowed disabled:bg-ink/35">
          {busy ? "Applying..." : "Apply change"}
        </button>
      </form>
      <div aria-live="polite" className="text-[13px]">
        {unavailableReason && <p className="text-muted">{unavailableReason}</p>}
        {error && <p role="alert" className="border-l-2 border-revision pl-2 text-[15px]">{error}</p>}
      </div>

      {latest && (
        <div>
          <p className="text-[15px] font-medium">What changed: {latest.summary}</p>
          <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-5 text-[15px] leading-snug">
            {latest.changes.length === 0 ? <li>No visible change.</li> : latest.changes.map((c) => <li key={c}>{c}</li>)}
          </ul>
          {latest.assumptions.length > 0 && (
            <p className="mt-1.5 text-[13px] text-muted">Assumed: {latest.assumptions.join(" ")}</p>
          )}
        </div>
      )}
      {history.length > 1 && (
        <details className="text-[13px]">
          <summary className="cursor-pointer text-muted">All changes ({history.length})</summary>
          <ol className="mt-1 flex list-decimal flex-col gap-1 pl-5">
            {history.map((h, i) => <li key={i}>{h.request}</li>)}
          </ol>
        </details>
      )}
    </section>
  );
}
