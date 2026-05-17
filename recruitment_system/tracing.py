from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from recruitment_system.models import RunEvent


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunTracer:
    """Collects structured run events for workflow observability."""

    def emit(
        self,
        state: dict[str, Any],
        node: str,
        event_type: str,
        *,
        status: str = "running",
        duration_ms: int | None = None,
        decision: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> list[RunEvent]:
        events = list(state.get("run_events", []))
        events.append(
            RunEvent(
                run_id=str(state.get("run_id", "")),
                node=node,
                event_type=event_type,
                timestamp=utc_now_iso(),
                duration_ms=duration_ms,
                status=status,
                decision=decision,
                metadata=metadata or {},
                warnings=warnings or [],
                errors=errors or [],
            )
        )
        return events

    def started(self, state: dict[str, Any], node: str) -> tuple[float, list[RunEvent]]:
        return perf_counter(), self.emit(state, node, "node_started", status="running")

    def completed(
        self,
        state: dict[str, Any],
        node: str,
        started_at: float,
        *,
        decision: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> list[RunEvent]:
        duration_ms = int((perf_counter() - started_at) * 1000)
        return self.emit(
            state,
            node,
            "node_completed",
            status="completed",
            duration_ms=duration_ms,
            decision=decision,
            metadata=metadata,
            warnings=warnings,
            errors=errors,
        )

    def failed(self, state: dict[str, Any], node: str, started_at: float, error: Exception) -> list[RunEvent]:
        duration_ms = int((perf_counter() - started_at) * 1000)
        return self.emit(
            state,
            node,
            "node_failed",
            status="failed",
            duration_ms=duration_ms,
            errors=[f"{type(error).__name__}: {error}"],
        )
