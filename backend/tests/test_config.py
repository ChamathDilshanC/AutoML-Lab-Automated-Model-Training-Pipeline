import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings, normalize_database_url


def test_defaults_are_local_and_sqlite() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "local"
    assert settings.effective_database_url.startswith("sqlite")


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "ci")
    monkeypatch.setenv("DB_HOST", "db.example")  # SQLite is not allowed outside local
    monkeypatch.setenv("CORS_ORIGINS", '["http://example.test"]')
    settings = Settings(_env_file=None)
    assert settings.environment == "ci"
    assert settings.cors_origins == ["http://example.test"]


# --- the database -------------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ["production", "staging", "ci", "anything-else"])
def test_sqlite_is_refused_everywhere_except_local(environment: str) -> None:
    with pytest.raises(ValidationError, match="only allowed when ENVIRONMENT=local"):
        Settings(_env_file=None, environment=environment)
    with pytest.raises(ValidationError, match="only allowed when ENVIRONMENT=local"):
        Settings(_env_file=None, environment=environment, database_url="sqlite:///x.db")


def test_local_may_use_either_sqlite_or_postgres() -> None:
    assert Settings(_env_file=None).effective_database_url.startswith("sqlite")
    postgres = Settings(_env_file=None, database_url="postgresql://u:p@localhost/db")
    assert postgres.effective_database_url == "postgresql+psycopg://u:p@localhost/db"


def test_a_database_host_builds_a_postgres_url_with_an_escaped_password() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        db_host="db.internal",
        db_name="automl",
        db_user="app",
        db_password="p@ss:w/rd#1 %",  # type: ignore[arg-type]
    )
    url = settings.effective_database_url
    parsed = make_url(url)
    assert parsed.password == "p@ss:w/rd#1 %"  # survives the round trip unchanged
    assert (parsed.host, parsed.port, parsed.database) == ("db.internal", 5432, "automl")
    assert parsed.query == {"sslmode": "require"}
    # The characters that would break a URL are encoded, so it cannot be mis-parsed.
    assert "p@ss" not in url and "w/rd" not in url and "#" not in url


def test_the_password_does_not_appear_in_the_settings_text() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        db_host="db.internal",
        db_password="correct-horse-battery",  # type: ignore[arg-type]
    )
    assert "correct-horse-battery" not in repr(settings) + str(settings)


def test_the_connection_parts_take_precedence_over_the_url() -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///ignored.db",
        db_host="db.internal",
        db_password="x",  # type: ignore[arg-type]
    )
    assert settings.effective_database_url.startswith("postgresql+psycopg://automl:x@db.internal")


def test_the_ssl_mode_is_configurable_and_defaults_to_encrypted() -> None:
    assert "sslmode=require" in Settings(_env_file=None, db_host="h").effective_database_url
    relaxed = Settings(_env_file=None, db_host="h", db_sslmode="disable")
    assert relaxed.effective_database_url.endswith("sslmode=disable")


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_database_urls_are_pointed_at_the_installed_driver(given: str, expected: str) -> None:
    assert normalize_database_url(given) == expected
