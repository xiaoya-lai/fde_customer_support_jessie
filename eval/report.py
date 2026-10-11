"""eval/report.py — assemble and write reports/eval.json (EVALS §4.2).

Written only by the runner, never by hand: a number no run produced is a red line. Formats
each THRESHOLDS row for the report, computes the four red-line booleans from the repo and the
run, and serialises the whole thing. Lives apart from the gates so run.py stays the gate list.
"""
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
RUNS = ROOT / "runs"
FAILING = RUNS / "failing"
TOOLS_YAML = ROOT / "mcp_toolbox" / "tools.yaml"

_OP = {"ge": ">=", "le": "<=", "eq": "=="}


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(ROOT),
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def secret_in_repo() -> bool:
    return ".env" in _git("ls-files").split()


def mutating_tool_loaded() -> bool:
    """A tool whose SQL writes customer_orders would violate M-6; none should exist."""
    if not TOOLS_YAML.exists():
        return False
    return bool(re.search(r"(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+customer_orders",
                          TOOLS_YAML.read_text(), re.I))


def failing_answered() -> bool:
    """Fail-loud violation (R-4): a runs/failing/ turn that answered instead of ending error."""
    if not FAILING.exists():
        return False
    for p in FAILING.glob("*.json"):
        try:
            if json.loads(p.read_text()).get("terminated") != "error":
                return True
        except Exception:
            pass
    return False


def build(rows: list[dict], items: list[dict], trajectories: dict,
          model: str, leak_value) -> dict:
    metrics = {r["id"]: {"value": r["value"], "target": f'{_OP[r["op"]]} {r["target"]}',
                         "n": r["n"], "pass": r["pass"]} for r in rows}
    return {
        "assignment": "Assignment 3: Customer Support",
        "commit": _git("rev-parse", "--short", "HEAD") or None,
        "ran_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "metrics": metrics,
        "items": items,
        "red_lines": {
            "secret_in_repo": secret_in_repo(),
            "mutating_tool_loaded": mutating_tool_loaded(),
            "leak": leak_value > 0,
            "silent_fail_open": failing_answered(),
        },
        "trajectories": trajectories,
    }


def write(report: dict) -> Path:
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / "eval.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    return path
