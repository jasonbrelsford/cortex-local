"""Pydantic models for the MCP Vector Server."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """A chunk of text with its embedding and metadata, ready for storage."""

    content: str
    embedding: list[float] = Field(description="768-dimensional embedding vector")
    source_type: str = Field(description="One of: confluence, git, transcript")
    source_id: str = Field(description="Unique identifier for deduplication")
    source_url: str | None = None
    title: str | None = None
    chunk_index: int = 0
    total_chunks: int | None = None
    metadata: dict = Field(default_factory=dict)


class SearchResult(BaseModel):
    """A single search result from vector similarity search."""

    id: UUID
    content: str
    score: float = Field(description="Cosine similarity score (0-1)")
    source_type: str
    source_id: str
    source_url: str | None = None
    title: str | None = None
    metadata: dict = Field(default_factory=dict)


class Collection(BaseModel):
    """A tracked ingestion source / collection."""

    id: UUID
    source_type: str
    name: str
    config: dict = Field(default_factory=dict)
    last_ingested_at: datetime | None = None
    chunk_count: int = 0
    status: str = "active"
    created_at: datetime | None = None
