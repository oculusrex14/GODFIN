"""Frozen desktop entry point for the local GODFIN API."""

from __future__ import annotations

import multiprocessing
import os

import uvicorn


def main() -> None:
    multiprocessing.freeze_support()
    from app.main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("GODFIN_BACKEND_PORT", "5100")),
        access_log=os.environ.get("GODFIN_ACCESS_LOG") == "1",
        log_level=os.environ.get("GODFIN_LOG_LEVEL", "warning"),
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
