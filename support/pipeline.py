"""support/pipeline.py — Stage 4 (P-1, agent slice of P-2) + Stage 5 (O-2, O-4).

The turn, as an async generator that yields the SPEC §7.1 events; front ends only
render what it yields (P-1). The whole turn runs inside one root `agent.turn` span
(CHAIN) so ADK's auto `invoke_agent → call_llm → execute_tool` spans nest under it
(O-2); the `trace` event carries that span's real trace id and a Phoenix URL (O-4).
It writes runs/<turn_id>.json (EVALS §4.1) before the terminal event. The guard
stages (sanitize…save) arrive in later stages.
"""
import json
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

from google.genai import types
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import context as context_api
from opentelemetry import trace as otel_trace
from opentelemetry.trace import Status, StatusCode

from support import telemetry
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
    t0 = time.monotonic()

    # Open the root span and make it current, so ADK's auto-spans nest under it (O-2).
    tracer = telemetry.setup()
    span = tracer.start_span("agent.turn")
    span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.CHAIN.value)
    span.set_attribute(SpanAttributes.INPUT_VALUE, message)
    span.set_attribute(SpanAttributes.USER_ID, user_email)
    ctx_token = context_api.attach(otel_trace.set_span_in_context(span))
    trace_id = format(span.get_span_context().trace_id, "032x")

    tokens_in = tokens_out = llm_calls = 0
    tool_calls_log: list[dict] = []
    pending: dict[str, list[tuple[int, float]]] = {}
    next_id = 1
    response_text = ""
    terminated, err = "done", None

    try:
        yield {"type": "trace", "turn_id": turn_id, "trace_id": trace_id,
               "url": telemetry.trace_url(trace_id)}
        yield {"type": "stage", "key": "agent", "label": "Support agent"}

        content = types.Content(role="user", parts=[types.Part(text=message)])
        last = time.monotonic()
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
        span.record_exception(e)
        span.set_status(Status(StatusCode.ERROR, err))

    wall = int((time.monotonic() - t0) * 1000)
    span.set_attribute(SpanAttributes.OUTPUT_VALUE, err if terminated == "error" else response_text)
    _write_run({"turn_id": turn_id, "trace_id": trace_id, "user": user_email, "message": message,
                "terminated": terminated, "blocked_at": None, "wall_clock_ms": wall,
                "tokens": {"in": tokens_in, "out": tokens_out}, "steps": [],
                "tool_calls": tool_calls_log, "llm_calls": llm_calls})

    # Close the root span and ship it so the printed URL opens a complete trace right away.
    context_api.detach(ctx_token)
    span.end()
    telemetry.flush()

    if terminated == "error":
        yield {"type": "error", "step": "agent", "status": 500, "error": err, "terminated": "error"}
    else:
        yield {"type": "final", "blocked": False, "blocked_at": None, "response": response_text,
               "terminated": "done", "wall_clock_ms": wall, "tokens": {"in": tokens_in, "out": tokens_out}}
