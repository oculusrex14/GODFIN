"""Frozen desktop entry point for the local GODFIN API."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
from pathlib import Path

import uvicorn


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GODFIN local desktop backend")
    parser.add_argument("--prepare-update-transition", action="store_true")
    parser.add_argument("--complete-backup-restore", action="store_true")
    parser.add_argument("--restore-token")
    parser.add_argument("--current-version")
    parser.add_argument("--target-version")
    return parser.parse_args()


def _recovery_paths() -> dict[str, str]:
    db_path = os.environ.get("DB_PATH")
    if not db_path:
        raise RuntimeError("The desktop database path is not configured.")
    database = Path(db_path).expanduser()
    backup_dir = os.environ.get(
        "GODFIN_BACKUP_DIR", str(database.parent / "backups")
    )
    journal_path = os.environ.get(
        "GODFIN_UPDATE_RECOVERY_JOURNAL",
        str(database.parent / "update-recovery.json"),
    )
    return {
        "db_path": db_path,
        "backup_dir": backup_dir,
        "journal_path": journal_path,
    }


def main() -> None:
    multiprocessing.freeze_support()
    arguments = _arguments()
    from app.core.update_recovery import (
        prepare_update_transition,
        recover_interrupted_transition,
    )

    paths = _recovery_paths()
    if arguments.complete_backup_restore:
        if not arguments.restore_token:
            raise RuntimeError("The one-use restore token is required.")
        from app.core.restore_request import (
            complete_restore_request,
            default_restore_request_path,
        )
        from app.core.startup_migrations import CURRENT_SCHEMA_REVISION

        result = complete_restore_request(
            backup_dir=paths["backup_dir"],
            database_path=paths["db_path"],
            request_path=default_restore_request_path(paths["db_path"]),
            restore_token=arguments.restore_token,
            maximum_schema_revision=CURRENT_SCHEMA_REVISION,
        )
        print(json.dumps(result, sort_keys=True))
        return
    if arguments.prepare_update_transition:
        if not arguments.current_version or not arguments.target_version:
            raise RuntimeError("Both update versions are required.")
        result = prepare_update_transition(
            **paths,
            current_version=arguments.current_version,
            target_version=arguments.target_version,
        )
        print(json.dumps(result, sort_keys=True))
        return

    from app.core.config import settings
    from app.core.network_access import bind_host

    app_version = os.environ.get("GODFIN_APP_VERSION", settings.VERSION)
    recover_interrupted_transition(**paths, current_version=app_version)

    from app.main import app

    uvicorn.run(
        app,
        host=bind_host(),
        port=int(os.environ.get("GODFIN_BACKEND_PORT", "5100")),
        access_log=os.environ.get("GODFIN_ACCESS_LOG") == "1",
        log_level=os.environ.get("GODFIN_LOG_LEVEL", "warning"),
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
