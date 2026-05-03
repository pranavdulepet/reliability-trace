from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


KEY_PROVIDERS = ["openai", "anthropic", "gemini", "openrouter", "tinker"]
RUN_PROVIDERS = ["preview", "local"] + KEY_PROVIDERS


class ProviderKeyCreate(BaseModel):
    provider: str
    api_key: str = Field(min_length=4, max_length=5000)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        provider = value.lower().strip()
        if provider not in KEY_PROVIDERS:
            raise ValueError("unsupported provider")
        return provider


class ProviderKeyView(BaseModel):
    provider: str
    fingerprint: str
    status: str
    created_at: str
    last_used_at: Optional[str] = None


class RunCreate(BaseModel):
    question: str = Field(min_length=3, max_length=12000)
    provider: str = "preview"
    model: Optional[str] = Field(default=None, max_length=500)
    samples: int = Field(default=3, ge=1, le=5)
    max_cost_usd: float = Field(default=1.0, ge=0.0, le=100.0)
    use_live_provider: bool = False

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        provider = value.lower().strip()
        if provider not in RUN_PROVIDERS:
            raise ValueError("unsupported provider")
        return provider


class RunView(BaseModel):
    run_id: str
    question: str
    provider: str
    model: Optional[str]
    samples: int
    max_cost_usd: float
    use_live_provider: bool
    status: str
    created_at: str
    completed_at: Optional[str] = None
    graph: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class RunLabelCreate(BaseModel):
    usefulness: Optional[int] = Field(default=None, ge=1, le=5)
    correctness: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=4000)


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=20, max_length=1_000_000)
    source_url: Optional[str] = Field(default=None, max_length=2000)
    source_type: str = Field(default="uploaded_document", max_length=80)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value.strip() == "":
            return None
        url = value.strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("source_url must be http or https")
        return url


class SourceFetchCreate(BaseModel):
    url: str = Field(min_length=8, max_length=2000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        url = value.strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("url must be http or https")
        return url


class ProviderMetadata(BaseModel):
    provider: str
    label: str
    default_model: Optional[str]
    key_env_var: Optional[str]
    key_state: str
    capabilities: List[str]
