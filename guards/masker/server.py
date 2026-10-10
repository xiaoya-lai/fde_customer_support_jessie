"""guards/masker/server.py — Stage 8 (K-1, K-3).

The Masker as its own A2A process, like the Judge: an agent card at /.well-known/agent.json
and a JSON-RPC `message/send` endpoint. It is called with the agent's final reply text and
the caller's own email (so that email is left alone, K-2); it returns the masked text, a count
of what it changed, and a human detail line (K-3). It is a pure transform — it never blocks.
"""
import os

from fastapi import FastAPI, Request

from guards.masker.mask import describe, mask_text

PORT = int(os.environ.get("MASKER_PORT", "10003"))

app = FastAPI()

AGENT_CARD = {
    "name": "Data Masker",
    "description": "Masks PII (other people's emails, phone numbers, card-like numbers) in a reply.",
    "url": f"http://localhost:{PORT}/",
    "version": "1.0.0",
    "capabilities": {"streaming": False},
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
    "skills": [{"id": "mask", "name": "mask",
                "description": "Return masked text and a count of PII changed.", "tags": ["security", "pii"]}],
}


@app.get("/.well-known/agent.json")
@app.get("/.well-known/agent-card.json")
def agent_card():
    return AGENT_CARD


def _text(params: dict) -> str:
    parts = params.get("message", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


@app.post("/")
async def rpc(req: Request):
    body = await req.json()
    rid = body.get("id")
    if body.get("method") != "message/send":
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}
    params = body.get("params", {})
    text = _text(params)
    own_email = (params.get("metadata") or {}).get("user_email")
    masked, counts = mask_text(text, own_email)
    return {"jsonrpc": "2.0", "id": rid,
            "result": {"masked": masked, "counts": counts, "detail": describe(counts)}}
