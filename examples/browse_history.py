"""Browse sessions on the server: list them, then render one message-by-message.

Shows how to walk ``MessageWithParts`` and its typed parts (text, tool
calls with their state, reasoning, step boundaries, ...).

Requires a running opencode server with at least one session.

Run:

    uv run python examples/browse_history.py
    uv run python examples/browse_history.py --session ses_xxx
"""

from __future__ import annotations

import argparse
import asyncio

from opencode_client import AssistantMessage, AsyncOpenCodeClient, Part


def _render(parts: list[Part]) -> None:
    """Print a message's parts as readable one-liners.

    Args:
        parts: The part list of one :class:`MessageWithParts`.
    """
    for part in parts:
        if part.type == "text":
            print(f"  text: {part.text[:120]!r}")
        elif part.type == "tool":
            # title exists only on the running/completed tool states
            print(f"  tool: {part.tool} [{part.state.status}] {getattr(part.state, 'title', '') or '-'}")
        elif part.type == "reasoning":
            print(f"  reasoning: {len(part.text)} chars")
        elif part.type == "step-finish":
            print(f"  step-finish: {part.reason} (cost {part.cost})")
        else:
            print(f"  part: {part.type}")


async def main(base_url: str, session_id: str | None = None) -> None:
    """List sessions and print the message history of one of them.

    Args:
        base_url: opencode server URL.
        session_id: Session to render; the most recent one when omitted.
    """
    async with AsyncOpenCodeClient(base_url) as client:
        sessions = await client.sessions.list_sessions(limit=10)
        for s in sessions:
            print(f"{s.id}  {s.title!r:<40} {s.time.updated}")

        target = session_id or (sessions[0].id if sessions else None)
        if target is None:
            print("no sessions found")
            return

        messages = await client.sessions.list_messages(target)
        print(f"\n--- {target}: {len(messages)} messages ---")
        for msg in messages:
            info = msg.info
            if isinstance(info, AssistantMessage):
                print(f"[assistant] {info.id}  finish={info.finish}")
            else:
                print(f"[user] {info.id}")
            _render(msg.parts)


def cli() -> None:
    """Parse CLI arguments and run :func:`main`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:4096")
    parser.add_argument("--session", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.url, args.session))


if __name__ == "__main__":
    cli()
