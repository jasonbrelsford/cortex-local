"""
Mock Embedding Server — deterministic OpenAI-compatible embedding API.

Returns 768-dimensional vectors based on a hash of the input text,
so the same input always produces the same output. This enables
development and testing without a real model or GPU.
"""

import hashlib
import math
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Mock Embedding Server", version="0.1.0")


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str = "nomic-embed-text-v1.5"
    encoding_format: str = "float"


class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: list[float]
    index: int


class EmbeddingUsage(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingData]
    model: str
    usage: EmbeddingUsage


def text_to_vector(text: str, dimensions: int = 768) -> list[float]:
    """Generate a deterministic 768-dim unit vector from text using SHA-256 hash.

    The same input text always produces the same vector.
    Vectors are normalized to unit length for cosine similarity.
    """
    # Use SHA-256 to generate enough bytes for 768 dimensions
    # We need multiple hashes since SHA-256 only gives 32 bytes (256 bits)
    vectors: list[float] = []
    block = 0
    while len(vectors) < dimensions:
        hash_input = f"{text}::{block}".encode("utf-8")
        digest = hashlib.sha256(hash_input).digest()
        # Convert each byte to a float in [-1, 1]
        for byte in digest:
            if len(vectors) >= dimensions:
                break
            vectors.append((byte / 127.5) - 1.0)
        block += 1

    # Normalize to unit vector (required for cosine similarity)
    magnitude = math.sqrt(sum(v * v for v in vectors))
    if magnitude > 0:
        vectors = [v / magnitude for v in vectors]

    return vectors


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(request: EmbeddingRequest) -> dict[str, Any]:
    """OpenAI-compatible embeddings endpoint."""
    # Normalize input to list
    texts = request.input if isinstance(request.input, list) else [request.input]

    if not texts:
        raise HTTPException(status_code=400, detail="Input must not be empty")

    data = []
    total_tokens = 0
    for i, text in enumerate(texts):
        embedding = text_to_vector(text)
        data.append({"object": "embedding", "embedding": embedding, "index": i})
        # Rough token count approximation
        total_tokens += len(text.split())

    return {
        "object": "list",
        "data": data,
        "model": request.model,
        "usage": {"prompt_tokens": total_tokens, "total_tokens": total_tokens},
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """List available models (OpenAI-compatible)."""
    return {
        "object": "list",
        "data": [
            {
                "id": "nomic-embed-text-v1.5",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "mock",
            }
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=11435)
