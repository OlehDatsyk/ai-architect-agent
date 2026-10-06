import { describeError } from "../utils/errorMessages";
import type { ClaudeVerification, ApiErrorBody, HealthResponse } from "../types/api";
import type { BuildResponse, DesignIntent, ModifyResponse, Override, ProjectListItem, ProjectPayload, ProjectView, DesignRequest, InterpretationResult, PlanResponse, RenderRequest, RenderResponse, ValidationIssue } from "../types/design";

// Empty by default: requests go to /api on the same origin and the Vite proxy forwards them.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";
const DEFAULT_TIMEOUT_MS = 8000;
const UNREACHABLE_MESSAGE = "Can't reach the backend. Check that it is running on port 8000.";
// A dev proxy or gateway answers with these when the backend itself is down.
const GATEWAY_STATUSES = new Set([502, 503, 504]);

export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly requestId: string | null;
  /** Validation issues the backend attached to the error, if any. */
  readonly issues: ValidationIssue[];

  constructor(message: string, code: string, status: number | null, requestId: string | null = null, issues: ValidationIssue[] = []) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.issues = issues;
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return typeof error === "object" && error !== null && "message" in error && "code" in error;
}

export async function request<T>(path: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  // One controller aborts on timeout OR when the caller's own signal aborts.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const forwardAbort = () => controller.abort();
  if (init.signal?.aborted) controller.abort();
  init.signal?.addEventListener("abort", forwardAbort, { once: true });

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
      signal: controller.signal,
    });
  } catch (cause) {
    const aborted = cause instanceof DOMException && cause.name === "AbortError";
    const cancelled = aborted && Boolean(init.signal?.aborted);
    throw new ApiError(
      cancelled ? "The request was cancelled." : aborted ? "The backend took too long to respond." : UNREACHABLE_MESSAGE,
      cancelled ? "cancelled" : aborted ? "timeout" : "network_error",
      null,
    );
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener("abort", forwardAbort);
  }

  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    if (isErrorBody(body)) {
      const issues = Array.isArray(body.error.issues) ? body.error.issues : [];
      throw new ApiError(describeError(body.error.code, body.error.message, body.error.reason), body.error.code, response.status, body.error.request_id, issues);
    }
    if (GATEWAY_STATUSES.has(response.status)) {
      throw new ApiError(UNREACHABLE_MESSAGE, "network_error", response.status);
    }
    throw new ApiError(`The backend returned an unexpected error (HTTP ${response.status}).`, "http_error", response.status);
  }
  if (body === null) {
    throw new ApiError("The backend returned an empty or invalid response.", "invalid_response", response.status);
  }
  return body as T;
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health", { signal });
}

// Claude interpretation can take a while for large buildings, especially if a correction is needed.
const INTERPRET_TIMEOUT_MS = 180_000;

export function interpretDesign(body: DesignRequest, signal?: AbortSignal): Promise<InterpretationResult> {
  return request<InterpretationResult>(
    "/api/designs/interpret",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal },
    INTERPRET_TIMEOUT_MS,
  );
}

/** Lays out an interpreted design. Deterministic and fast; no Claude call is made. */
export function planDesign(intent: DesignIntent, signal?: AbortSignal): Promise<PlanResponse> {
  return request<PlanResponse>(
    "/api/designs/plan",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ intent }), signal },
    30_000,
  );
}

/** Builds the approved specification in Blender on the server and saves a .blend file. */
export function buildDesign(specification: Record<string, unknown>, signal?: AbortSignal): Promise<BuildResponse> {
  return request<BuildResponse>(
    "/api/designs/build",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ specification }), signal },
    600_000,
  );
}

/** Renders one image of a built design. High quality on a CPU can take several minutes. */
export function renderDesign(jobId: string, body: RenderRequest, signal?: AbortSignal): Promise<RenderResponse> {
  return request<RenderResponse>(
    `/api/designs/jobs/${encodeURIComponent(jobId)}/renders`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal },
    1_800_000,
  );
}

/** Applies a plain-English change to the current design; the response is the updated design. */
export function modifyDesign(body: { request: string; intent: DesignIntent; overrides: Override[]; specification: Record<string, unknown> }, signal?: AbortSignal): Promise<ModifyResponse> {
  return request<ModifyResponse>(
    "/api/designs/modify",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal },
    180_000,
  );
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export const listProjects = () => request<ProjectListItem[]>("/api/projects");
export const getProject = (id: string) => request<ProjectView>(`/api/projects/${encodeURIComponent(id)}`);
export const createProject = (body: ProjectPayload) =>
  request<ProjectView>("/api/projects", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
export const updateProject = (id: string, version: number, body: ProjectPayload) =>
  request<ProjectView>(`/api/projects/${encodeURIComponent(id)}`, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ ...body, version }) });

export async function deleteProject(id: string): Promise<void> {
  const response = await fetch(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok && response.status !== 204) throw new ApiError("The project could not be deleted.", "delete_failed", response.status);
}

/** Prove Anthropic accepts requests (cached on the server for 10 minutes unless refresh is set). */
export const verifyClaude = (refresh = false) =>
  request<ClaudeVerification>(`/api/health/claude${refresh ? "?refresh=true" : ""}`, {}, 90_000);
