import { useState } from "react";

import type { ProjectListItem } from "../types/design";

interface Props {
  projects: ProjectListItem[];
  currentId: string | null;
  disabled: boolean;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}

const dateFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function ProjectsPanel({ projects, currentId, disabled, onOpen, onDelete }: Props) {
  const [confirming, setConfirming] = useState<string | null>(null);
  return (
    <section aria-labelledby="projects-title" className="flex flex-col gap-2 border-t border-line pt-5">
      <h2 id="projects-title" className="text-[17px] font-semibold">Projects</h2>
      {projects.length === 0 ? (
        <p className="text-[13px] text-muted">Saved designs appear here.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line">
          {projects.map((p) => (
            <li key={p.id} className="flex items-center gap-3 py-2">
              {p.thumbnail_url && <img src={p.thumbnail_url} alt="" className="h-9 w-16 shrink-0 border border-line object-cover" />}
              <div className="min-w-0 flex-1">
                <p className="truncate text-[15px] font-medium">{p.name}</p>
                {p.id === currentId && <p className="text-[13px] font-medium text-ok">Open now</p>}
                <p className="text-[13px] text-muted">
                  {p.floors} {p.floors === 1 ? "floor" : "floors"}, {p.bedrooms} bedrooms{p.changes > 0 ? `, ${p.changes} changes` : ""}. Saved {dateFormat.format(new Date(p.updated_at))}
                </p>
              </div>
              {confirming === p.id ? (
                <>
                  <button type="button" onClick={() => { setConfirming(null); onDelete(p.id); }} className="text-[13px] font-medium text-revision underline-offset-2 hover:underline">Confirm delete</button>
                  <button type="button" onClick={() => setConfirming(null)} className="text-[13px] text-muted hover:text-ink">Keep</button>
                </>
              ) : (
                <>
                  <button type="button" disabled={disabled} onClick={() => onOpen(p.id)} aria-label={`Open ${p.name}`}
                    className="text-[13px] font-medium underline-offset-2 hover:underline disabled:opacity-50">Open</button>
                  <button type="button" disabled={disabled} onClick={() => setConfirming(p.id)} aria-label={`Delete ${p.name}`}
                    className="text-[13px] text-muted hover:text-ink disabled:opacity-50">Delete</button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
