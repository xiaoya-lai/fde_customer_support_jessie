"""eval/drive.py — run one gold turn and collect its evidence.

Drives the CLI subprocess (`--user <email> --events`) so each turn goes through the exact
pipeline a real user hits (P-1), parses the §7.1 NDJSON stream, and loads the
runs/<turn_id>.json log the pipeline wrote (EVALS §4.1 — the runner reads it, never
reconstructs it). Returns (events, run_log); `terminal()` picks the turn's final/error event.
"""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")
RUNS = ROOT / "runs"
TURN_TIMEOUT = 90  # T-BUD-WALL is 30s; 90 leaves headroom for a slow four-layer tail


def drive_turn(email: str, message: str, timeout: int = TURN_TIMEOUT) -> tuple[list[dict], dict | None]:
    proc = subprocess.run(
        [PY, "-m", "support.cli", "--user", email, "--events"],
        input=message + "\n", capture_output=True, text=True,
        cwd=str(ROOT), timeout=timeout,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    events: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # the CLI prints only NDJSON under --events; ignore any stray line
    turn_id = next((e["turn_id"] for e in events if e.get("type") == "trace"), None)
    run_log = None
    if turn_id:
        path = RUNS / f"{turn_id}.json"
        if path.exists():
            run_log = json.loads(path.read_text())
    return events, run_log


def terminal(events: list[dict]) -> dict | None:
    """The turn's terminal event — the last `final` or `error` in the stream."""
    for ev in reversed(events):
        if ev.get("type") in ("final", "error"):
            return ev
    return None
