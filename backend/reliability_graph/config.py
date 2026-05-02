import os
from pathlib import Path
from typing import Dict, List, Optional


class Settings:
    def __init__(
        self,
        db_path: Path,
        cors_origins: List[str],
        user_id: str,
        secret: Optional[str],
    ) -> None:
        self.db_path = db_path
        self.cors_origins = cors_origins
        self.user_id = user_id
        self.secret = secret

    @classmethod
    def from_env(cls) -> "Settings":
        db_path = Path(os.getenv("RELIABILITY_GRAPH_DB", "data/reliability_graph.sqlite"))
        cors = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
        )
        return cls(
            db_path=db_path,
            cors_origins=[origin.strip() for origin in cors.split(",") if origin.strip()],
            user_id=os.getenv("RELIABILITY_GRAPH_USER_ID", "local"),
            secret=os.getenv("RELIABILITY_GRAPH_SECRET"),
        )


ENV_KEY_BY_PROVIDER: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "tinker": "TINKER_API_KEY",
}


settings = Settings.from_env()
