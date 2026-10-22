"""Environment-backed settings for the local API server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    cors_origins: tuple[str, ...]

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if environ is None else environ
        host = env.get("SONIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
        try:
            port = int(env.get("SONIC_PORT", "8000"))
        except ValueError as exc:
            raise ValueError("SONIC_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ValueError("SONIC_PORT must be between 1 and 65535")
        origin_value = env.get(
            "SONIC_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        origins = tuple(origin.strip().rstrip("/") for origin in origin_value.split(",") if origin.strip())
        return cls(host=host, port=port, cors_origins=origins)
