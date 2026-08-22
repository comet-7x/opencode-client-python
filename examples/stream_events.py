"""Watch a prompt live: consume the SSE event stream while a prompt runs.

The example sends a prompt with ``prompt_async`` (fire-and-forget), then
prints server events — including incremental text deltas — until the
session goes idle, which is the natural "turn complete" signal.

Requires a running opencode server.

Run:

    uv run python examples/stream_events.py
"""

from __future__ import annotations

import argparse
import asyncio

from opencode_client import AsyncOpenCodeClient


async def main(base_url: str, provider_id: str | None = None, model_id: str | None = None) -> None:
    """Stream events from the server while one prompt executes.

    Args:
        base_url: opencode server URL.
        provider_id: Optional provider to pin for the prompt.
        model_id: Optional model to pin for the prompt.
    """
    async with AsyncOpenCodeClient(base_url) as client:
        session = await client.sessions.create()

        async def listen() -> None:
            """Read the /event stream until the session goes idle (auto-reconnects on drops)."""
            async with client.server.stream_events() as stream:
                async for event in stream.aiter_events():
                    if event.type == "message.part.delta":
                        props = event.properties
                        if props.get("field") == "text":
                            print(props.get("delta", ""), end="", flush=True)
                    else:
                        print(f"\n[event] {event.type}")
                    if event.type == "session.idle":
                        return

        listener = asyncio.create_task(listen())
        await asyncio.sleep(0.5)  # let the stream attach before the turn starts

        model = {"providerID": provider_id, "modelID": model_id} if provider_id and model_id else None
        await client.sessions.prompt_async(session.id, "Count from one to five.", model=model)
        await listener
        print()

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
