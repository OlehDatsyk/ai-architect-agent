interface Props {
  name: string;
  onNameChange: (name: string) => void;
  status: "new" | "saved" | "unsaved";
  saving: boolean;
  error: string | null;
  onSave: () => void;
}

const STATUS_TEXT = { new: "Not saved yet", saved: "Saved", unsaved: "Unsaved changes" } as const;

export function SaveBar({ name, onNameChange, status, saving, error, onSave }: Props) {
  return (
    <div className="mt-3 flex flex-col gap-1.5">
      <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) onSave(); }}>
        <label htmlFor="project-name" className="text-[13px] text-muted">Project name</label>
        <input id="project-name" value={name} maxLength={120} onChange={(e) => onNameChange(e.target.value)}
          className="min-w-48 flex-1 rounded-[3px] border border-line bg-surface px-2 py-1 text-[15px] focus:border-ink focus:outline-none" />
        <button type="submit" disabled={saving || !name.trim() || status === "saved"}
          className="rounded-[3px] border border-ink px-3 py-1 text-[15px] font-medium hover:bg-ink hover:text-surface disabled:cursor-not-allowed disabled:border-line disabled:text-muted disabled:hover:bg-transparent">
          {saving ? "Saving..." : "Save project"}
        </button>
        <span aria-live="polite" className={`text-[13px] ${status === "unsaved" ? "text-warn" : "text-muted"}`}>{STATUS_TEXT[status]}</span>
      </form>
      {error && <p role="alert" className="border-l-2 border-revision pl-2 text-[13px]">{error}</p>}
    </div>
  );
}
