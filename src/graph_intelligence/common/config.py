"""Configuration management via pydantic-settings."""

from pathlib import Path
from typing import Optional
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve repository root directory (3 levels up from this file)
# src/graph_intelligence/common/config.py -> parents[3] is repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    FALKORDB_HOST: str = Field(default="localhost")
    FALKORDB_PORT: int = Field(default=6379)
    FALKORDB_USERNAME: Optional[str] = Field(default=None)
    FALKORDB_PASSWORD: Optional[SecretStr] = Field(default=None)
    FALKORDB_SSL: bool = Field(default=False)
    FALKORDB_GRAPH: str = Field(default="graphcortex_demo")
    FALKORDB_GRAPH_TEST: str = Field(default="graphcortex_test")
    DEMO_USER_ID: str = Field(default="demo-user-herbert")
    DEFAULT_PROJECT_ID: str = Field(default="proj-payment-reliability")
    LOG_LEVEL: str = Field(default="INFO")

    @field_validator("FALKORDB_USERNAME", mode="before")
    @classmethod
    def handle_empty_username(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and str(v).strip() == "":
            return None
        return v

    def get_password_str(self) -> Optional[str]:
        """Safely extract plain password string for adapter without repr leakage."""
        if self.FALKORDB_PASSWORD is None:
            return None
        val = self.FALKORDB_PASSWORD.get_secret_value()
        if not val or not val.strip():
            return None
        return val


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Retrieve global cached settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
