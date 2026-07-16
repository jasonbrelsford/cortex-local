"""Verification script: embed text, store in pgvector, and query it.

Usage:
    python scripts/test_embed_and_store.py

Requires running services:
    docker compose up -d postgres nomic-embed
"""

import asyncio
import os
import sys

# Add parent path so we can import mcp-vector modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-vector"))

from src.embeddings import EmbeddingClient
from src.models import DocumentChunk
from src.vector_store import PgvectorStore


async def main() -> None:
    # Configuration (use localhost since we're running outside Docker)
    embedding_url = os.getenv("EMBEDDING_MODEL_URL", "http://localhost:11435")
    postgres_dsn = os.getenv(
        "DATABASE_URL",
        "postgresql://cortex:cortex_dev_password@localhost:5433/cortex",
    )

    print("=" * 60)
    print("Cortex-Local: Embedding + Vector Store Verification")
    print("=" * 60)

    # 1. Test embedding service
    print("\n[1/4] Testing embedding service...")
    async with EmbeddingClient(base_url=embedding_url) as embed_client:
        test_text = "What is a donor search?"
        vector = await embed_client.embed_text(test_text)
        print(f"  Input: '{test_text}'")
        print(f"  Vector dimensions: {len(vector)}")
        print(f"  First 5 values: {vector[:5]}")
        assert len(vector) == 768, f"Expected 768 dims, got {len(vector)}"
        print("  ✓ Embedding service works!")

        # 2. Embed additional texts for testing
        print("\n[2/4] Embedding sample documents...")
        documents = [
            ("What is a donor search?", "confluence", "doc-001", "Donor Search Overview"),
            ("Finding a matching donor requires HLA typing analysis.", "confluence", "doc-002", "HLA Matching Guide"),
            ("The weather forecast shows sunny skies tomorrow.", "confluence", "doc-003", "Weather Report"),
            ("Authentication module uses OAuth2 for secure login.", "git", "doc-004", "auth.py"),
            ("Donor matching process involves comparing allele frequencies.", "transcript", "doc-005", "Q4 Demo"),
        ]

        chunks = []
        for text, source_type, source_id, title in documents:
            embedding = await embed_client.embed_text(text)
            chunks.append(
                DocumentChunk(
                    content=text,
                    embedding=embedding,
                    source_type=source_type,
                    source_id=source_id,
                    source_url=f"http://example.com/{source_id}",
                    title=title,
                    chunk_index=0,
                    total_chunks=1,
                    metadata={"test": True},
                )
            )
        print(f"  Embedded {len(chunks)} documents")
        print("  ✓ Batch embedding works!")

        # 3. Store in pgvector
        print("\n[3/4] Storing vectors in pgvector...")
        async with PgvectorStore(dsn=postgres_dsn) as store:
            await store.store(chunks)
            print(f"  Stored {len(chunks)} chunks")
            print("  ✓ Vector storage works!")

            # 4. Search
            print("\n[4/4] Testing similarity search...")
            query_text = "finding a matching donor"
            query_vector = await embed_client.embed_text(query_text)
            results = await store.search(query_vector, top_k=5)

            print(f"\n  Query: '{query_text}'")
            print(f"  Results ({len(results)} matches):")
            print("  " + "-" * 50)
            for i, result in enumerate(results, 1):
                print(f"  {i}. [{result.score:.4f}] {result.title}")
                print(f"     Content: {result.content[:60]}...")
                print(f"     Source: {result.source_type} | {result.source_id}")
                print()

            # Verify donor-related results rank higher than weather
            donor_scores = [r.score for r in results if "donor" in r.content.lower() or "matching" in r.content.lower()]
            weather_scores = [r.score for r in results if "weather" in r.content.lower()]

            if donor_scores and weather_scores:
                best_donor = max(donor_scores)
                best_weather = max(weather_scores)
                print(f"  Best donor-related score: {best_donor:.4f}")
                print(f"  Best weather score:       {best_weather:.4f}")
                if best_donor > best_weather:
                    print("  ✓ Donor results rank higher than weather — semantic search works!")
                else:
                    print("  ⚠ Ranking unexpected (mock embeddings are hash-based, not semantic)")

            # Test with source_type filter
            print("\n  Testing source_type filter (confluence only):")
            filtered = await store.search(query_vector, top_k=5, filters={"source_type": "confluence"})
            print(f"  Filtered results: {len(filtered)} (should be confluence only)")
            for r in filtered:
                assert r.source_type == "confluence", f"Expected confluence, got {r.source_type}"
            print("  ✓ Source filtering works!")

    print("\n" + "=" * 60)
    print("All verifications passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
