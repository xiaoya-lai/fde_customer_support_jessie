"""support/pipeline.py — Stage 4 (P-1, and the agent slice of P-2).

The turn, as an async generator that yields the SPEC §7.1 events; front ends only
render what it yields (P-1). Stage 4 covers the agent path only — trace (placeholder
id until Stage 5), the agent stage, llm/tool_call/tool_result read off ADK's events,
then the terminal final/error — and writes runs/<turn_id>.json (EVALS §4.1) before
the terminal event. The guard stages (sanitize…save) arrive in later stages.
"""
import json
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

from google.genai import types

from support.agent import MODEL, set_session_email

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


def _decode(value):
    """Decode a tool payload that may be a JSON string and/or {'result': <str>}-wrapped."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    if isinstance(value, dict) and set(value) == {"result"}:
        return _decode(value["result"])
    return value


def _write_run(doc: dict) -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    (RUNS_DIR / f"{doc['turn_id']}.json").write_text(json.dumps(doc, indent=2))


async def run_turn(*, runner, user_email: str, session_id: str, message: str) -> AsyncIterator[dict]:
    set_session_email(user_email)  # bind this turn's identity for the tools (M-5)
    turn_id = "turn_" + uuid.uuid4().hex
    trace_id = "0" * 32  # placeholder; the real trace id is wired in Stage 5
    t0 = time.monotonic()

    yield {"type": "trace", "turn_id": turn_id, "trace_id": trace_id,
           "url": "http://localhost:6006 (real trace id in Stage 5)"}
    yield {"type": "stage", "key": "agent", "label": "Support agent"}

    tokens_in = tokens_out = llm_calls = 0
    tool_calls_log: list[dict] = []
    pending: dict[str, list[tuple[int, float]]] = {}
    next_id = 1
    response_text = ""
    terminated, err = "done", None

    content = types.Content(role="user", parts=[types.Part(text=message)])
    last = time.monotonic()
    try:
        async for ev in runner.run_async(user_id=user_email, session_id=session_id, new_message=content):
            now = time.monotonic()
            um = getattr(ev, "usage_metadata", None)
            ti = (getattr(um, "prompt_token_count", 0) or 0) if um else 0
            to = (getattr(um, "candidates_token_count", 0) or 0) if um else 0

            fcalls = ev.get_function_calls()
            if fcalls:
                llm_calls += 1
                tokens_in += ti
                tokens_out += to
                yield {"type": "llm", "model": MODEL,
                       "decision": "call " + ", ".join(c.name for c in fcalls),
                       "tokens_in": ti, "tokens_out": to, "ms": int((now - last) * 1000), "span": "call_llm"}
                for c in fcalls:
                    cid, next_id = next_id, next_id + 1
                    pending.setdefault(c.name, []).append((cid, now))
                    yield {"type": "tool_call", "id": cid, "name": c.name,
                           "args": {k: _decode(v) for k, v in dict(c.args).items()},
                           "info": {"kind": "MCP", "access": "WRITE" if c.name == "action-log" else "READ"},
                           "span": f"execute_tool {c.name}"}

            for r in ev.get_function_responses():
                queue = pending.get(r.name) or [(None, now)]
                cid, start = queue.pop(0)
                result = _decode(r.response)
                ok = not (isinstance(result, dict) and "error" in result)
                ms = int((now - start) * 1000)
                yield {"type": "tool_result", "id": cid, "name": r.name, "ok": ok, "ms": ms, "result": result}
                entry = {"name": r.name, "ok": ok, "ms": ms}
                if not ok:
                    entry["error"] = str(result)
                tool_calls_log.append(entry)

            if ev.is_final_response():
                llm_calls += 1
                tokens_in += ti
                tokens_out += to
                if ev.content and ev.content.parts and ev.content.parts[0].text:
                    response_text = ev.content.parts[0].text
                yield {"type": "llm", "model": MODEL, "decision": "final answer",
                       "tokens_in": ti, "tokens_out": to, "ms": int((now - last) * 1000), "span": "call_llm"}
            last = now
    except Exception as e:  # fail loud: an agent-side failure ends the turn as an error (R-4)
        terminated, err = "error", f"{type(e).__name__}: {e}"

    wall = int((time.monotonic() - t0) * 1000)
    _write_run({"turn_id": turn_id, "trace_id": trace_id, "user": user_email, "message": message,
                "terminated": terminated, "blocked_at": None, "wall_clock_ms": wall,
                "tokens": {"in": tokens_in, "out": tokens_out}, "steps": [],
                "tool_calls": tool_calls_log, "llm_calls": llm_calls})

    if terminated == "error":
        yield {"type": "error", "step": "agent", "status": 500, "error": err, "terminated": "error"}
    else:
        yield {"type": "final", "blocked": False, "blocked_at": None, "response": response_text,
               "terminated": "done", "wall_clock_ms": wall, "tokens": {"in": tokens_in, "out": tokens_out}}
