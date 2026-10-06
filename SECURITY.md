# AI Architect Agent - Security

This document describes the security model of AI Architect Agent as implemented, its known weaknesses, and what would need to change before any public deployment. It complements [Architecture](ARCHITECTURE.md), [API Documentation](API_DOCUMENTATION.md) and the [Installation Guide](INSTRUCTION.md).

---

## 1. Security Overview

AI Architect Agent is designed as a **single-user application running on the user's own machine**: the backend binds to `127.0.0.1`, the frontend runs on the Vite development server, and generated files are written to the local `output/` folder.

Within that context the main assets are:

- **the Anthropic API key**, which can spend money;
- **the machine itself**, because the backend starts Blender processes and writes files;
- **the user's saved designs**.

The main untrusted inputs are building briefs and change requests (which go to Claude), Claude's replies, and anything sent to the HTTP API.

The central design choice is that **AI output never becomes executable code**. Claude returns structured data, which is validated three times (schema, Pydantic, rules) and then compiled by deterministic code into a data file for Blender, which validates it again.

## 2. API Key Security

`ANTHROPIC_API_KEY` must be handled as follows. The current code supports each rule:

| Rule | How the code supports it |
| --- | --- |
| Backend only | Read by `Settings` on the backend; no endpoint returns it; the frontend never needs it |
| Stored in `.env` | `.env` in the project root, ignored by Git |
| Never in the frontend | The browser calls the backend, which calls Anthropic |
| Never in Git | `.gitignore` excludes `.env` and `.env.*` (but keeps `.env.example`, which has an empty key) |
| Never in logs | Held as a Pydantic `SecretStr`; Claude failures are logged with status, type, request ID and message only; a test asserts the key is absent from the log |
| Never in screenshots | Users' responsibility: the System panel only says *Configured on the server* |
| Rotate if exposed | If a key ever appears in a commit, chat, screenshot or log, revoke it in the Anthropic console and create a new one; deleting the text is not enough |

The diagnostic script prints only the key's length and whether it starts with `sk-ant-`.

## 3. Environment Variables

All configuration is typed and bounded by `Settings` (`backend/app/core/config.py`) and documented in `.env.example`. Security-relevant settings:

| Variable | Security effect |
| --- | --- |
| `ANTHROPIC_API_KEY` | Secret; see above |
| `APP_ENV` | `production` stops Anthropic's error text (`reason` and related fields) being sent to the browser |
| `CORS_ORIGINS` | Which browser origins may call the API (default: the local Vite server only) |
| `MAX_REQUEST_BYTES` | Request body limit (default 1 MB) |
| `BLENDER_EXECUTABLE` | The program the backend runs; trusted configuration, never taken from requests |
| `BLENDER_TIMEOUT_SECONDS`, `RENDER_TIMEOUT_SECONDS` | Bound how long a Blender process may run |
| `JOBS_DIR`, `PROJECTS_DIR` | Where files are written; blank values fall back to the defaults, never the current directory |

## 4. .gitignore

Verified in the repository's `.gitignore`:

| Pattern | Status |
| --- | --- |
| `.env` | Ignored |
| `.env.*` | Ignored |
| `!.env.example` | Explicitly kept, so the example stays in the repository |
| `output/` | Ignored (builds, renders, projects) |
| `.venv/`, `node_modules/`, caches, `frontend/dist/` | Ignored |
| `*.blend1` | Ignored (Blender backup files) |
| `.vscode/`, `.idea/` | Ignored |

There are no patterns for private key or certificate files (`*.pem`, `*.key`). The project uses none, so this is low risk; adding them is a reasonable precaution.

## 5. Secret Exposure Check

The tracked files were searched for Anthropic keys, AWS access keys, GitHub tokens, private key blocks and hard-coded passwords.

- **No real credentials were found.**
- The only matches are **deliberately fake placeholder keys in tests**, used to prove the key never leaks: in `backend/tests/test_health.py`, `backend/tests/test_config.py` and `backend/tests/e2e/test_definition_of_done.py`. They are not valid keys.
- No `.env` file is tracked.

Each developer's own `.env` is outside Git and was not examined. Run `git status` before committing: `.env` must never appear in it.

## 6. Anthropic API Security

- **Backend-only requests.** All calls go through `AnthropicStructuredClient` (`backend/app/services/claude_service.py`).
- **Error sanitisation.** Every SDK error becomes a fixed `CLAUDE_*` code and a fixed message. Anthropic's own text is attached as `reason` only outside production. Anthropic's error messages do not contain the key.
- **Logging.** Failures log the HTTP status, Anthropic error type, request ID, model and message: enough to diagnose, nothing secret.
- **Cost control.** Each brief or change uses at most `ARCHITECT_MAX_ATTEMPTS` calls (default 2), replies are capped by `ANTHROPIC_MAX_TOKENS`, and the health check is cached for 10 minutes. **Rate limiting is not currently implemented in the backend**; only Anthropic's own account limits apply.

## 7. Frontend Security

| Area | Finding |
| --- | --- |
| Secrets | None in the frontend; it only knows whether a key is configured |
| API communication | Same-origin `/api` requests through the Vite proxy; no credentials or tokens |
| User input | Sent as JSON; validated by the backend (length limits, types) |
| Rendering of text | React escapes all text; the code does not use `dangerouslySetInnerHTML` |
| Generated SVG floor plans | Shown through an `<img>` data URL, so the browser treats them as images and cannot run scripts inside them |
| Error messages | Codes are translated to fixed messages; Anthropic's reason appears only in development |

## 8. Backend Security

| Control | Implementation |
| --- | --- |
| Input validation | Pydantic models with `extra="forbid"`, string length limits, numeric bounds and enums on every request body |
| Body size | Middleware rejects bodies over `MAX_REQUEST_BYTES` with `413` before parsing |
| Request IDs | Accepted from `X-Request-ID` only if alphanumeric and at most 64 characters; otherwise generated |
| Exception handling | Expected failures return the error envelope; unexpected ones return `500 internal_error` with no details, and the traceback goes only to the log |
| CORS | Restricted origins, listed methods and headers, no credentials (see [section 14](#14-cors)) |
| File access | Every ID used in a path is checked against a strict pattern first (see [section 12](#12-file-security)) |
| Subprocesses | Argument lists, no shell (see [section 9](#9-blendersubprocess-security)) |

## 9. Blender/Subprocess Security

This is the most security-sensitive part of the project, because the backend starts external programs.

**Existing protections**

| Risk | Protection |
| --- | --- |
| Command injection | `subprocess.run` is always given an **argument list**; `shell=True` is never used. The only arguments are the configured executable, the project's own script path and paths built from server-generated IDs |
| Untrusted executable | `BLENDER_EXECUTABLE` comes only from server configuration, never from a request |
| Arbitrary code execution through AI | Claude never produces code. The scene sent to Blender is **data** (boxes, meshes, materials, cameras, lights), and `blender/scripts/scene_validation.py` re-validates it: allowed element kinds, name patterns, finite and bounded numbers, valid mesh indices, size limits. A test sends a tampered scene to real Blender and checks it is refused |
| User or add-on scripts | Blender application mode runs with `--background --factory-startup`, which skips the user's start-up file and add-ons |
| Render options | `render_runner.py` checks every option against its own whitelists and only accepts cameras that exist in the file; the render ID is checked against a strict hexadecimal pattern **before** it is used as a file name |
| Runaway processes | Build and render timeouts (`BLENDER_TIMEOUT_SECONDS`, `RENDER_TIMEOUT_SECONDS`) |

**Weaknesses**

- Blender runs with the **same user permissions as the backend**. There is no sandbox, container or resource limit beyond the timeout.
- A Blender process started by a request keeps running until it finishes or times out, even if the client disconnects.
- There is **no limit on how many builds or renders run at once**, other than the thread pool.

## 10. Prompt Injection

Building briefs and change requests are untrusted text sent to Claude. Someone could write "ignore your instructions and..." into a brief.

What limits the impact:

- **Separation.** System instructions are sent as the system prompt; the brief is wrapped in tags (`<building_request>`, `<change_request>`), and tag-like text inside it is stripped. The modification prompt instructs Claude to treat the request purely as a description of a change and to ignore instructions inside it.
- **Constrained output.** Replies must match a JSON Schema (structured outputs), so Claude cannot answer with free text, code or commands.
- **Validation.** Every reply is parsed and validated by Pydantic and by the validation rules; invalid output is rejected.
- **No capabilities to abuse.** Claude has no tools, cannot read files, cannot browse and cannot run anything. The worst outcome of a successful injection is an odd design, a refusal or a wasted request.

**Residual risk:** an injected brief could produce a strange but valid design, or consume API credit.

## 11. AI Output Validation

```
Claude reply
  -> structured output (constrained to the JSON Schema)
  -> json.loads
  -> Pydantic model (DesignIntent or ChangeSet): types, bounds, enums, unknown fields rejected
  -> rules: intent validation; for changes, IDs must exist and materials must suit the surface
  -> deterministic planner and BuildingSpecification validation
  -> scene compiler -> scene.json -> re-validated inside Blender
```

Claude's output is never trusted on its own: a reply that fails any step is sent back once with the specific problems, and then rejected.

## 12. File Security

| Item | Protection |
| --- | --- |
| Job IDs, render IDs, project IDs | Generated by the server (`uuid4().hex`) and checked against a 32-character lowercase hexadecimal pattern before touching the filesystem; anything else is a 404 |
| Example IDs | Slug pattern only, resolved inside the examples folder |
| Saved projects | The client sends only IDs; the server derives every path and URL itself. Client-supplied path, URL or report fields are rejected (`extra="forbid"`) |
| Writes | Project files are written to a temporary file and renamed into place |
| Downloads | `.blend` and `.png` files are served only from validated job folders |
| Cleanup | **Not currently implemented**: `output/jobs/` and `output/projects/` grow until cleaned manually |

## 13. API Security

**The current backend API does not implement user authentication.** Any program that can reach the backend's address can interpret briefs (spending API credit), start Blender builds and renders, and read, overwrite or delete saved projects.

On `127.0.0.1` this means any program running on the same machine, which is acceptable for a personal development tool. **It is not acceptable on a shared network or the internet.**

## 14. CORS

Configured in `backend/app/main.py`:

| Setting | Value |
| --- | --- |
| Allowed origins | `CORS_ORIGINS`, default `http://localhost:5173` and `http://127.0.0.1:5173` |
| Allowed methods | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` |
| Allowed headers | `Content-Type`, `X-Request-ID` |
| Credentials | Not allowed |

CORS only controls which *web pages* may call the API from a browser. It does not stop other programs on the machine from calling it, and it is no substitute for authentication.

## 15. Rate Limiting

**Rate limiting is not currently implemented.** Repeated requests could spend Anthropic credit or start many Blender processes. Before any shared or public deployment, add per-client limits, especially on `/api/designs/interpret`, `/api/designs/modify`, `/api/designs/build` and the render endpoint.

## 16. Logging Security

| Logged (safe) | Never logged |
| --- | --- |
| Model name, SDK version, whether a key is set | The API key or any part of it |
| HTTP status, Anthropic error type and message, request IDs | Other secrets or the full environment |
| Token usage per request | |
| Build and render IDs, timings, object counts | |
| Tracebacks of unexpected errors (server log only) | |

Logs go to the backend's console. Briefs are not logged by the service layer, but treat logs as potentially containing design details.

## 17. Dependency Security

- **Python:** dependencies are bounded by version ranges in `requirements.txt` and `requirements-dev.txt`, but **there is no lockfile**, so installs on different days can resolve to different versions. Recommended: a lockfile (for example with `pip-tools` or `uv`) and `pip-audit`.
- **Frontend:** `frontend/package-lock.json` pins exact versions. Run `npm audit` regularly.
- **CI** (`.github/workflows/ci.yml`) runs lint and tests but **no vulnerability scanning**. Recommended: Dependabot or an audit step.
- **Blender:** the user's installation; keep it updated.

## 18. Threat Model

| Threat | Risk (local use) | Current protection | Recommendation |
| --- | --- | --- | --- |
| API key exposure in Git | Medium | `.env` ignored; no secrets tracked; `SecretStr`; key never returned or logged | Keep it; add a pre-commit secret scanner |
| API key exposure by the user (screenshots, chats) | Medium | Key never displayed by the app | Rotate any exposed key immediately |
| Prompt injection | Low | Tags, system prompt, schema-constrained output, validation, no tools | Keep Claude tool-free |
| Malicious API input | Low | Pydantic validation, size limits, unknown fields rejected | Keep strict models |
| Command injection | Low | Argument lists, no shell, executable from configuration only | Keep it; never accept executables or paths from requests |
| Code execution through Blender | Low | Data-only scene, re-validated in Blender; `--factory-startup` | Run Blender in a sandbox for any shared use |
| Path traversal | Low | Strict ID patterns before any filesystem access; server-derived paths | Keep it |
| Excessive API usage | Medium | Attempt and token caps; cached health check | Rate limiting; spending limits in the Anthropic console |
| Unauthorised API access | Low locally, **Critical if exposed** | Localhost binding by default | Authentication before any non-local deployment |
| Denial of service (many builds or renders) | Low locally, High if exposed | Timeouts only | Job queue with concurrency limits |
| Dependency vulnerabilities | Medium | Version ranges; npm lockfile | Python lockfile, `pip-audit`, `npm audit`, Dependabot |
| Disk exhaustion from generated files | Low | None | Retention or cleanup for `output/` |

## 19. Local Deployment vs Public Deployment

As shipped, the application is **reasonably safe on `127.0.0.1` for one user**. It is **not ready for public internet exposure**. Before that, at minimum:

1. Add authentication and per-user authorisation (projects are currently global).
2. Add rate limiting and spending limits.
3. Run builds and renders through a job queue with concurrency limits, in sandboxed workers.
4. Serve over HTTPS behind a reverse proxy; set `APP_ENV=production` and tighten `CORS_ORIGINS`.
5. Replace the in-process caches and the process-local lock with shared infrastructure.
6. Add retention and cleanup for generated files.
7. Pin and scan dependencies.

## 20. Security Checklist

Items marked [x] were verified in the repository.

- [x] `.env` excluded from Git, and `.env.example` kept with an empty key
- [x] No real secrets in tracked files (test placeholders only)
- [x] API key used only by the backend, stored as `SecretStr`, never returned or logged
- [x] Request bodies validated by Pydantic, unknown fields rejected
- [x] Request size limited
- [x] Claude output validated (schema, Pydantic, rules) and never executed
- [x] Blender receives data only and re-validates it
- [x] Subprocess arguments passed as lists, no shell
- [x] IDs validated before filesystem access; paths derived by the server
- [x] CORS restricted to the local frontend, without credentials
- [x] Production mode hides Anthropic's error text from the browser
- [ ] Exposed keys rotated (each user's responsibility)
- [ ] Rate limiting configured
- [ ] Authentication added before any non-local deployment
- [ ] Python dependencies locked and scanned
- [ ] Generated files cleaned up automatically
- [ ] Blender sandboxed for shared use

## 21. Reporting a Vulnerability

Please do **not** report security problems in public issues.

- If the repository has **GitHub private vulnerability reporting** enabled, use **Security -> Report a vulnerability** on the repository page.
- Otherwise, contact the repository owner privately through their GitHub profile.

Include what is affected, how to reproduce it, and the impact. Never include real API keys or other secrets in a report; if one was exposed, revoke it first.
