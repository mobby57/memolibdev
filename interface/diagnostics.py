from __future__ import annotations

import socket
import subprocess
import urllib.error
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StepDiagnostic:
    step_id: str
    duration_s: float
    timeout_s: float | None
    status: str
    error_code: str | None = None
    exception_type: str | None = None

    @property
    def failed(self) -> bool:
        return self.status == "FAILED"

    @property
    def degraded(self) -> bool:
        return self.status == "DEGRADED"

    def user_message(self) -> str:
        if not self.error_code:
            return f"{self.step_id} terminé en {self.duration_s:.2f}s."

        parts = [
            self.error_code,
            f"étape : {self.step_id}",
            f"durée mesurée : {self.duration_s:.2f}s",
        ]
        if self.timeout_s is not None:
            parts.append(f"limite configurée : {self.timeout_s:g}s")
        if self.exception_type:
            parts.append(f"exception : {self.exception_type}")
        return " — ".join(parts)


class StepDiagnosticFailure(RuntimeError):
    def __init__(self, diagnostic: StepDiagnostic):
        super().__init__(diagnostic.error_code or diagnostic.step_id)
        self.diagnostic = diagnostic


def successful_step(step_id: str, duration_s: float) -> StepDiagnostic:
    return StepDiagnostic(
        step_id=step_id,
        duration_s=duration_s,
        timeout_s=None,
        status="SUCCESS",
    )


def failed_step(
    step_id: str,
    duration_s: float,
    exception: Exception,
    *,
    error_code: str,
    timeout_s: float | None = None,
) -> StepDiagnostic:
    return StepDiagnostic(
        step_id=step_id,
        duration_s=duration_s,
        timeout_s=timeout_s,
        status="FAILED",
        error_code=error_code,
        exception_type=type(exception).__name__,
    )


def inspection_failure(
    duration_s: float,
    exception: Exception,
    timeout_s: float,
) -> StepDiagnostic:
    if isinstance(exception, subprocess.TimeoutExpired):
        return failed_step(
            "Inspection",
            duration_s,
            exception,
            error_code="INSPECTION_TIMEOUT",
            timeout_s=timeout_s,
        )
    return failed_step(
        "Inspection",
        duration_s,
        exception,
        error_code="INSPECTION_ERROR",
    )


def ollama_failure(
    duration_s: float,
    exception: Exception,
    timeout_s: float,
) -> StepDiagnostic:
    if isinstance(exception, (TimeoutError, socket.timeout)):
        return failed_step(
            "Génération Ollama",
            duration_s,
            exception,
            error_code="OLLAMA_TIMEOUT",
            timeout_s=timeout_s,
        )

    if isinstance(exception, urllib.error.URLError):
        reason = exception.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return failed_step(
                "Génération Ollama",
                duration_s,
                exception,
                error_code="OLLAMA_TIMEOUT",
                timeout_s=timeout_s,
            )
        if isinstance(
            reason,
            (
                ConnectionError,
                ConnectionRefusedError,
                ConnectionResetError,
                ConnectionAbortedError,
                socket.gaierror,
            ),
        ):
            return failed_step(
                "Génération Ollama",
                duration_s,
                exception,
                error_code="OLLAMA_CONNECTION_ERROR",
            )

    if isinstance(
        exception,
        (
            ConnectionError,
            ConnectionRefusedError,
            ConnectionResetError,
            ConnectionAbortedError,
            socket.gaierror,
        ),
    ):
        return failed_step(
            "Génération Ollama",
            duration_s,
            exception,
            error_code="OLLAMA_CONNECTION_ERROR",
        )

    return failed_step(
        "Génération Ollama",
        duration_s,
        exception,
        error_code="OLLAMA_ERROR",
    )


def web_research_diagnostic(
    duration_s: float,
    report: dict[str, Any],
) -> StepDiagnostic:
    sources = report.get("sources", [])
    has_source_error = isinstance(sources, list) and any(
        isinstance(source, dict) and source.get("error")
        for source in sources
    )
    if report.get("success") is False or has_source_error:
        return StepDiagnostic(
            step_id="Recherche Web",
            duration_s=duration_s,
            timeout_s=None,
            status="DEGRADED",
            error_code="WEB_RESEARCH_FAILED",
            exception_type="WebResearchFailure",
        )
    return successful_step("Recherche Web", duration_s)


def timing_summary(diagnostics: list[StepDiagnostic]) -> str:
    return " | ".join(
        f"{diagnostic.step_id}: {diagnostic.duration_s:.2f}s"
        for diagnostic in diagnostics
    )
