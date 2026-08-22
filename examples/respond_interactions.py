"""Keep a turn moving: auto-respond to pending permission/question requests.

This is the "interaction loop" pattern: start a prompt that may need a tool
permission or an answered follow-up question, then — watching the event stream
for the ``session.idle`` end-of-turn signal — poll the server's pending
interaction lists and answer each one until the turn finishes.

Defaults to the safe side:

- permission requests are answered ``reject`` (never auto-grant a tool);
- question requests are answered with the first available option label.

Pass ``--allow`` to auto-approve permissions with ``once`` instead.

Requires a running opencode server.

Run:

    uv run python examples/respond_interactions.py
    uv run python examples/respond_interactions.py --allow
"""

from __future__ import annotations

import argparse
import asyncio

from opencode_client import AsyncOpenCodeClient, SSEDecoder

POLL_SECONDS = 0.5
MAX_WAIT_SECONDS = 180.0


async def answer_pending(client: AsyncOpenCodeClient, *, allow: bool, model: dict[str, str] | None) -> None:
    """Run a prompt and auto-answer its pending interaction requests until idle.

    Args:
        client: A client that is about to be used (not yet entered is fine).
        allow: When True, grant permissions with ``once``; otherwise reject them.
        model: Optional ``{"providerID": ..., "modelID": ...}`` for the prompt.
    """
    session = await client.sessions.create()
    decoder = SSEDecoder()
    idle = asyncio.Event()
    answered = 0

    async def watch() -> None:
        """Track the event stream; signal when the session goes idle."""
        async with client.server.stream_events() as stream:
            async for event in decoder.aiter_events(stream.aiter_lines()):
                label = "interaction" if event.type in ("permission.updated", "question.updated") else "event"
                print(f"[{label}] {event.type}")
                if event.type == "session.idle" and event.properties.get("sessionID") == session.id:
                    idle.set()
                    return

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0.5)  # let the stream attach before the turn starts
    await client.sessions.prompt_async(session.id, "List the files in the current directory.", model=model)

    try:
        idle_task = asyncio.create_task(idle.wait())
        deadline = asyncio.create_task(asyncio.sleep(MAX_WAIT_SECONDS))
        # Keep answering anything pending until the session reports idle (or timeout).
        while not idle.is_set():
            for perm in await client.server.list_permissions():
                decision = "once" if allow else "reject"
                print(f"permission {perm.id} ({perm.permission}: {', '.join(perm.patterns)}) -> {decision}")
                await client.server.reply_permission(perm.id, decision)
                answered += 1
            for question in await client.server.list_questions():
                options = question.questions[0].options
                answers = [[options[0].label]] if options else [[""]]
                print(f"question {question.id}: {question.questions[0].question!r} -> {answers}")
                await client.server.reply_question(question.id, answers)
                answered += 1
            done, _ = await asyncio.wait(
                {idle_task, deadline}, timeout=POLL_SECONDS, return_when=asyncio.FIRST_COMPLETED
            )
            if deadline in done and not idle.is_set():
                print("timed out waiting for session.idle")
                return
    finally:
        watcher.cancel()
        await client.sessions.delete(session.id)

    print(f"turn finished; answered {answered} interaction(s)")


def cli() -> None:
    """Parse CLI arguments and run :func:`answer_pending`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:4096")
    parser.add_argument("--allow", action="store_true", help="auto-approve tool permissions")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    model = {"providerID": args.provider, "modelID": args.model} if args.provider and args.model else None
    asyncio.run(answer_pending(AsyncOpenCodeClient(args.url), allow=args.allow, model=model))


if __name__ == "__main__":
    cli()
