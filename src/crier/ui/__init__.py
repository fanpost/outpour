"""Outpour web UI package (Phase 2, optional [ui] extra).

Importing this package must not require FastAPI, so the CLI stays
usable without the extra installed. create_app and run_server import
their heavy dependencies lazily and raise a clear error when the
extra is missing.
"""

from __future__ import annotations

from typing import Any


def create_app(service: Any = None):  # type: ignore[no-untyped-def]
    """Build the FastAPI app (requires the [ui] extra)."""
    try:
        from .app import create_app as _create_app
    except ImportError as exc:
        raise RuntimeError(
            "The web UI needs the [ui] extra: pip install 'outpour[ui]'"
        ) from exc
    return _create_app(service)


def run_server(port: int = 8000) -> None:
    """Serve the UI on 127.0.0.1 only. Never bind a public interface."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "The web UI needs the [ui] extra: pip install 'outpour[ui]'"
        ) from exc
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=port)
