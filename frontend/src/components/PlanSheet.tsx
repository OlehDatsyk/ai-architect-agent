import type { ValidationIssue } from "../types/design";

export type SheetState =
  | { kind: "empty" }
  | { kind: "loading"; onCancel: () => void }
  | { kind: "error"; message: string; issues: ValidationIssue[]; onRetry: () => void };

const STATUS_TEXT = { empty: "Awaiting brief", loading: "Interpreting", error: "Needs attention" } as const;

/** The centre drawing sheet before a design exists: empty, interpreting or failed. */
export function PlanSheet({ state = { kind: "empty" } }: { state?: SheetState }) {
  const titleBlock: ReadonlyArray<[string, string]> = [
    ["Project", "Untitled"],
    ["Drawing", "Ground floor plan"],
    ["Scale", "Not set"],
    ["Status", STATUS_TEXT[state.kind]],
  ];
  return (
    <section aria-label="Floor plan sheet" className="relative flex min-h-[28rem] flex-1 flex-col border border-ink/70 bg-surface p-3">
      <div className="plan-grid relative flex flex-1 items-center justify-center overflow-hidden border border-line">
        {/* Dimension strings along the top and left edges, as on a drawn plan. */}
        <svg aria-hidden="true" className="absolute inset-x-10 top-5 h-4 w-[calc(100%-5rem)] overflow-visible">
          <line x1="0" y1="8" x2="100%" y2="8" className="stroke-revision" strokeWidth="1" />
          <line x1="0" y1="2" x2="0" y2="14" className="stroke-revision" strokeWidth="1" />
          <line x1="100%" y1="2" x2="100%" y2="14" className="stroke-revision" strokeWidth="1" />
        </svg>
        <svg aria-hidden="true" className="absolute inset-y-10 left-5 h-[calc(100%-5rem)] w-4 overflow-visible">
          <line x1="8" y1="0" x2="8" y2="100%" className="stroke-revision" strokeWidth="1" />
          <line x1="2" y1="0" x2="14" y2="0" className="stroke-revision" strokeWidth="1" />
          <line x1="2" y1="100%" x2="14" y2="100%" className="stroke-revision" strokeWidth="1" />
        </svg>

        <div className="max-w-md bg-surface/90 px-6 py-5 text-center" role={state.kind === "error" ? "alert" : undefined} aria-live="polite">
          {state.kind === "empty" && (
            <>
              <h3 className="text-[17px] font-semibold">No design yet</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-muted">
                Describe a building in the brief. Once it has been interpreted, you can review it here before anything
                is built in Blender.
              </p>
            </>
          )}
          {state.kind === "loading" && (
            <>
              <h3 className="text-[17px] font-semibold">Interpreting your brief</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-muted">
                Claude is working out the rooms, sizes and layout. This can take up to a minute.
              </p>
              <button type="button" onClick={state.onCancel} className="mt-3 text-[15px] font-medium text-muted underline underline-offset-2 hover:text-ink">
                Cancel
              </button>
            </>
          )}
          {state.kind === "error" && (
            <>
              <h3 className="text-[17px] font-semibold">The brief could not be interpreted</h3>
              <p className="mt-2 text-[15px] leading-relaxed">{state.message}</p>
              {state.issues.length > 0 && (
                <ul className="mt-3 flex flex-col gap-1 text-left text-[13px] leading-snug text-muted">
                  {state.issues.slice(0, 6).map((issue) => (
                    <li key={issue.code + issue.message} className="border-l-2 border-revision pl-2">{issue.message}</li>
                  ))}
                </ul>
              )}
              <button type="button" onClick={state.onRetry} className="mt-4 rounded-[3px] bg-ink px-3.5 py-2 text-[15px] font-medium text-surface hover:bg-ink/85">
                Try again
              </button>
            </>
          )}
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-2 border border-ink/70 text-[13px] sm:absolute sm:right-6 sm:bottom-6 sm:mt-0 sm:w-72 sm:bg-surface">
        {titleBlock.map(([term, value], i) => (
          <div key={term} className={`px-2.5 py-1.5 ${i % 2 === 0 ? "border-r border-ink/70" : ""} ${i < 2 ? "border-b border-ink/70" : ""}`}>
            <dt className="text-muted">{term}</dt>
            <dd className="font-medium">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
