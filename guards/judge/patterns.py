"""guards/judge/patterns.py — Stage 6 (J-2, deterministic half).

The Judge's deterministic pattern matcher: the known attack shapes a regex can catch
without a model call. Patterns use word boundaries so ordinary words slip through —
"drop the gift wrap", "select a plan", "delete my old address" must NOT match (that is
the T-LEGIT-FALSE-BLOCK side of the lesson); the model handles anything subtler (J-2).
"""
import re
from dataclasses import dataclass

PATTERNS = {
    "sql_injection": [
        r"'\s*;", r";\s*--", r"\bdrop\s+table\b", r"\bunion\s+select\b",
        r"\bor\s+1\s*=\s*1\b", r"\bdelete\s+from\b", r"\binsert\s+into\b",
        r"\bupdate\s+\w+\s+set\b",
    ],
    "markup_injection": [
        r"<\s*script\b", r"</\s*script", r"javascript:", r"onerror\s*=",
        r"<\s*iframe\b", r"<\s*svg\b",
    ],
    "template_injection": [r"\{\{", r"\}\}", r"\$\{", r"<%", r"%>", r"#\{"],
    "shell_injection": [
        r"\$\(", r"`[^`]*`", r"\brm\s+-rf\b", r"/bin/(?:ba)?sh\b",
        r"\bbash\s+-c\b", r"\b(?:curl|wget)\s+https?://",
    ],
    "path_traversal": [r"\.\./", r"\.\.\\", r"/etc/passwd\b", r"%2e%2e", r"\.\.%2f"],
    "prompt_extraction": [
        r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?)\b",
        r"\bdisregard\s+(?:the\s+)?(?:above|previous|prior|system)\b",
        r"\b(?:reveal|show|print|repeat|share)\s+(?:me\s+)?(?:your\s+)?(?:the\s+)?(?:system\s+)?(?:prompt|instructions?)\b",
        r"\bsystem\s+prompt\b", r"\byou\s+are\s+now\b", r"\bdeveloper\s+mode\b",
    ],
}
_COMPILED = {cat: [re.compile(p, re.IGNORECASE) for p in ps] for cat, ps in PATTERNS.items()}


@dataclass
class Hit:
    category: str
    snippet: str


def scan(message: str) -> Hit | None:
    """Return the first attack pattern that matches, or None if the message looks clean."""
    for category, regexes in _COMPILED.items():
        for rx in regexes:
            m = rx.search(message)
            if m:
                return Hit(category, m.group(0))
    return None
