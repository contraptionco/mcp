from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    chroma_tenant: str = Field(description="Chroma Cloud tenant ID")
    chroma_database: str = Field(description="Chroma database name")
    chroma_api_key: str = Field(description="Chroma API key")
    chroma_collection: str = Field(default="posts", description="Chroma collection name")

    ghost_admin_api_key: str = Field(description="Ghost Admin API key")
    ghost_api_url: str = Field(description="Ghost API URL")
    webhook_secret: str = Field(description="Secret token for webhook URL validation")

    chunk_size: int = Field(default=500, description="Maximum chunk size in words")
    chunk_overlap: int = Field(default=50, description="Overlap between chunks in words")

    max_posts_per_page: int = Field(default=10, description="Maximum posts per page")
    search_top_k: int = Field(default=10, description="Number of search results to return")

    dense_query_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight applied to dense similarity during hybrid search",
    )
    sparse_query_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight applied to sparse similarity during hybrid search",
    )
    hybrid_rrf_k: float = Field(
        default=42.0,
        gt=0.0,
        description="Reciprocal rank fusion k parameter for hybrid search",
    )

    @model_validator(mode="after")
    def _validate_query_weights(self) -> "Settings":
        if self.dense_query_weight == 0 and self.sparse_query_weight == 0:
            raise ValueError(
                "At least one of dense_query_weight or sparse_query_weight must be > 0"
            )
        return self


settings = Settings()  # values pulled from environment at runtime
