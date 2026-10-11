from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moonshot_api_key: SecretStr | None = None
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    moonshot_model: str | None = None
    moonshot_temperature: float | None = Field(default=None, ge=0, le=2)
    moonshot_thinking_enabled: bool = False
    moonshot_input_cost_per_million_usd: float | None = Field(default=None, ge=0)
    moonshot_output_cost_per_million_usd: float | None = Field(default=None, ge=0)
    tavily_api_key: SecretStr | None = None
    tavily_base_url: str = "https://api.tavily.com"
    request_timeout_seconds: float = Field(default=20.0, gt=0)
    moonshot_timeout_seconds: float = Field(default=300.0, gt=0)
    provider_max_retries: int = Field(default=1, ge=0, le=3)
    provider_retry_delay_seconds: float = Field(default=0.5, ge=0, le=10)

    @classmethod
    def from_environment(cls) -> ProviderSettings:
        timeout = os.getenv("REQUEST_TIMEOUT_SECONDS", "20")
        moonshot_timeout = os.getenv("MOONSHOT_TIMEOUT_SECONDS", "300")
        provider_max_retries = os.getenv("PROVIDER_MAX_RETRIES", "1")
        provider_retry_delay = os.getenv("PROVIDER_RETRY_DELAY_SECONDS", "0.5")
        return cls(
            moonshot_api_key=_optional_secret("MOONSHOT_API_KEY"),
            moonshot_base_url=os.getenv(
                "MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"
            ),
            moonshot_model=os.getenv("MOONSHOT_MODEL") or None,
            moonshot_temperature=_optional_float("MOONSHOT_TEMPERATURE"),
            moonshot_thinking_enabled=_environment_bool(
                "MOONSHOT_THINKING_ENABLED", default=False
            ),
            moonshot_input_cost_per_million_usd=_optional_float(
                "MOONSHOT_INPUT_COST_PER_MILLION_USD"
            ),
            moonshot_output_cost_per_million_usd=_optional_float(
                "MOONSHOT_OUTPUT_COST_PER_MILLION_USD"
            ),
            tavily_api_key=_optional_secret("TAVILY_API_KEY"),
            tavily_base_url=os.getenv("TAVILY_BASE_URL", "https://api.tavily.com"),
            request_timeout_seconds=float(timeout),
            moonshot_timeout_seconds=float(moonshot_timeout),
            provider_max_retries=int(provider_max_retries),
            provider_retry_delay_seconds=float(provider_retry_delay),
        )

    def require_moonshot(self) -> tuple[str, str]:
        if self.moonshot_api_key is None or self.moonshot_model is None:
            raise ValueError("MOONSHOT_API_KEY and MOONSHOT_MODEL are required")
        return self.moonshot_api_key.get_secret_value(), self.moonshot_model

    def require_tavily_key(self) -> str:
        if self.tavily_api_key is None:
            raise ValueError("TAVILY_API_KEY is required")
        return self.tavily_api_key.get_secret_value()


def _optional_secret(name: str) -> SecretStr | None:
    value = os.getenv(name)
    return SecretStr(value) if value else None


def _optional_float(name: str) -> float | None:
    value = os.getenv(name)
    return float(value) if value else None


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")
