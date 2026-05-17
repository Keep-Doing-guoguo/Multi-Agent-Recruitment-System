from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str
    base_url: str
    responses_path: str
    files_path: str
    model: str
    multimodal_model: str
    temperature: float
    max_tokens: int
    timeout_seconds: int
    max_retries: int

    @classmethod
    def from_env(cls, dotenv_path: str | Path = ".env") -> "LLMConfig":
        load_dotenv(dotenv_path)
        return cls(
            provider=os.getenv("LLM_PROVIDER", "volcengine_ark"),
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            responses_path=os.getenv("LLM_RESPONSES_PATH", "/responses"),
            files_path=os.getenv("LLM_FILES_PATH", "/files"),
            model=os.getenv("LLM_MODEL", "doubao-seed-2-0-lite-260428"),
            multimodal_model=os.getenv("MULTIMODAL_MODEL", os.getenv("LLM_MODEL", "doubao-seed-2-0-lite-260428")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
            timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        )

    @property
    def responses_url(self) -> str:
        return self.base_url.rstrip("/") + "/" + self.responses_path.strip("/")

    @property
    def files_url(self) -> str:
        return self.base_url.rstrip("/") + "/" + self.files_path.strip("/")


def env_flag(name: str, default: bool = False, dotenv_path: str | Path = ".env") -> bool:
    load_dotenv(dotenv_path)
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
