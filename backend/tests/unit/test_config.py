from budgeted_research.config import ProviderSettings


def test_moonshot_timeout_is_independent_from_http_timeout(monkeypatch) -> None:
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "17")
    monkeypatch.setenv("MOONSHOT_TIMEOUT_SECONDS", "240")
    monkeypatch.setenv("MOONSHOT_THINKING_ENABLED", "false")
    monkeypatch.delenv("MOONSHOT_TEMPERATURE", raising=False)

    settings = ProviderSettings.from_environment()

    assert settings.request_timeout_seconds == 17
    assert settings.moonshot_timeout_seconds == 240
    assert settings.moonshot_thinking_enabled is False
    assert settings.moonshot_temperature is None
