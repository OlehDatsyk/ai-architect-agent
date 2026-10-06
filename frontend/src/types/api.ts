// Mirrors backend/app/schemas/health.py. Keep in sync when the schema changes.

import type { ValidationIssue } from "./design";

export type BlenderStatus = "not_configured" | "found" | "missing";

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  timestamp: string;
  checks: {
    anthropic: { configured: boolean; model: string; verification: ClaudeVerification };
    blender: { status: BlenderStatus; detail: string };
  };
}

/** Error envelope returned by every backend error response. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string | null;
    /** Anthropic's own explanation of a Claude error; sent only outside production. */
    reason?: string;
    /** Present when a design could not be interpreted. */
    issues?: ValidationIssue[];
  };
}

/** Whether Anthropic actually accepts requests (a key being configured does not prove that). */
export interface ClaudeVerification {
  status: "verified" | "failed" | "not_checked";
  structured_outputs: "ok" | "failed" | "not_checked";
  code: string | null;
  message: string | null;
  checked_at: string | null;
}
