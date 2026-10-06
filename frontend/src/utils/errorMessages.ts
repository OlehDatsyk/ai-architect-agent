/** Clear messages for the backend's Claude error codes. The backend also sends a safe message;
 *  outside production it adds Anthropic's own reason, which is shown after the message. */
export const CLAUDE_MESSAGES: Record<string, string> = {
  CLAUDE_AUTH_ERROR: "Claude API authentication failed. Check the API key (ANTHROPIC_API_KEY in .env).",
  CLAUDE_PERMISSION_ERROR: "This API key is not allowed to use the configured Claude model.",
  CLAUDE_MODEL_ERROR: "The configured Claude model is unavailable. Check ANTHROPIC_MODEL in .env.",
  CLAUDE_BILLING_ERROR:
    "Your Anthropic account has no API credit. Add credit at console.anthropic.com (Settings, Billing). A Claude.ai subscription does not include API credit.",
  CLAUDE_SCHEMA_ERROR: "The architectural response schema was rejected by Claude.",
  CLAUDE_RATE_LIMIT: "Claude API rate limit reached. Please try again shortly.",
  CLAUDE_CONNECTION_ERROR: "Claude could not be reached. Check your internet connection and try again.",
  CLAUDE_UNAVAILABLE: "Claude is temporarily unavailable. Please try again shortly.",
  CLAUDE_BAD_REQUEST: "Claude rejected the request.",
};

export function describeError(code: string, message: string, reason?: unknown): string {
  const base = CLAUDE_MESSAGES[code] ?? message;
  return typeof reason === "string" && reason ? `${base} Anthropic said: "${reason}"` : base;
}
