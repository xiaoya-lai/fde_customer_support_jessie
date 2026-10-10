"""support/web.py — Stage 9 (W-1, W-2).

A FastAPI front end that is a thin renderer, like the CLI: it serves the §7.2 API and a
single-page UI at `/`, and `POST /api/chat` streams the exact §7.1 events as
`application/x-ndjson` by iterating the same `run_turn` generator the CLI uses (P-1, W-2).
Login verifies against the `verify-login` tool and creates one in-memory session per user;
`/api/chat` validates (empty, not-logged-in, too-long) before it begins streaming (§7.2).
"""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from toolbox_core import ToolboxClient

from guards.sanitizer import MAX_LEN
from support import telemetry
from support.agent import build_agent, current_email
from support.pipeline import JUDGE_URL, MASKER_URL, run_turn
from support.telemetry import PHOENIX_URL

load_dotenv()
TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5050")
APP = "support"
INDEX = (Path(__file__).resolve().parent / "index.html").read_text()

_state: dict = {}
_logged_in: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    telemetry.setup()
    async with ToolboxClient(TOOLBOX_URL) as toolbox:
        _state["login"] = await toolbox.load_tool("verify-login")
        tools = await toolbox.load_toolset(
            "support-agent",
            bound_params={"customer_email": current_email, "user_email": current_email},
            strict=False,
        )
        _state["sessions"] = InMemorySessionService()
        _state["runner"] = Runner(agent=build_agent(tools), app_name=APP, session_service=_state["sessions"])
        yield


app = FastAPI(lifespan=lifespan)


def _rows(result):
    data = json.loads(result) if isinstance(result, str) else result
    if isinstance(data, dict):
        return [data]
    return data or []


@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX


@app.post("/api/login")
async def login(req: Request):
    body = await req.json()
    rows = _rows(await _state["login"](email=body.get("email", ""), password=body.get("password", "")))
    if not rows:
        return JSONResponse({"error": "Invalid email or password."}, status_code=401)
    row = rows[0]
    email = row["email"]
    if await _state["sessions"].get_session(app_name=APP, user_id=email, session_id=email) is None:
        await _state["sessions"].create_session(app_name=APP, user_id=email, session_id=email)
    _logged_in.add(email)
    return {"user_id": email, "full_name": row.get("full_name"),
            "is_premium": bool(row.get("is_premium_customer"))}


@app.post("/api/logout")
async def logout(req: Request):
    body = await req.json()
    _logged_in.discard(body.get("user_id", ""))
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    user_id = body.get("user_id", "")
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "message is empty"}, status_code=400)
    if user_id not in _logged_in:
        return JSONResponse({"error": "Not logged in."}, status_code=401)
    if len(message) > MAX_LEN:
        return JSONResponse({"error": "message too long"}, status_code=413)

    async def stream():
        async for ev in run_turn(runner=_state["runner"], user_email=user_id,
                                 session_id=user_id, message=message):
            yield json.dumps(ev) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.get("/health")
async def health():
    checks = {"status": "ok", "model": os.environ.get("MODEL", "gemini-3-flash-preview")}
    probes = {"toolbox": f"{TOOLBOX_URL}/", "judge": f"{JUDGE_URL}/.well-known/agent.json",
              "masker": f"{MASKER_URL}/.well-known/agent.json", "phoenix": f"{PHOENIX_URL}/"}
    ok = True
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, url in probes.items():
            try:
                await client.get(url)
                checks[name] = "ok"
            except Exception as e:
                checks[name] = f"{type(e).__name__}: {e}"
                ok = False
    checks["db"] = "ok" if checks.get("toolbox") == "ok" else "unknown (toolbox down)"
    checks["mem0"] = "ok" if os.environ.get("MEM0_API_KEY") else "no key"
    if not ok:
        checks["status"] = "degraded"
        return JSONResponse(checks, status_code=503)
    return checks
