"""Environment-based application configuration."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


@dataclass(frozen=True)
class Settings:
    hindsight_api_key: str
    hindsight_base_url: str
    hindsight_bank_id: str
    groq_api_key: str
    groq_model: str = DEFAULT_GROQ_MODEL


def get_settings() -> Settings:
    return Settings(
        hindsight_api_key=os.getenv("HINDSIGHT_API_KEY", "").strip(),
        hindsight_base_url=os.getenv("HINDSIGHT_BASE_URL", "").strip(),
        hindsight_bank_id=os.getenv("HINDSIGHT_BANK_ID", "").strip(),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL,
    )


def missing_hindsight_settings(settings: Settings | None = None) -> list[str]:
    configured = settings or get_settings()
    required = {
        "HINDSIGHT_API_KEY": configured.hindsight_api_key,
        "HINDSIGHT_BASE_URL": configured.hindsight_base_url,
        "HINDSIGHT_BANK_ID": configured.hindsight_bank_id,
    }
    return [name for name, value in required.items() if not value]