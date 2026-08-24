from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def secure_sqlite_files(database_path: Path) -> None:
    """Create/harden the local SQLite database and any active sidecar files."""

    path = database_path.expanduser()
    if path.is_symlink():
        raise RuntimeError("GODFIN database path cannot be a symbolic link")
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not parent_existed:
        os.chmod(path.parent, 0o700)

    no_follow = getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | no_follow, 0o600)
    os.close(descriptor)
    os.chmod(path, 0o600)

    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.is_symlink():
            raise RuntimeError("GODFIN database sidecar cannot be a symbolic link")
        if sidecar.exists():
            os.chmod(sidecar, 0o600)


secure_sqlite_files(settings.database_path)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    secure_sqlite_files(settings.database_path)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
