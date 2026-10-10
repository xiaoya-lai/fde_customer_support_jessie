"""guards/judge/server.py — Stage 6 (J-1, J-3, J-4).

The Judge as its own process: an A2A agent card at /.well-known/agent.json and a
JSON-RPC `message/send` endpoint (the current A2A method; recorded in DESIGN.md).
Decision A: patterns are checked first and block on their own without a model call
(cheap, protects T-LAT-BLOCK-P95); only a message with no pattern match reaches the
model. The reply is always an explicit {verdict, reason} (J-3); an output that cannot
be parsed into allow|block becomes a JSON-RPC error the pipeline treats as a failure (J-4).
"""
import json
import os
import re
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from guards.judge.agent import build_judge_agent
from guards.judge.patterns import scan

load_dotenv()
PORT = int(os.environ.get("JUDGE_PORT", "10002"))
APP = "judge"

app = FastAPI()
_agent = build_judge_agent()
_sessions = InMemorySessionService()
_runner = Runner(agent=_agent, app_name=APP, session_service=_sessions)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

AGENT_CARD = {
    "name": "Security Judge",
    "description": "Classifies a customer-support message as allow or block (injection / prompt-extraction).",
    "url": f"http://localhost:{PORT}/",
    "version": "1.0.0",
    "capabilities": {"streaming": False},
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
    "skills": [{"id": "judge", "name": "judge",
                "description": "Return {verdict, reason} for a user message.", "tags": ["security"]}],
}


@app.get("/.well-known/agent.json")
@app.get("/.well-known/agent-card.json")
def agent_card():
    return AGENT_CARD


def _text(params: dict) -> str:
    parts = params.get("message", {}).get("parts", [])
    return " ".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()


async def _model_verdict(text: str) -> dict:
    """Run the ADK Judge agent on a message with no deterministic match, and parse its verdict."""
    sid = "judge_" + uuid.uuid4().hex
    await _sessions.create_session(app_name=APP, user_id="judge", session_id=sid)
    out = ""
    content = types.Content(role="user", parts=[types.Part(text=text)])
    async for ev in _runner.run_async(user_id="judge", session_id=sid, new_message=content):
        if ev.is_final_response() and ev.content and ev.content.parts and ev.content.parts[0].text:
            out = ev.content.parts[0].text
    await _sessions.delete_session(app_name=APP, user_id="judge", session_id=sid)
    m = _JSON_RE.search(out)
    if not m:
        raise ValueError(f"unparseable judge output: {out!r}")
    data = json.loads(m.group(0))
    if data.get("verdict") not in ("allow", "block"):
        raise ValueError(f"invalid verdict: {data!r}")
    return {"verdict": data["verdict"], "reason": data.get("reason", "")}


@app.post("/")
async def rpc(req: Request):
    body = await req.json()
    rid = body.get("id")
    if body.get("method") != "message/send":
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}
    text = _text(body.get("params", {}))
    hit = scan(text)
    if hit:  # patterns first — a match blocks alone, no model call (decision A)
        result = {"verdict": "block", "reason": f"pattern: {hit.category} ({hit.snippet!r})"}
    else:
        try:
            result = await _model_verdict(text)
        except Exception as e:  # fail loud: an unparseable verdict is an error, never a pass (J-4)
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(e)}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}
