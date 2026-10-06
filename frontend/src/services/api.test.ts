import { describe, expect, it, vi } from "vitest";

import { ApiError, fetchHealth, request } from "./api";

const healthBody = {
  status: "ok",
  service: "AI Architect Agent",
  version: "0.1.0",
  environment: "test",
  timestamp: "2026-10-02T12:00:00Z",
  checks: {
    anthropic: { configured: false, model: "claude-sonnet-5-5" },
    blender: { status: "not_configured", detail: "BLENDER_EXECUTABLE is not set." },
  },
};

function mockFetch(impl: () => Promise<Response>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(impl);
}

describe("fetchHealth", () => {
  it("calls the relative /api/health path and returns the parsed body", async () => {
    const spy = mockFetch(async () => new Response(JSON.stringify(healthBody), { status: 200 }));

    await expect(fetchHealth()).resolves.toEqual(healthBody);
    expect(spy.mock.calls[0]?.[0]).toBe("/api/health");
  });

  it("turns the backend error envelope into an ApiError with the server message", async () => {
    mockFetch(async () =>
      new Response(
        JSON.stringify({ error: { code: "internal_error", message: "Something went wrong on the server.", request_id: "abc" } }),
        { status: 500 },
      ),
    );

    const error = await fetchHealth().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "internal_error", status: 500, requestId: "abc", message: "Something went wrong on the server." });
  });

  it("handles non-JSON error responses", async () => {
    mockFetch(async () => new Response("<html>Server error</html>", { status: 500 }));

    await expect(fetchHealth()).rejects.toMatchObject({ code: "http_error", status: 500 });
  });

  it("treats a proxy 502 without an error envelope as the backend being unreachable", async () => {
    mockFetch(async () => new Response("", { status: 502 }));

    await expect(fetchHealth()).rejects.toMatchObject({ code: "network_error", message: expect.stringContaining("Can't reach the backend") });
  });

  it("reports a friendly message when the backend is unreachable", async () => {
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(fetchHealth()).rejects.toMatchObject({ code: "network_error", message: expect.stringContaining("Can't reach the backend") });
  });

  it("keeps its timeout when the caller also passes a signal", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      }),
    );

    await expect(request("/api/slow", { signal: new AbortController().signal }, 20)).rejects.toMatchObject({ code: "timeout" });
  });

  it("reports a caller cancellation as cancelled, not as a timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      }),
    );
    const controller = new AbortController();
    const pending = request("/api/slow", { signal: controller.signal }, 10_000);
    controller.abort();

    await expect(pending).rejects.toMatchObject({ code: "cancelled" });
  });

  it("carries validation issues from the error envelope", async () => {
    const issue = { severity: "error", code: "room_inaccessible", message: "WC cannot be reached.", element_ids: [], location: null };
    mockFetch(async () => new Response(JSON.stringify({ error: { code: "design_interpretation_failed", message: "Invalid layout.", request_id: "r", issues: [issue] } }), { status: 422 }));

    const error = await request("/api/designs/interpret").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).issues).toEqual([issue]);
  });
});
