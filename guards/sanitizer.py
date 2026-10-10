"""guards/sanitizer.py — Stage 6 (S-1, S-2).

The first guard: in-process, no model call. A length cap, a printable-character
allow-list, and the cheapest obvious reject (control / non-printable bytes). It must
let ordinary punctuation through — apostrophes, # $ : ; @ and the rest — so a real
customer is never blocked here (S-2 / T-LEGIT-FALSE-BLOCK); anything that needs
reading is the Judge's job, not the Sanitizer's.
"""
from dataclasses import dataclass

# A support question is short. Longer than this is not a real customer turn; the §7.2
# `413 message too long` route keys off the same limit. Not a THRESHOLDS number — a
# design choice, so it lives here where it is easy to find and change.
MAX_LEN = 2000
_ALLOWED_WHITESPACE = {"\t", "\n", "\r", " "}


@dataclass
class Verdict:
    ok: bool
    detail: str


def sanitize(message: str) -> Verdict:
    """Allow-list check. ok=True means pass it to the Judge; ok=False means block here."""
    if len(message) > MAX_LEN:
        return Verdict(False, f"message too long ({len(message)} > {MAX_LEN} chars)")
    bad = next((c for c in message if not c.isprintable() and c not in _ALLOWED_WHITESPACE), None)
    if bad is not None:
        return Verdict(False, f"disallowed control/non-printable character {bad!r}")
    return Verdict(True, "clean: length and characters ok")
