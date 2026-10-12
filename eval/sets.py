"""eval/sets.py — run the gold sets and gather each turn's evidence (EVALS §3).

Simple sets are one turn per item. The memory set runs batched with one shared T-MEM-WAIT
(the Stage 10 decision): plant every pair, wait once, then ask every pair — Mem0 extracts
asynchronously, so asking sooner measures the queue, not the memory. The action set snapshots
customer_orders before and after so the mutation check (T-MUTATE) has before/after evidence.
"""
import time

from eval import gold
from eval.db import snapshot_orders
from eval.drive import drive_turn, terminal

MEM_WAIT = 120  # T-MEM-WAIT: Mem0's async extraction returns PENDING before this
PACE = 1.0      # seconds between turns: keeps the run under Gemini's per-minute rate limit so
                # calls don't get throttled/queued. Sleeps AFTER the measured turn, so it never
                # counts toward wall_clock_ms, T-LAT-* or T-BUD-WALL — it only protects the next turn.


def _gather(item: dict, message: str) -> dict:
    events, run_log = drive_turn(item["user"], message)
    time.sleep(PACE)
    trace_id = next((e["trace_id"] for e in events if e.get("type") == "trace"), None)
    return {**item, "events": events, "run_log": run_log, "terminal": terminal(events),
            "trace_id": trace_id, "ms": (run_log or {}).get("wall_clock_ms")}


def run_simple(name: str) -> list[dict]:
    """attack / legit / offtopic / probe / order — one message turn per item."""
    return [_gather(it, it["message"]) for it in gold.load(name)]


def run_action() -> tuple[list[dict], str, str]:
    """Action set, with a customer_orders snapshot before and after (EVALS §3.6)."""
    before = snapshot_orders()
    results = [_gather(it, it["message"]) for it in gold.load("action")]
    after = snapshot_orders()
    return results, before, after


def run_memory() -> list[dict]:
    """Memory pairs, batched: plant all, wait once, ask all (EVALS §3.7). Mem0 must already
    be cleared for these users by the reset. Each result carries the ask turn's recall step."""
    pairs = gold.load("memory")
    for p in pairs:
        drive_turn(p["user"], p["plant"])
    time.sleep(MEM_WAIT)
    results = []
    for p in pairs:
        r = _gather(p, p["ask"])
        r["recall"] = next((e for e in r["events"]
                            if e.get("type") == "step" and e.get("key") == "recall"), None)
        results.append(r)
    return results
