from app.core.config import Settings


def test_defaults_are_local_and_sqlite() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "local"
    assert settings.database_url.startswith("sqlite")


def test_environment_overrides_defaults(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "ci")
    monkeypatch.setenv("CORS_ORIGINS", '["http://example.test"]')
    settings = Settings(_env_file=None)
    assert settings.environment == "ci"
    assert settings.cors_origins == ["http://example.test"]
