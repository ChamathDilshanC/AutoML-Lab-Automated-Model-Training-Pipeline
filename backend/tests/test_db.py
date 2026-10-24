from sqlalchemy import text

from app.db.session import make_engine


def test_sqlite_engine_connects_and_enforces_foreign_keys() -> None:
    engine = make_engine("sqlite://")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
