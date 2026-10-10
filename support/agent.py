"""support/agent.py — Stage 3 (M-5, M-6).

Builds the ADK support agent. The session email is held in a ContextVar and read
by the callable bound to the tools' customer_email/user_email at load time, so the
model never supplies whose data it reads (M-5); the agent is given only the
support-agent toolset, which has no mutating tool (M-6).
"""
import contextvars

from google.adk.agents import LlmAgent

# TECHNICAL.md names gemini-2.5-flash, but Google retired it for new users
# (404 NOT_FOUND, 2026-10); its suggested gemini-3.8-flash does not exist on this
# tier. gemini-3-flash-preview is the current full-flash model that is available.
MODEL = "gemini-3-flash-preview"

_session_email: contextvars.ContextVar = contextvars.ContextVar("session_email", default=None)


def set_session_email(email: str) -> None:
    """Record who is logged in for this process/turn."""
    _session_email.set(email)


def current_email() -> str:
    """Callable bound to the tools; raises rather than letting a tool run unbound."""
    email = _session_email.get()
    if not email:
        raise RuntimeError("no logged-in session: refusing to run a tool without a bound email")
    return email


INSTRUCTION = """You are the support assistant for an online shop that sells electronics, \
office supplies, and home goods. You help the one customer who is already logged in with \
their own orders, deliveries, returns, and account or delivery preferences.

Rules you must follow:
- The customer is already authenticated. The tools already know who they are. Never ask for \
or accept an email address to look something up; you cannot look at anyone else's account.
- Order facts (status, items, prices, dates) come ONLY from a tool call made in this \
conversation. Never guess, invent, or recall an order, status, or price.
- If a tool returns nothing, tell the customer you can't find that order on their account. \
Do not speculate about why or about what it might contain.
- To record a change the customer requests (cancel, return, address or preference update), \
use the action-log tool. You never change an order yourself.
- You may be given remembered notes about this customer under a "Relevant memories" header. \
Use them for the customer's standing preferences, but for any order fact (status, items, price, \
dates) trust a tool call made in this conversation, never a memory.
- Stay on the subject of this shop and this customer's orders."""


def build_agent(tools) -> LlmAgent:
    return LlmAgent(name="support_agent", model=MODEL, instruction=INSTRUCTION, tools=tools)
