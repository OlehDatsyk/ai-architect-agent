import { useCallback, useState } from "react";

import { ApiError, buildDesign } from "../services/api";
import type { BuildResponse } from "../types/design";

export type BuildState =
  | { kind: "idle" }
  | { kind: "building" }
  | { kind: "success"; result: BuildResponse }
  | { kind: "error"; message: string };

export function useBuild() {
  const [state, setState] = useState<BuildState>({ kind: "idle" });

  const build = useCallback(async (specification: Record<string, unknown>) => {
    setState({ kind: "building" });
    try {
      setState({ kind: "success", result: await buildDesign(specification) });
    } catch (error) {
      setState({ kind: "error", message: error instanceof ApiError ? error.message : "Something unexpected went wrong." });
    }
  }, []);

  const reset = useCallback(() => setState({ kind: "idle" }), []);
  const restore = useCallback((result: BuildResponse | null) => setState(result ? { kind: "success", result } : { kind: "idle" }), []);
  return { state, build, reset, restore };
}
