from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.account import Account
from app.models.app_setting import AppSetting
from app.seed import run_seeds


def test_clean_database_bootstraps_with_create_all_and_seeds(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        run_seeds(session)
        assert session.query(Account).count() == 2
        assert (
            session.query(AppSetting)
            .filter_by(key="allow_network_access", value="false")
            .one()
        )
    finally:
        session.close()
        engine.dispose()
