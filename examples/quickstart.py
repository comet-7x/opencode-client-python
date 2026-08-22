"""Quickstart: health check, create a session, send a prompt, print the answer.

Requires a running opencode server (``opencode serve --port 4096``).

Run:

    uv run python examples/quickstart.py
    uv run python examples/quickstart.py --url http://127.0.0.1:20001
"""

from __future__ import annotations

import argparse
import asyncio

from opencode_client import AssistantMessage, AsyncOpenCodeClient, TextPart


async def main(base_url: str, provider_id: str | None = None, model_id: str | None = None) -> None:
    """Connect, create a session, ask a question, print the reply text.

    Args:
        base_url: opencode server URL.
        provider_id: Optional provider to pin; session default when omitted.
        model_id: Optional model to pin; session default when omitted.
    """
    async with AsyncOpenCodeClient(base_url) as client:
        health = await client.server.health()
        print("health:", health.version)

        session = await client.sessions.create()
        print("session:", session.id)

        model = {"providerID": provider_id, "modelID": model_id} if provider_id and model_id else None
        reply = await client.sessions.prompt(session.id, "Reply with exactly one word: pong", model=model)

        for part in reply.parts:
            if isinstance(part, TextPart):
                print("assistant:", part.text.strip())

        if isinstance(reply.info, AssistantMessage):
            print("tokens:", reply.info.tokens.total)
        await client.sessions.delete(session.id)


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:4096")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.url, args.provider, args.model))


if __name__ == "__main__":
    cli()
