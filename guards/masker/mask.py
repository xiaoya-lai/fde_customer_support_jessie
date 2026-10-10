"""guards/masker/mask.py — Stage 8 (K-2, the regex core).

Deterministic PII masking: emails other than the logged-in user's own, phone numbers,
and card-like numbers, and nothing else. It never changes case or whitespace (the R-8
lowercase-Masker precedent): it only substitutes a matched PII span with a fixed token,
leaving every other character untouched. Returns the masked text and a per-category count
so the step can report exactly what it changed (K-3).
"""
import re

# Order matters: card-like runs (13–16 digits) are matched before phones so a long card
# number is not chewed up as a phone. Each pattern maps to the token it is replaced with.
_CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
_PHONE = re.compile(
    r"(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"  # 10-digit
    r"|\b\d{3}[\s.-]\d{4}\b"                                        # 7-digit, e.g. 555-0100
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def mask_text(text: str, own_email: str | None) -> tuple[str, dict]:
    """Mask PII in `text`, keeping the logged-in user's own email. Returns (masked, counts)."""
    counts = {"email": 0, "phone": 0, "card": 0}
    own = (own_email or "").strip().lower()

    def _card(m):
        counts["card"] += 1
        return "[card]"

    def _phone(m):
        counts["phone"] += 1
        return "[phone]"

    def _email(m):
        if m.group(0).lower() == own:  # the user's own email is not PII to the user (K-2)
            return m.group(0)
        counts["email"] += 1
        return "[email]"

    masked = _CARD.sub(_card, text)
    masked = _PHONE.sub(_phone, masked)
    masked = _EMAIL.sub(_email, masked)
    return masked, counts


def describe(counts: dict) -> str:
    """K-3: a human detail line that names what was masked, or that nothing was."""
    parts = []
    for kind in ("email", "phone", "card"):
        n = counts[kind]
        if n:
            parts.append(f"{n} {kind}{'s' if n > 1 else ''}")
    return "masked " + ", ".join(parts) if parts else "nothing to mask"
