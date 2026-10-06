import { useCallback, useEffect, useState } from "react";

import { ApiError, fetchHealth } from "../services/api";
import type { HealthResponse } from "../types/api";

export type HealthState =
  | { kind: "loading" }
  | { kind: "ready"; data: HealthResponse }
  | { kind: "error"; message: string };

export function useHealth() {
  const [state, setState] = useState<HealthState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    fetchHealth(controller.signal)
      .then((data) => setState({ kind: "ready", data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof ApiError ? error.message : "Unexpected error while checking the backend.";
        setState({ kind: "error", message });
      });
    return () => controller.abort();
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { state, retry };
}
