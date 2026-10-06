import { useCallback, useEffect, useState } from "react";

import { ApiError, createProject, deleteProject, listProjects, updateProject } from "../services/api";
import type { ProjectListItem, ProjectPayload, ProjectView } from "../types/design";

export interface CurrentProject {
  id: string;
  version: number;
  name: string;
  /** What was last saved, to tell whether the design has changed since. */
  savedSignature: string;
}

/** A stable fingerprint of what a save would store. */
export function signature(payload: ProjectPayload | null): string {
  return payload ? JSON.stringify([payload.name, payload.specification, payload.overrides, payload.history.length,
    payload.build?.job_id ?? null, payload.renders.map((r) => r.render_id)]) : "";
}

export function useProjects() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [current, setCurrent] = useState<CurrentProject | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProjects(await listProjects());
    } catch {
      setProjects([]);  // the list is a convenience; the main flow does not depend on it
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const save = useCallback(async (payload: ProjectPayload) => {
    setBusy(true);
    setError(null);
    try {
      const saved = current ? await updateProject(current.id, current.version, payload) : await createProject(payload);
      setCurrent({ id: saved.id, version: saved.version, name: saved.name, savedSignature: signature(payload) });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The project could not be saved.");
    } finally {
      setBusy(false);
    }
  }, [current, refresh]);

  const opened = useCallback((project: ProjectView, payload: ProjectPayload) => {
    setCurrent({ id: project.id, version: project.version, name: project.name, savedSignature: signature(payload) });
    setError(null);
  }, []);

  const remove = useCallback(async (id: string) => {
    try {
      await deleteProject(id);
      if (current?.id === id) setCurrent(null);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The project could not be deleted.");
    }
  }, [current, refresh]);

  const forget = useCallback(() => setCurrent(null), []);
  return { projects, current, busy, error, save, opened, remove, forget, refresh };
}
