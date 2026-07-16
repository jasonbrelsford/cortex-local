"""Async embedding client for the nomic-embed-text-v1.5 service.

Calls the OpenAI-compatible /v1/embeddings endpoint to generate
768-dimensional vectors from text input.
"""

import httpx


class EmbeddingError(Exception):
    """Raised when the embedding service returns an error."""


class EmbeddingClient:
    """Async client for the embedding service."""

    def __init__(
        self,
        base_url: str = "http://nomic-embed:11435",
        model: str = "nomic-embed-text-v1.5",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string, returns 768-dim vector."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text strings, returns list of 768-dim vectors."""
        if not texts:
            return []

        client = await self._get_client()
        url = f"{self.base_url}/v1/embeddings"
        payload = {
            "input": texts,
            "model": self.model,
        }

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise EmbeddingError(
                f"Embedding service returned {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise EmbeddingError(
                f"Failed to connect to embedding service at {self.base_url}: {e}"
            ) from e

        data = response.json()
        # Sort by index to ensure correct ordering
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in embeddings]

    async def __aenter__(self) -> "EmbeddingClient":
        await self._get_client()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
