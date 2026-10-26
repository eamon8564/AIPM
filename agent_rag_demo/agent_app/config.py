"""集中管理项目配置，避免把密钥或参数散落在业务代码中。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env")


_load_dotenv_if_available()


@dataclass(frozen=True)
class Settings:
    """应用运行参数。local 模式不依赖任何第三方服务。"""

    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    runtime_dir: Path = PROJECT_ROOT / "runtime"
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "360"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "60"))
    top_k: int = int(os.getenv("TOP_K", "3"))
    min_retrieval_score: float = float(os.getenv("MIN_RETRIEVAL_SCORE", "0.08"))
    default_mode: str = os.getenv("AGENT_MODE", "local").lower()
    openai_model: str | None = os.getenv("OPENAI_MODEL") or None

    @property
    def has_openai_key(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))


def get_settings() -> Settings:
    settings = Settings()
    if settings.chunk_overlap >= settings.chunk_size:
        raise ValueError("CHUNK_OVERLAP 必须小于 CHUNK_SIZE")
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    return settings
