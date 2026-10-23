from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Deliberately never load the legacy, tracked .env file.
    model_config = SettingsConfigDict(
        env_prefix="KINVOICE_", env_file=BACKEND / ".env.local", extra="ignore", hide_input_in_errors=True
    )
    mode: Literal["disabled", "demo", "remote"] = "disabled"
    auth_db: Path = BACKEND / "data" / "ccare_auth.db"
    api_key: str = Field(default="", repr=False)
    api_base: str = ""
    model: str = ""
    provider_label: str = ""
    provider_privacy_url: str = ""
    provider_kind: Literal["compatible", "deepseek"] = "compatible"
    session_seconds: int = Field(default=3600, ge=60, le=86400)
    call_timeout: float = Field(default=12, gt=0, le=30)
    turn_timeout: float = Field(default=45, gt=0, le=90)
    max_tokens: int = Field(default=700, ge=100, le=2000)

    @model_validator(mode="after")
    def remote_configuration(self):
        if self.mode == "remote":
            if not all((self.api_key, self.model, self.provider_label)):
                raise ValueError("Remote mode requires a new key, model and provider label")
            endpoint = urlsplit(self.api_base)
            if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
                raise ValueError("Remote provider must use HTTPS")
            if self.provider_kind == "deepseek" and (endpoint.hostname != "api.deepseek.com" or endpoint.path.rstrip("/") not in ("", "/v1")):
                raise ValueError("DeepSeek profile requires its official API endpoint")
            if not self.provider_privacy_url.startswith("https://"):
                raise ValueError("Configure the provider privacy notice before enabling remote mode")
        return self
