"""support/memory.py — Stage 8 (R-1, R-2, R-4).

Memory as pipeline code, not a tool: the model decides what to say, never whether the
system remembers (SPEC §6). `recall` searches Mem0 for this user before the agent runs and
decides which candidates to insert; `save` stores only the user's own message afterwards.
The cutoffs are the THRESHOLDS numbers (T-MEM-TOPK, T-MEM-MINSCORE, T-MEM-MAXCHARS); every
candidate is reported with its score and whether it was inserted so the step can list them (R-5).
"""
import os

from mem0 import MemoryClient

TOPK = 5          # T-MEM-TOPK
MINSCORE = 0.25   # T-MEM-MINSCORE
MAXCHARS = 500    # T-MEM-MAXCHARS
HEADER = "Relevant memories about this customer (from Mem0):"

_client = None


def _get_client() -> MemoryClient:
    global _client
    if _client is None:
        _client = MemoryClient(api_key=os.environ["MEM0_API_KEY"])
    return _client


def _rows(result) -> list:
    """Mem0's hosted search returns either a list or {'results': [...]}; normalise to a list."""
    if isinstance(result, dict):
        return result.get("results", [])
    return result or []


def recall(user_email: str, message: str) -> list[dict]:
    """Search Mem0 for this user and classify each candidate. Returns the §7.1 `memories` list.

    Each item: {memory, score, inserted, reason}. inserted only when score >= MINSCORE and
    length <= MAXCHARS (R-2); everything else is reported skipped with the reason."""
    hits = _rows(_get_client().search(
        message, version="v2", filters={"user_id": user_email}, limit=TOPK))
    out = []
    for h in hits:
        text = h.get("memory", "")
        score = h.get("score") or 0.0
        if score < MINSCORE:
            inserted, reason = False, "below cutoff"
        elif len(text) > MAXCHARS:
            inserted, reason = False, "too long"
        else:
            inserted, reason = True, None
        out.append({"memory": text, "score": round(float(score), 4), "inserted": inserted, "reason": reason})
    return out


def build_input(message: str, memories: list[dict]) -> str:
    """Prepend inserted memories under the fixed header, above the user's message (R-3)."""
    inserted = [m["memory"] for m in memories if m["inserted"]]
    if not inserted:
        return message
    lines = "\n".join(f"- {m}" for m in inserted)
    return f"{HEADER}\n{lines}\n\n{message}"


def save(user_email: str, message: str) -> None:
    """Save only the user's own message, filtered to that user (R-4). Never the agent's reply."""
    _get_client().add(message, user_id=user_email)
