"""Tests for the embedding client and vector store.

These tests run against the mock embedding server and a real PostgreSQL
instance. Start services first: docker compose up -d postgres nomic-embed
"""

import math
import os
import sys

import pytest

# Add source path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.embeddings import EmbeddingClient, EmbeddingError
from src.models import DocumentChunk
from src.vector_store import PgvectorStore

# Test configuration — uses localhost for running outside Docker
EMBEDDING_URL = os.getenv("EMBEDDING_MODEL_URL", "http://localhost:11435")
POSTGRES_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://cortex:cortex_dev_password@localhost:5433/cortex",
)


@pytest.fixture
async def embed_client():
    """Create an embedding client for tests."""
    client = EmbeddingClient(base_url=EMBEDDING_URL)
    yield client
    await client.close()


@pytest.fixture
async def vector_store():
    """Create a vector store and clean up test data after."""
    store = PgvectorStore(dsn=POSTGRES_DSN)
    await store.connect()
    yield store
    # Clean up test data
    pool = await store._get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM document_chunks WHERE source_id LIKE 'test-%'")
    await store.close()


class TestEmbeddingClient:
    """Tests for the EmbeddingClient."""

    @pytest.mark.asyncio
    async def test_embed_text_returns_768_dims(self, embed_client: EmbeddingClient):
        """embed_text returns a list of exactly 768 floats."""
        result = await embed_client.embed_text("hello world")
        assert isinstance(result, list)
        assert len(result) == 768
        assert all(isinstance(v, float) for v in result)

    @pytest.mark.asyncio
    async def test_embed_text_deterministic(self, embed_client: EmbeddingClient):
        """Same input text always produces the same vector."""
        v1 = await embed_client.embed_text("deterministic test")
        v2 = await embed_client.embed_text("deterministic test")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_embed_text_different_inputs_differ(self, embed_client: EmbeddingClient):
        """Different input texts produce different vectors."""
        v1 = await embed_client.embed_text("hello world")
        v2 = await embed_client.embed_text("goodbye moon")
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_embed_batch_returns_correct_count(self, embed_client: EmbeddingClient):
        """embed_batch returns one 768-dim vector per input text."""
        texts = ["alpha", "beta", "gamma"]
        results = await embed_client.embed_batch(texts)
        assert len(results) == 3
        for vec in results:
            assert len(vec) == 768

    @pytest.mark.asyncio
    async def test_embed_batch_empty_input(self, embed_client: EmbeddingClient):
        """embed_batch with empty list returns empty list."""
        results = await embed_client.embed_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_embed_text_is_normalized(self, embed_client: EmbeddingClient):
        """Embedding vectors should be unit-normalized."""
        vec = await embed_client.embed_text("normalize test")
        magnitude = math.sqrt(sum(v * v for v in vec))
        assert abs(magnitude - 1.0) < 0.01, f"Expected magnitude ~1.0, got {magnitude}"

    @pytest.mark.asyncio
    async def test_connection_error_raises(self):
        """Connection to non-existent server raises EmbeddingError."""
        client = EmbeddingClient(base_url="http://localhost:99999")
        with pytest.raises(EmbeddingError):
            await client.embed_text("test")
        await client.close()


class TestPgvectorStore:
    """Tests for the PgvectorStore."""

    @pytest.mark.asyncio
    async def test_store_and_search(self, vector_store: PgvectorStore, embed_client: EmbeddingClient):
        """Stored vectors are retrievable via cosine similarity search."""
        text = "donor search process"
        embedding = await embed_client.embed_text(text)

        chunk = DocumentChunk(
            content=text,
            embedding=embedding,
            source_type="confluence",
            source_id="test-001",
            source_url="http://example.com/test",
            title="Test Document",
            chunk_index=0,
            total_chunks=1,
        )
        await vector_store.store([chunk])

        # Search with the same embedding
        results = await vector_store.search(embedding, top_k=1)
        assert len(results) >= 1
        assert results[0].content == text
        assert results[0].score > 0.99  # Same vector should be ~1.0

    @pytest.mark.asyncio
    async def test_search_ranking(self, vector_store: PgvectorStore, embed_client: EmbeddingClient):
        """Search with the same embedding as a stored doc ranks it highest (score ~1.0).

        Note: The mock embedding server uses hash-based vectors, not semantic ones,
        so we test ranking by searching with the exact text of one stored document.
        With a real model, "donor search" would rank "donor matching" higher than "weather."
        """
        donor_text = "Finding a matching donor for transplant"
        weather_text = "The weather forecast shows rain tomorrow"

        donor_emb = await embed_client.embed_text(donor_text)
        weather_emb = await embed_client.embed_text(weather_text)

        chunks = [
            DocumentChunk(
                content=donor_text,
                embedding=donor_emb,
                source_type="confluence",
                source_id="test-rank-001",
                title="Donor Matching",
                chunk_index=0,
                total_chunks=1,
            ),
            DocumentChunk(
                content=weather_text,
                embedding=weather_emb,
                source_type="confluence",
                source_id="test-rank-002",
                title="Weather",
                chunk_index=0,
                total_chunks=1,
            ),
        ]
        await vector_store.store(chunks)

        # Search with the exact donor text — its vector should be closest to itself
        query_emb = await embed_client.embed_text(donor_text)
        results = await vector_store.search(query_emb, top_k=10)

        # Find our test docs in results
        donor_result = next((r for r in results if r.source_id == "test-rank-001"), None)
        weather_result = next((r for r in results if r.source_id == "test-rank-002"), None)

        assert donor_result is not None, "Donor doc should be in results"
        assert weather_result is not None, "Weather doc should be in results"
        # Same text → same vector → score ~1.0, always higher than a different hash
        assert donor_result.score > weather_result.score, (
            f"Donor ({donor_result.score:.4f}) should rank higher than weather ({weather_result.score:.4f})"
        )
        assert donor_result.score > 0.99, f"Exact match should be ~1.0, got {donor_result.score:.4f}"

    @pytest.mark.asyncio
    async def test_search_with_source_filter(self, vector_store: PgvectorStore, embed_client: EmbeddingClient):
        """Source type filter limits results to matching type."""
        emb = await embed_client.embed_text("filtered content")
        chunks = [
            DocumentChunk(
                content="Confluence doc",
                embedding=emb,
                source_type="confluence",
                source_id="test-filter-001",
                title="Conf Doc",
                chunk_index=0,
                total_chunks=1,
            ),
            DocumentChunk(
                content="Git file",
                embedding=emb,
                source_type="git",
                source_id="test-filter-002",
                title="Code File",
                chunk_index=0,
                total_chunks=1,
            ),
        ]
        await vector_store.store(chunks)

        results = await vector_store.search(emb, top_k=10, filters={"source_type": "git"})
        for r in results:
            if r.source_id.startswith("test-filter"):
                assert r.source_type == "git"

    @pytest.mark.asyncio
    async def test_delete(self, vector_store: PgvectorStore, embed_client: EmbeddingClient):
        """Delete removes all chunks for a source_id."""
        emb = await embed_client.embed_text("delete me")
        chunk = DocumentChunk(
            content="to be deleted",
            embedding=emb,
            source_type="confluence",
            source_id="test-delete-001",
            title="Delete Test",
            chunk_index=0,
            total_chunks=1,
        )
        await vector_store.store([chunk])

        # Verify it's stored
        results = await vector_store.search(emb, top_k=1)
        assert any(r.source_id == "test-delete-001" for r in results)

        # Delete it
        await vector_store.delete("test-delete-001")

        # Verify it's gone
        results = await vector_store.search(emb, top_k=10)
        assert not any(r.source_id == "test-delete-001" for r in results)

    @pytest.mark.asyncio
    async def test_store_upsert(self, vector_store: PgvectorStore, embed_client: EmbeddingClient):
        """Storing same source_id + chunk_index updates instead of duplicating."""
        emb = await embed_client.embed_text("upsert test")
        chunk = DocumentChunk(
            content="original content",
            embedding=emb,
            source_type="confluence",
            source_id="test-upsert-001",
            title="Upsert Test",
            chunk_index=0,
            total_chunks=1,
        )
        await vector_store.store([chunk])

        # Update content
        chunk.content = "updated content"
        await vector_store.store([chunk])

        results = await vector_store.search(emb, top_k=1)
        matching = [r for r in results if r.source_id == "test-upsert-001"]
        assert len(matching) == 1
        assert matching[0].content == "updated content"
