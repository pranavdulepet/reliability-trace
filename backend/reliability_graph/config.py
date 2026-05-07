import os
from pathlib import Path
from typing import Dict, List, Optional


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(
        self,
        db_path: Path,
        cors_origins: List[str],
        cors_origin_regex: Optional[str],
        user_id: str,
        secret: Optional[str],
        public_demo: bool,
        access_token: Optional[str],
        rate_limit_requests: int,
        rate_limit_window_seconds: int,
        allow_key_management: bool,
        cookie_secure: bool,
    ) -> None:
        self.db_path = db_path
        self.cors_origins = cors_origins
        self.cors_origin_regex = cors_origin_regex
        self.user_id = user_id
        self.secret = secret
        self.public_demo = public_demo
        self.access_token = access_token
        self.rate_limit_requests = rate_limit_requests
        self.rate_limit_window_seconds = rate_limit_window_seconds
        self.allow_key_management = allow_key_management
        self.cookie_secure = cookie_secure

    @classmethod
    def from_env(cls) -> "Settings":
        db_path = Path(os.getenv("RELIABILITY_GRAPH_DB", "data/reliability_graph.sqlite"))
        cors = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
        )
        public_demo = _bool_env("RELIABILITY_GRAPH_PUBLIC_DEMO", False)
        return cls(
            db_path=db_path,
            cors_origins=[origin.strip() for origin in cors.split(",") if origin.strip()],
            cors_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1):[0-9]+"),
            user_id=os.getenv("RELIABILITY_GRAPH_USER_ID", "local"),
            secret=os.getenv("RELIABILITY_GRAPH_SECRET"),
            public_demo=public_demo,
            access_token=os.getenv("RELIABILITY_GRAPH_ACCESS_TOKEN") or None,
            rate_limit_requests=int(os.getenv("RELIABILITY_GRAPH_RATE_LIMIT_REQUESTS", "120")),
            rate_limit_window_seconds=int(os.getenv("RELIABILITY_GRAPH_RATE_LIMIT_WINDOW_SECONDS", "3600")),
            allow_key_management=_bool_env("RELIABILITY_GRAPH_ALLOW_KEY_MANAGEMENT", not public_demo),
            cookie_secure=_bool_env("RELIABILITY_GRAPH_COOKIE_SECURE", public_demo),
        )


ENV_KEY_BY_PROVIDER: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "tinker": "TINKER_API_KEY",
}

ENV_KEY_BY_SEARCH_PROVIDER: Dict[str, str] = {
    "tavily": "TAVILY_API_KEY",
}


settings = Settings.from_env()
