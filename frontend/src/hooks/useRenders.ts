import { useCallback, useState } from "react";

import { ApiError, renderDesign } from "../services/api";
import type { RenderRequest, RenderResponse } from "../types/design";

export const DEFAULT_RENDER: RenderRequest = {
  camera: "Camera_Exterior_Front",
  preset: "day",
  quality: "preview",
  resolution: "1280x720",
  engine: "auto",
};

export interface RenderState {
  renders: RenderResponse[];
  busy: boolean;
  error: string | null;
}

export function useRenders() {
  const [state, setState] = useState<RenderState>({ renders: [], busy: false, error: null });

  const render = useCallback(async (jobId: string, request: RenderRequest) => {
    setState((s) => ({ ...s, busy: true, error: null }));
    try {
      const result = await renderDesign(jobId, request);
      setState((s) => ({ renders: [result, ...s.renders], busy: false, error: null }));
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Something unexpected went wrong.";
      setState((s) => ({ ...s, busy: false, error: message }));
    }
  }, []);

  const reset = useCallback(() => setState({ renders: [], busy: false, error: null }), []);
  const restore = useCallback((renders: RenderResponse[]) => setState({ renders, busy: false, error: null }), []);
  return { state, render, reset, restore };
}
