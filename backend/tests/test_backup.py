from __future__ import annotations

from datetime import datetime, timedelta

from app.core.backup import prune_backups


def _backup(tmp_path, when: datetime):
    path = tmp_path / f"godfin_backup_{when:%Y%m%d_%H%M%S}.db"
    path.write_bytes(b"backup")
    return path


def test_retention_keeps_seven_daily_and_four_older_weekly(tmp_path):
    anchor = datetime(2026, 7, 28, 23, 0, 0)
    for days_ago in range(10):
        _backup(tmp_path, anchor - timedelta(days=days_ago))
    for weeks_ago in range(3, 10):
        _backup(tmp_path, anchor - timedelta(weeks=weeks_ago))

    removed = prune_backups(str(tmp_path))
    remaining = sorted(tmp_path.glob("godfin_backup_*.db"))

    assert removed
    assert len(remaining) == 11
    daily_names = {
        f"godfin_backup_{anchor - timedelta(days=days_ago):%Y%m%d_%H%M%S}.db"
        for days_ago in range(7)
    }
    assert daily_names.issubset({path.name for path in remaining})
