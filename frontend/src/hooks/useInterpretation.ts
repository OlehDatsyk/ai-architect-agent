import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, interpretDesign, modifyDesign, planDesign } from "../services/api";
import type { DesignRequest, InterpretationResult, ModificationRecord, Override, PlanResponse, ValidationIssue } from "../types/design";

export interface PlanFailure {
  message: string;
  issues: ValidationIssue[];
}

export type InterpretationState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "planning"; result: InterpretationResult }
  | {
      kind: "success";
      result: InterpretationResult;
      plan: PlanResponse | null;
      planError: PlanFailure | null;
      /** Finishing changes made since the brief, re-applied by the backend after every re-plan. */
      overrides: Override[];
      history: ModificationRecord[];
      modifying: boolean;
      modifyError: string | null;
    }
  | { kind: "error"; message: string; code: string; issues: ValidationIssue[] };

function describe(error: unknown): { message: string; code: string; issues: ValidationIssue[] } {
  if (error instanceof ApiError) return { message: error.message, code: error.code, issues: error.issues };
  return { message: "Something unexpected went wrong.", code: "unknown", issues: [] };
}

/** Brief -> Claude interpretation -> deterministic floor plan, as one user action. */
export function useInterpretation() {
  const [state, setState] = useState<InterpretationState>({ kind: "idle" });
  const controllerRef = useRef<AbortController | null>(null);
  // The latest state, for callbacks that must send the current design (setState updaters may run later).
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => () => controllerRef.current?.abort(), []);

  const interpret = useCallback(async (request: DesignRequest) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ kind: "loading" });

    let result: InterpretationResult;
    try {
      result = await interpretDesign(request, controller.signal);
    } catch (error) {
      if (!controller.signal.aborted) setState({ kind: "error", ...describe(error) });
      return;
    }
    if (controller.signal.aborted) return;

    // Keep Claude's interpretation even if planning fails, so the user can still review it.
    setState({ kind: "planning", result });
    try {
      const plan = await planDesign(result.intent, controller.signal);
      if (!controller.signal.aborted) setState({ kind: "success", result, plan, planError: null, overrides: [], history: [], modifying: false, modifyError: null });
    } catch (error) {
      if (controller.signal.aborted) return;
      const { message, issues } = describe(error);
      setState({ kind: "success", result, plan: null, planError: { message, issues }, overrides: [], history: [], modifying: false, modifyError: null });
    }
  }, []);

  /** Change the current design in plain English. Returns true if the design changed. */
  const modify = useCallback(async (request: string): Promise<boolean> => {
    const snapshot = stateRef.current;
    if (snapshot.kind !== "success" || !snapshot.plan || snapshot.modifying) return false;
    setState((s) => (s.kind === "success" ? { ...s, modifying: true, modifyError: null } : s));
    try {
      const updated = await modifyDesign({ request, intent: snapshot.result.intent, overrides: snapshot.overrides, specification: snapshot.plan.specification });
      setState((s) => s.kind !== "success" ? s : {
        ...s,
        result: { ...s.result, intent: updated.intent },
        plan: { specification: updated.specification, report: updated.report, summary: updated.summary, notes: updated.notes, plans: updated.plans, completed_stages: updated.completed_stages },
        overrides: updated.overrides,
        history: [...s.history, { request, summary: updated.change_summary, changes: updated.changes, assumptions: updated.assumptions }],
        modifying: false,
        modifyError: null,
      });
      return true;
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Something unexpected went wrong.";
      setState((s) => (s.kind === "success" ? { ...s, modifying: false, modifyError: message } : s));
      return false;
    }
  }, []);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    setState({ kind: "idle" });
  }, []);

  /** Show a saved project as if it had just been interpreted, planned and changed. */
  const restore = useCallback((restored: Extract<InterpretationState, { kind: "success" }>) => {
    controllerRef.current?.abort();
    setState(restored);
  }, []);

  return { state, interpret, modify, cancel, restore };
}
