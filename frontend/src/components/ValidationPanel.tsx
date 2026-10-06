import type { ValidationIssue, ValidationReport } from "../types/design";

interface Props {
  /** The planned building's report (the authoritative one), plus Claude's interpretation report. */
  reports: ValidationReport[];
  /** Room and element names by ID, so issues can say which rooms they affect. */
  names: Record<string, string>;
}

const STATUS = {
  PASS: { text: "Passed every check", tone: "bg-ok" },
  WARNING: { text: "Passed, with points to review", tone: "bg-warn" },
  ERROR: { text: "Has problems that must be fixed", tone: "bg-revision" },
} as const;

/** Every validation issue and automatic fix, grouped by severity, naming the rooms affected. */
export function ValidationPanel({ reports, names }: Props) {
  const seen = new Set<string>();
  const issues: ValidationIssue[] = [];
  for (const issue of reports.flatMap((r) => r.issues)) {
    if (!seen.has(issue.message)) {
      seen.add(issue.message);
      issues.push(issue);
    }
  }
  const fixes = reports.flatMap((r) => r.fixes);
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");
  const status = errors.length ? "ERROR" : warnings.length ? "WARNING" : "PASS";

  const affected = (issue: ValidationIssue) =>
    [...new Set(issue.element_ids.map((id) => names[id]).filter(Boolean))].join(", ");

  const list = (items: ValidationIssue[], border: string) => (
    <ul className="mt-1.5 flex flex-col gap-1.5 text-[15px] leading-snug">
      {items.map((i) => (
        <li key={i.code + i.message} className={`border-l-2 ${border} pl-3`}>
          {i.message}
          {affected(i) && <span className="block text-[13px] text-muted">Affects: {affected(i)}</span>}
        </li>
      ))}
    </ul>
  );

  return (
    <section aria-labelledby="checks-title">
      <h3 id="checks-title" className="text-[17px] font-semibold">Design checks</h3>
      <p className="mt-1 flex items-center gap-2 text-[15px]">
        <span aria-hidden="true" className={`size-2.5 ${STATUS[status].tone}`} />
        {STATUS[status].text}
        <span className="text-[13px] text-muted">
          ({errors.length} {errors.length === 1 ? "error" : "errors"}, {warnings.length} {warnings.length === 1 ? "warning" : "warnings"})
        </span>
      </p>
      {errors.length > 0 && <><h4 className="mt-3 text-[13px] font-semibold uppercase tracking-wide text-revision">Errors</h4>{list(errors, "border-revision")}</>}
      {warnings.length > 0 && <><h4 className="mt-3 text-[13px] font-semibold text-muted">Points to review</h4>{list(warnings, "border-warn")}</>}
      {fixes.length > 0 && (
        <>
          <h4 className="mt-3 text-[13px] font-semibold text-muted">Corrected automatically</h4>
          <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-5 text-[13px] leading-snug text-muted">
            {fixes.map((f) => <li key={f.code + f.message}>{f.message}</li>)}
          </ul>
        </>
      )}
      <p className="mt-3 text-[13px] text-muted">Checks cover layout, access, openings, stairs, roof and wall clearances. They are not a building-regulations review.</p>
    </section>
  );
}
