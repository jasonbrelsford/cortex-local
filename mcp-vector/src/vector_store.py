"""Vector store abstraction and pgvector implementation.

Provides a protocol-based interface so alternative backends
(Qdrant, Milvus, etc.) can be swapped in via configuration.
"""

import json
from typing import Protocol
from uuid import UUID

import asyncpg

from .models import Collection, DocumentChunk, SearchResult


class VectorStore(Protocol):
    """Protocol defining the vector store interface."""

    async def store(self, chunks: list[DocumentChunk]) -> None:
        """Store document chunks with their embeddings."""
        ...

    async def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Search for similar vectors using cosine similarity."""
        ...

    async def delete(self, source_id: str) -> None:
        """Delete all chunks for a given source_id."""
        ...

    async def list_collections(self) -> list[Collection]:
        """List all tracked ingestion sources."""
        ...


class PgvectorStore:
    """PostgreSQL + pgvector implementation of VectorStore."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Initialize the connection pool."""

        async def _init_connection(conn: asyncpg.Connection) -> None:
            """Set up JSONB codec for each new connection."""
            await conn.set_type_codec(
                "jsonb",
                encoder=json.dumps,
                decoder=json.loads,
                schema="pg_catalog",
            )

        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=2,
            max_size=10,
            command_timeout=30,
            init=_init_connection,
        )
        # Ensure pgvector extension exists
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            await self.connect()
        return self._pool  # type: ignore

    async def store(self, chunks: list[DocumentChunk]) -> None:
        """Store document chunks with their embeddings."""
        if not chunks:
            return

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Use a transaction for atomic batch insert
            async with conn.transaction():
                for chunk in chunks:
                    embedding_str = "[" + ",".join(str(v) for v in chunk.embedding) + "]"
                    await conn.execute(
                        """
                        INSERT INTO document_chunks
                            (content, embedding, source_type, source_id, source_url,
                             title, chunk_index, total_chunks, metadata)
                        VALUES ($1, $2::vector, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (source_id, chunk_index)
                        DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            source_url = EXCLUDED.source_url,
                            title = EXCLUDED.title,
                            total_chunks = EXCLUDED.total_chunks,
                            metadata = EXCLUDED.metadata,
                            updated_at = NOW()
                        """,
                        chunk.content,
                        embedding_str,
                        chunk.source_type,
                        chunk.source_id,
                        chunk.source_url,
                        chunk.title,
                        chunk.chunk_index,
                        chunk.total_chunks,
                        chunk.metadata if chunk.metadata else {},
                    )

    async def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Search for similar vectors using cosine similarity."""
        pool = await self._get_pool()
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        # Build filter clause
        where_clauses = []
        params: list = [embedding_str, top_k]
        param_idx = 3

        if filters:
            if "source_type" in filters:
                where_clauses.append(f"source_type = ${param_idx}")
                params.append(filters["source_type"])
                param_idx += 1

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        query = f"""
            SELECT
                id, content, source_type, source_id, source_url,
                title, metadata,
                1 - (embedding <=> $1::vector) AS score
            FROM document_chunks
            {where_sql}
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        results = []
        for row in rows:
            results.append(
                SearchResult(
                    id=row["id"],
                    content=row["content"],
                    score=float(row["score"]),
                    source_type=row["source_type"],
                    source_id=row["source_id"],
                    source_url=row["source_url"],
                    title=row["title"],
                    metadata=row["metadata"] if row["metadata"] else {},
                )
            )
        return results

    async def delete(self, source_id: str) -> None:
        """Delete all chunks for a given source_id."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM document_chunks WHERE source_id = $1",
                source_id,
            )

    async def list_collections(self) -> list[Collection]:
        """List all tracked ingestion sources."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, source_type, name, config, last_ingested_at,
                       chunk_count, status, created_at
                FROM ingestion_sources
                ORDER BY created_at DESC
                """
            )

        return [
            Collection(
                id=row["id"],
                source_type=row["source_type"],
                name=row["name"],
                config=row["config"] if row["config"] else {},
                last_ingested_at=row["last_ingested_at"],
                chunk_count=row["chunk_count"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def __aenter__(self) -> "PgvectorStore":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
