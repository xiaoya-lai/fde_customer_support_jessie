"""support/cli.py — Stage 4 (C-3).

A thin front end: it logs in, then for each message drives support.pipeline.run_turn
and only renders the events it yields (P-1). --events prints the raw §7.1 NDJSON
with no rendering (for jq and the eval runner); otherwise it prints the symbol+compact
human lines. --user <email> is a local/eval shortcut that skips the password prompt.
"""
import argparse
import asyncio
import getpass
import json
import os
import sys

from dotenv import load_dotenv
from toolbox_core import ToolboxClient
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from support import telemetry
from support.agent import build_agent, current_email
from support.pipeline import run_turn

load_dotenv()
TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5050")
APP = "support"


def _rows(result):
    data = json.loads(result) if isinstance(result, str) else result
    if isinstance(data, dict):
        return [data]
    return data or []


def _render(ev: dict) -> None:
    t = ev["type"]
    if t == "trace":
        print(f"  turn {ev['turn_id']}  ·  trace {ev['url']}")
    elif t == "stage":
        print(f"» {ev['label']}")
    elif t == "step":
        mark = "✓" if ev["status"] == "passed" else "✗"
        print(f"{mark} {ev['key']:<9} {ev['status']} · {ev['detail']} · {ev['ms']}ms · {ev['span']}")
        for m in ev.get("memories", []):
            tag = "inserted" if m["inserted"] else f"skipped ({m['reason']})"
            print(f"    · {m['score']:>6}  {tag}  {m['memory']}")
    elif t == "llm":
        print(f"→ llm         {ev['decision']}   ({ev['ms']}ms, {ev['tokens_out']} tok)")
    elif t == "tool_call":
        args = ", ".join(f"{k}={v}" for k, v in ev["args"].items())
        print(f"→ tool        {ev['name']}  {{{args}}}")
    elif t == "tool_result":
        mark = "✓" if ev["ok"] else "✗"
        n = len(ev["result"]) if isinstance(ev["result"], list) else 1
        print(f"{mark} tool        {ev['name']}  {n} row(s)   {ev['ms']}ms")
    elif t == "final":
        tag = f"[blocked at {ev['blocked_at']}] " if ev["blocked"] else ""
        print(f"\nBot: {tag}{ev['response']}\n")
    elif t == "error":
        print(f"✗ error       [{ev['step']}] {ev['error']}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", help="log in as this email without a password (local/eval only)")
    ap.add_argument("--events", action="store_true", help="print raw §7.1 NDJSON, no rendering")
    args = ap.parse_args()

    telemetry.setup()  # install the global TracerProvider before any agent is built (O-2)

    async with ToolboxClient(TOOLBOX_URL) as toolbox:
        login_tool = await toolbox.load_tool("verify-login")
        tools = await toolbox.load_toolset(
            "support-agent",
            bound_params={"customer_email": current_email, "user_email": current_email},
            strict=False,
        )

        if args.user:
            email = args.user
        else:
            email = input("email: ").strip()
            password = getpass.getpass("password: ")
            if not _rows(await login_tool(email=email, password=password)):
                print("Invalid email or password.")
                return
            if not args.events:
                print(f"Logged in as {email}. Type 'quit' to exit.\n")

        agent = build_agent(tools)
        sessions = InMemorySessionService()
        await sessions.create_session(app_name=APP, user_id=email, session_id=email)
        runner = Runner(agent=agent, app_name=APP, session_service=sessions)

        async def handle(msg: str) -> None:
            async for ev in run_turn(runner=runner, user_email=email, session_id=email, message=msg):
                print(json.dumps(ev), flush=True) if args.events else _render(ev)

        if not sys.stdin.isatty():
            for line in sys.stdin:
                line = line.strip()
                if line:
                    await handle(line)
        else:
            while True:
                try:
                    msg = input("You: ").strip()
                except EOFError:
                    break
                if msg.lower() in {"quit", "exit", "q"}:
                    break
                if msg:
                    await handle(msg)


if __name__ == "__main__":
    asyncio.run(main())
