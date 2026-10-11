"""eval/gold.py — load the frozen gold sets the runner measures against (EVALS §3).

The seven .jsonl files under gold/ are transcribed verbatim from EVALS and never edited;
this is the only reader. `memory_users()` derives the memory-pair users from the data so
the eval reset clears exactly those Mem0 accounts (EVALS §3.7) with no second hard-coded list.
"""
import json
from pathlib import Path

GOLD_DIR = Path(__file__).resolve().parent / "gold"
SETS = ["attack", "legit", "offtopic", "probe", "order", "action", "memory"]


def load(name: str) -> list[dict]:
    path = GOLD_DIR / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def memory_users() -> list[str]:
    return sorted({item["user"] for item in load("memory")})
