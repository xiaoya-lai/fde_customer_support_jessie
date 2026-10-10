"""support/telemetry.py — Stage 5 (O-1..O-4).

Wires one Phoenix trace per turn: an OTLP/HTTP exporter pointed at the standalone
`phoenix serve` process, a global TracerProvider installed BEFORE any agent is built,
and Gemini auto-instrumentation (O-3). setup() is idempotent and returns the tracer the
pipeline opens `agent.turn` on; trace_url() builds the O-4 deep link into Phoenix.
"""
import json
import os
import urllib.request

from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
from openinference.semconv.resource import ResourceAttributes
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

PHOENIX_URL = os.environ.get("PHOENIX_URL", "http://localhost:6006")
PROJECT = os.environ.get("PHOENIX_PROJECT", "support")

_tracer = None
_project_id = None


def setup():
    """Install the global TracerProvider + Gemini instrumentation once, before agents build."""
    global _tracer
    if _tracer is not None:
        return _tracer
    resource = Resource.create({ResourceAttributes.PROJECT_NAME: PROJECT})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{PHOENIX_URL}/v1/traces"))
    )
    trace.set_tracer_provider(provider)  # global, so ADK's auto-spans join our turn (O-2)
    GoogleGenAIInstrumentor().instrument(tracer_provider=provider)
    _tracer = trace.get_tracer("support")
    return _tracer


def flush():
    """Ship buffered spans now so a trace is readable the instant a turn ends."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush()


def _resolve_project_id():
    """Look up Phoenix's internal id for our project name once (REST), so the URL opens it."""
    global _project_id
    if _project_id is not None:
        return _project_id
    try:
        with urllib.request.urlopen(f"{PHOENIX_URL}/v1/projects", timeout=3) as r:
            for p in json.load(r).get("data", []):
                if p.get("name") == PROJECT:
                    _project_id = p["id"]
                    break
    except Exception:
        _project_id = ""
    return _project_id


def trace_url(trace_id: str) -> str:
    pid = _resolve_project_id()
    return f"{PHOENIX_URL}/projects/{pid}/traces/{trace_id}" if pid else f"{PHOENIX_URL}/projects"
