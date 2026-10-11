"""eval/observe.py — the observability metrics (THRESHOLDS §5, SPEC §7.3 & §10).

T-TRACE-ONE and T-TRACE-SHAPE read spans from the Phoenix "support" project over HTTP and
match them to each turn by trace id. T-EVENT-ORDER is a pure check over the turn's event
stream (the same stream the CLI and web render), enforcing the six ordering rules in §7.3.
Spans export asynchronously, so the caller waits before fetching.
"""
import httpx

from eval.metrics import _row

PHOENIX_URL = "http://localhost:6006"
PROJECT = "support"
# SPEC §10 required-span list; invoke_agent is matched by prefix (ADK names it per agent).
REQUIRED = {"agent.turn", "security.sanitize", "security.a2a_judge", "guardrail.check",
            "memory.recall", "security.a2a_mask", "memory.save"}
_STAGE_ORDER = ["sanitize", "judge", "guardrail", "recall", "agent", "mask", "save"]


def _project_id() -> str:
    data = httpx.get(f"{PHOENIX_URL}/v1/projects", timeout=10).json()["data"]
    for p in data:
        if p["name"] == PROJECT:
            return p["id"]
    raise RuntimeError(f"Phoenix project {PROJECT!r} not found; have {[p['name'] for p in data]}")


def fetch_spans() -> list[dict]:
    pid = _project_id()
    spans, cursor = [], None
    while True:
        params = {"limit": 1000, **({"cursor": cursor} if cursor else {})}
        page = httpx.get(f"{PHOENIX_URL}/v1/projects/{pid}/spans", params=params, timeout=30).json()
        spans.extend(page.get("data", []))
        cursor = page.get("next_cursor")
        if not cursor:
            return spans


def _by_trace(spans: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for s in spans:
        out.setdefault(s.get("context", {}).get("trace_id"), []).append(s)
    return out


def _check_order(events: list[dict]) -> list[str]:
    """Rules 1-6 of SPEC §7.3; returns the ids of any rules the stream broke."""
    errs = []
    if not events or events[0].get("type") != "trace":
        errs.append("rule1-trace-first")
    terms = [i for i, e in enumerate(events) if e.get("type") in ("final", "error")]
    if len(terms) != 1 or terms[-1] != len(events) - 1:
        errs.append("rule5-one-terminal-last")
    res_ids = [e.get("id") for e in events if e.get("type") == "tool_result"]
    for c in (e for e in events if e.get("type") == "tool_call"):
        if res_ids.count(c.get("id")) != 1:
            errs.append(f"rule3-tool-pair-{c.get('id')}")
    for i, e in enumerate(events):
        if e.get("type") == "step" and e.get("status") == "blocked":
            nxt = events[i + 1] if i + 1 < len(events) else None
            if not (nxt and nxt.get("type") == "final" and nxt.get("blocked")
                    and nxt.get("blocked_at") == e.get("key")):
                errs.append("rule4-blocked-then-final")
    last = events[-1] if events else {}
    blocked_or_err = last.get("type") == "error" or (last.get("type") == "final" and last.get("blocked"))
    if blocked_or_err and any(e.get("type") == "step" and e.get("key") == "save" for e in events):
        errs.append("rule6-no-save-on-block")
    stage_idx = [i for i, e in enumerate(events) if e.get("type") == "stage"]
    canon = [_STAGE_ORDER.index(events[i]["key"]) for i in stage_idx
             if events[i]["key"] in _STAGE_ORDER]
    if canon != sorted(canon):
        errs.append("rule2-stage-order")
    for n, i in enumerate(stage_idx):
        key = events[i]["key"]
        if key == "agent":  # §7.3 rule 2: llm/tool_* events sit between agent and mask
            continue
        end = stage_idx[n + 1] if n + 1 < len(stage_idx) else len(events)
        if not any(e.get("type") == "step" and e.get("key") == key for e in events[i + 1:end]):
            errs.append(f"rule2-missing-step-{key}")
    return errs


def score(results: list[dict]) -> tuple[list[dict], list[dict]]:
    traces = _by_trace(fetch_spans())
    items = []
    for r in results:
        spans = traces.get(r.get("trace_id"), [])
        names = {s["name"] for s in spans}
        roots = sum(1 for s in spans if s["name"] == "agent.turn" and not s.get("parent_id"))
        passing = (r.get("terminal") or {}).get("terminated") == "done"
        shape_ok = REQUIRED <= names and any(n.startswith("invoke_agent") for n in names)
        items.append({"id": r["id"], "roots": roots, "passing": passing,
                      "shape_ok": shape_ok if passing else None,
                      "order_errs": _check_order(r["events"]), "n_spans": len(spans)})
    n = len(items)
    passed = [i for i in items if i["passing"]]
    rows = [
        _row("T-TRACE-ONE", sum(i["roots"] == 1 for i in items) / n, 1.0, "eq", n),
        _row("T-TRACE-SHAPE",
             (sum(i["shape_ok"] for i in passed) / len(passed)) if passed else 1.0, 1.0, "eq", len(passed)),
        _row("T-EVENT-ORDER", sum(not i["order_errs"] for i in items) / n, 1.0, "eq", n),
    ]
    return rows, items
