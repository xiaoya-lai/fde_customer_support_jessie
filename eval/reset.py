"""eval/reset.py — the fixed starting state before an eval run (EVALS §2, §3.7).

`reset_db()` drops, recreates and reseeds Postgres through run.sh so every run starts from
the same rows and the same SERIAL ids. `clear_memories()` wipes Mem0 for the memory-pair
users so T-MEM-RECALL measures the facts this run plants, not leftovers from a prior one.
"""
import subprocess
from pathlib import Path

from eval.gold import memory_users
from support import memory

ROOT = Path(__file__).resolve().parent.parent


def reset_db() -> None:
    subprocess.run(["./run.sh", "reset"], cwd=str(ROOT), check=True)


def clear_memories(users: list[str] | None = None) -> None:
    for user in users or memory_users():
        try:
            memory.clear(user)
            print(f"  cleared Mem0 for {user}")
        except Exception as e:  # a stale account that no longer exists is not fatal
            print(f"  WARN: Mem0 clear failed for {user}: {e}")
