"""Checks the connection to Claude step by step, using the same client and error handling as the app.

    python -m scripts.check_claude

1. Settings: is a key set, which model and SDK.
2. Plain text request, no prompt caching: proves the key, the account's credit, the model, the network.
3. The same with prompt caching on the system prompt.
4. Structured output with a tiny schema.
5. Structured output with the interpretation schema.
6. Structured output with the modification schema.

It stops at the first failure and prints the error code and Anthropic's own explanation. The
whole check costs a fraction of a cent: replies are capped at a few tokens, because Anthropic
validates a request (and its schema) before it starts generating.
"""

import asyncio
import sys

import anthropic

from app.agents.architect_agent import OUTPUT_SCHEMA as INTERPRETATION_SCHEMA
from app.agents.modification_agent import OUTPUT_SCHEMA as MODIFICATION_SCHEMA
from app.core.config import get_settings
from app.services.claude_service import TINY_SCHEMA, AnthropicStructuredClient, ClaudeError

ADVICE = {
    "CLAUDE_AUTH_ERROR": "Create a new key at console.anthropic.com and put it in .env (ANTHROPIC_API_KEY).",
    "CLAUDE_BILLING_ERROR": "Add API credit at console.anthropic.com (Settings, Billing).",
    "CLAUDE_MODEL_ERROR": "Set ANTHROPIC_MODEL in .env to a model your account can use, then restart the backend.",
    "CLAUDE_PERMISSION_ERROR": "Check the key's workspace permissions at console.anthropic.com.",
    "CLAUDE_CONNECTION_ERROR": "Check your internet connection, VPN or proxy settings.",
}


async def run() -> int:
    settings = get_settings()
    print("1. Settings")
    if not settings.anthropic_configured or settings.anthropic_api_key is None:
        print("   FAILED: ANTHROPIC_API_KEY is not set. Add it to the .env file in the project root.")
        return 1
    key = settings.anthropic_api_key.get_secret_value()
    print(f"   API key: set ({len(key)} characters, {'starts with sk-ant-' if key.startswith('sk-ant-') else 'does NOT start with sk-ant-: check it was copied whole'})")
    print(f"   Model:   {settings.anthropic_model}")
    print(f"   SDK:     anthropic {anthropic.__version__}")
    client = AnthropicStructuredClient(api_key=key, model=settings.anthropic_model, max_tokens=64,
                                       timeout=60, max_retries=1, expose_details=True)
    user = [{"role": "user", "content": "Reply briefly."}]
    steps = [
        ("2. Plain text request (no prompt caching)", lambda: client.generate_text("Reply with OK", max_tokens=8)),
        ("3. Plain text request with prompt caching", lambda: client.generate_text("Reply with OK", system="You are a test.", max_tokens=8, cache=True)),
        ("4. Structured output, tiny schema", lambda: client.structured_once(system=None, messages=user, schema=TINY_SCHEMA, max_tokens=32)),
        ("5. Structured output, interpretation schema", lambda: client.structured_once(system=None, messages=user, schema=INTERPRETATION_SCHEMA, max_tokens=64)),
        ("6. Structured output, modification schema", lambda: client.structured_once(system=None, messages=user, schema=MODIFICATION_SCHEMA, max_tokens=64)),
    ]
    for title, step in steps:
        print(f"\n{title}")
        try:
            await step()
        except ClaudeError as exc:
            print(f"   FAILED: {exc.code} (HTTP {exc.http_status}, {exc.error_type}, request {exc.request_id})")
            print(f"   Anthropic said: {exc.reason}")
            if exc.code in ADVICE:
                print(f"   What to do: {ADVICE[exc.code]}")
            elif title.startswith(("3.",)):
                print("   Prompt caching is the problem: set ANTHROPIC_PROMPT_CACHING=false in .env (the app also drops it automatically).")
            elif title.startswith(("5.", "6.")):
                print("   The app's schema was rejected. The app will fall back to JSON-only replies; please report this output.")
            return 1
        print("   OK")
    print("\nEverything works: the app can interpret briefs and apply changes.")
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
