"""support/cli.py — Stage 3 (throwaway CLI).

A bare login-and-chat loop: it verifies credentials against the users table through
the Toolbox verify-login tool (so no SQL lives in Python, M-2), binds the session
email to the agent's tools via a callable (M-5), and runs one ADK session per
logged-in user. Stage 4 replaces this with the pipeline + event renderer.
"""
import asyncio
import getpass
import json
import os

from dotenv import load_dotenv
from toolbox_core import ToolboxClient
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from support.agent import build_agent, current_email, set_session_email

load_dotenv()
TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5050")
APP = "support"


def _rows(result):
    """Normalize a Toolbox result (JSON string of an object or array) to a list of rows."""
    data = json.loads(result) if isinstance(result, str) else result
    if isinstance(data, dict):
        return [data]
    return data or []


async def main() -> None:
    async with ToolboxClient(TOOLBOX_URL) as toolbox:
        login_tool = await toolbox.load_tool("verify-login")
        tools = await toolbox.load_toolset(
            "support-agent",
            bound_params={"customer_email": current_email, "user_email": current_email},
            strict=False,
        )

        email = input("email: ").strip()
        password = getpass.getpass("password: ")
        rows = _rows(await login_tool(email=email, password=password))
        if not rows:
            print("Invalid email or password.")
            return
        set_session_email(email)
        print(f"Logged in as {rows[0].get('full_name') or email}. Type 'quit' to exit.\n")

        agent = build_agent(tools)
        sessions = InMemorySessionService()
        await sessions.create_session(app_name=APP, user_id=email, session_id=email)
        runner = Runner(agent=agent, app_name=APP, session_service=sessions)

        while True:
            msg = input("You: ").strip()
            if msg.lower() in {"quit", "exit", "q"}:
                break
            if not msg:
                continue
            content = types.Content(role="user", parts=[types.Part(text=msg)])
            async for event in runner.run_async(user_id=email, session_id=email, new_message=content):
                if event.is_final_response() and event.content and event.content.parts:
                    print("Bot:", event.content.parts[0].text, "\n")


if __name__ == "__main__":
    asyncio.run(main())
