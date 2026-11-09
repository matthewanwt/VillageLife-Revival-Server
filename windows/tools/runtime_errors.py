"""Stable, user-visible error codes for player support and automated regression tests.

Do not embed tokens, join codes or raw secrets in exception messages.
"""
from __future__ import annotations
import json
import sys
import traceback
from pathlib import Path


class VillageRuntimeError(RuntimeError, ValueError):
    def __init__(self, code: str, explanation: str, remedy: str = "", *, details: str = ""):
        self.code = code
        self.explanation = explanation
        self.remedy = remedy
        self.details = details
        super().__init__(f"[{code}] {explanation}" + (f" Next: {remedy}" if remedy else ""))


def initialize_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def report_error(error: Exception, *, report_file: Path | None = None) -> None:
    """Print a specific player-facing failure and write an optional technical receipt.

    The report deliberately contains no environment dump or application settings.
    """
    if isinstance(error, VillageRuntimeError):
        print(f"ERROR {error}", flush=True)
        data = {"code": error.code, "explanation": error.explanation, "remedy": error.remedy}
        if error.details:
            data["technical_details"] = error.details[:1200]
    else:
        print("ERROR [VL-UNEXPECTED] The launcher encountered an unexpected error.", flush=True)
        print(f"Details: {type(error).__name__}: {str(error)[:800]}", flush=True)
        print("Next: Export diagnostics and send the support bundle privately.", flush=True)
        data = {"code": "VL-UNEXPECTED", "exception_type": type(error).__name__, "message": str(error)[:1000]}
    if report_file is not None:
        try:
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
