from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ContentType = Literal["post", "page"]


class GhostPost(BaseModel):
    id: str
    slug: str
    title: str
    html: str | None = None
    plaintext: str | None = None
    feature_image: str | None = None
    excerpt: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    tags: list[dict[str, Any]] = Field(default_factory=list)
    authors: list[dict[str, Any]] = Field(default_factory=list)
    url: str | None = None
    custom_excerpt: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None


class PostChunk(BaseModel):
    post_id: str
    post_slug: str
    post_title: str
    post_url: str
    chunk_text: str
    chunk_index: int
    total_chunks: int
    content_type: ContentType = "post"
    content_hash: str | None = None
    published_at: datetime | None
    updated_at: datetime | None
    tags: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)


class PostSummary(BaseModel):
    id: str
    slug: str
    title: str
    excerpt: str | None
    url: str
    published_at: datetime | None
    updated_at: datetime | None
    content_type: ContentType = "post"
    tags: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    post_slug: str
    post_title: str
    post_url: str
    excerpt: str
    relevance_score: float
    published_at: datetime | None
    content_type: ContentType = "post"
    tags: list[str] = Field(default_factory=list)


class WebhookPayload(BaseModel):
    post: dict[str, Any]
