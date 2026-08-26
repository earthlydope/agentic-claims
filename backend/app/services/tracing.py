"""Tracing and evaluation, through LangSmith where it is configured.

One trace from the customer tap to the signed write. LangSmith is the destination when a
key is present; where it is not, the same spans are kept in process so the console still
has a trace to show and the platform behaves identically. Tracing that only works when a
SaaS key is present is tracing you cannot rely on in a regulated environment.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

LANGSMITH_KEY = (
    os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY") or ""
)
LANGSMITH_PROJECT = os.environ.get("LANGSMITH_PROJECT", "allianz-at-agentic-claims")
LANGSMITH_ENDPOINT = os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")


def langsmith_enabled() -> bool:
    return bool(LANGSMITH_KEY)


if langsmith_enabled():
    # The SDK reads these, so set them once rather than passing them everywhere.
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", LANGSMITH_KEY)
    os.environ.setdefault("LANGCHAIN_PROJECT", LANGSMITH_PROJECT)
    os.environ.setdefault("LANGCHAIN_ENDPOINT", LANGSMITH_ENDPOINT)


# --------------------------------------------------------------------------
@dataclass
class Span:
    span_id: str
    name: str
    kind: str                    # chain | llm | tool | guard | write
    parent_id: str | None
    started_at: float
    ended_at: float | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.perf_counter()
        return round((end - self.started_at) * 1000.0, 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id, "name": self.name, "kind": self.kind,
            "parent_id": self.parent_id, "duration_ms": self.duration_ms,
            "inputs": self.inputs, "outputs": self.outputs, "error": self.error,
            "metadata": self.metadata,
        }


class Trace:
    """A tree of spans for one unit of work, whether or not LangSmith is listening."""

    def __init__(self, name: str, *, metadata: dict[str, Any] | None = None) -> None:
        self.trace_id = f"tr-{uuid.uuid4().hex[:12]}"
        self.name = name
        self.metadata = metadata or {}
        self.started_at = dt.datetime.now(dt.timezone.utc).isoformat()
        self.spans: list[Span] = []
        self._stack: list[str] = []

    @contextlib.contextmanager
    def span(
        self, name: str, kind: str = "chain", **inputs: Any
    ) -> Iterator[Span]:
        span = Span(
            span_id=f"sp-{uuid.uuid4().hex[:10]}",
            name=name, kind=kind,
            parent_id=self._stack[-1] if self._stack else None,
            started_at=time.perf_counter(),
            inputs=_safe(inputs),
        )
        self.spans.append(span)
        self._stack.append(span.span_id)
        try:
            yield span
        except Exception as exc:  # noqa: BLE001 — the span records it, then re-raises
            span.error = f"{type(exc).__name__}: {exc}"[:400]
            raise
        finally:
            span.ended_at = time.perf_counter()
            self._stack.pop()

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "started_at": self.started_at,
            "destination": "langsmith" if langsmith_enabled() else "in-process",
            "project": LANGSMITH_PROJECT if langsmith_enabled() else None,
            "metadata": self.metadata,
            "span_count": len(self.spans),
            "spans": [s.as_dict() for s in self.spans],
        }

    def flush(self) -> dict[str, Any]:
        """Ship the trace where it belongs, and return what was shipped."""
        payload = self.as_dict()
        if langsmith_enabled():
            try:
                _push_to_langsmith(self)
                payload["shipped"] = True
            except Exception as exc:  # noqa: BLE001 — never fail a run over telemetry
                payload["shipped"] = False
                payload["ship_error"] = f"{type(exc).__name__}: {exc}"[:200]
        else:
            payload["shipped"] = False
        return payload


def _push_to_langsmith(trace: Trace) -> None:  # pragma: no cover — needs a key
    from langsmith import Client

    client = Client(api_key=LANGSMITH_KEY, api_url=LANGSMITH_ENDPOINT)
    root_id = uuid.uuid4()
    ids: dict[str, uuid.UUID] = {}

    for span in trace.spans:
        ids[span.span_id] = uuid.uuid4()

    client.create_run(
        id=root_id, name=trace.name, run_type="chain",
        project_name=LANGSMITH_PROJECT,
        inputs=trace.metadata, outputs={"span_count": len(trace.spans)},
    )
    for span in trace.spans:
        client.create_run(
            id=ids[span.span_id],
            name=span.name,
            run_type=_RUN_TYPE.get(span.kind, "chain"),
            project_name=LANGSMITH_PROJECT,
            parent_run_id=ids.get(span.parent_id or "", root_id),
            inputs=span.inputs, outputs=span.outputs,
            error=span.error, extra={"metadata": span.metadata},
        )


_RUN_TYPE = {
    "llm": "llm", "tool": "tool", "chain": "chain", "guard": "chain", "write": "chain",
}


def _safe(value: Any, depth: int = 0) -> Any:
    """Traces are read by people; keep them readable and never let one raise."""
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        return {str(k): _safe(v, depth + 1) for k, v in list(value.items())[:24]}
    if isinstance(value, (list, tuple)):
        return [_safe(v, depth + 1) for v in list(value)[:12]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and len(value) > 800:
            return value[:800] + " […]"
        return value
    if hasattr(value, "model_dump"):
        try:
            return _safe(value.model_dump(), depth + 1)
        except Exception:  # noqa: BLE001
            return str(value)[:400]
    return str(value)[:400]


def status() -> dict[str, Any]:
    return {
        "langsmith_enabled": langsmith_enabled(),
        "project": LANGSMITH_PROJECT,
        "endpoint": LANGSMITH_ENDPOINT if langsmith_enabled() else None,
        "destination": "langsmith" if langsmith_enabled() else "in-process",
        "note": (
            "Traces are shipped to LangSmith."
            if langsmith_enabled()
            else "No LANGSMITH_API_KEY is set, so traces are kept in process. The console "
                 "shows the same spans either way."
        ),
    }
