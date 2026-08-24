from __future__ import annotations

import os

import pytest

from app.core.database import secure_sqlite_files


def test_sqlite_database_and_existing_sidecars_are_owner_only(tmp_path):
    database = tmp_path / "private" / "godfin.db"
    secure_sqlite_files(database)
    database.chmod(0o666)
    wal = database.with_name(f"{database.name}-wal")
    shm = database.with_name(f"{database.name}-shm")
    wal.write_bytes(b"wal")
    shm.write_bytes(b"shm")
    wal.chmod(0o666)
    shm.chmod(0o666)

    secure_sqlite_files(database)

    assert database.stat().st_mode & 0o077 == 0
    assert wal.stat().st_mode & 0o077 == 0
    assert shm.stat().st_mode & 0o077 == 0
    assert database.parent.stat().st_mode & 0o077 == 0


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_sqlite_database_symlink_is_rejected(tmp_path):
    target = tmp_path / "target.db"
    target.write_bytes(b"do-not-touch")
    link = tmp_path / "godfin.db"
    link.symlink_to(target)

    with pytest.raises(RuntimeError, match="symbolic link"):
        secure_sqlite_files(link)

    assert target.read_bytes() == b"do-not-touch"
