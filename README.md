# Cortex-Local

A self-hosted, local-first RAG (Retrieval-Augmented Generation) system that provides a unified AI-powered interface to query internal knowledge across multiple sources — without sending data to external cloud services.

## Architecture

Cortex-Local uses a modular MCP (Model Context Protocol) microservices architecture where a local LLM orchestrates queries across specialized tool servers:

- **API Gateway** — Central entry point, LLM orchestration loop
- **MCP Vector Server** — Semantic search over pgvector embeddings
- **MCP Git Server** — Real-time code search across local repos
- **MCP Transcript Server** — Timestamp-aware transcript search
- **Ingestion Service** — Multi-source document processing pipeline

## Prerequisites

- Docker Desktop (with Docker Compose v2)
- ~16GB RAM available
- macOS or Linux

## Quickstart

```bash
# Clone the repository
git clone <repo-url> cortex-local
cd cortex-local

# Copy environment config
cp .env.example .env

# Start all services (pulls models on first run)
docker compose up -d

# Verify database is ready
docker compose exec postgres psql -U cortex -d cortex -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL + pgvector | 5432 | Vector storage and metadata |
| Qwen 3 8B | 11434 | Local LLM inference |
| nomic-embed-text | 11435 | Local embedding generation |
| API Gateway | 8000 | Query orchestration |
| MCP Vector | 8001 | Semantic search tools |
| MCP Git | 8002 | Code search tools |
| MCP Transcript | 8003 | Transcript search tools |
| Ingestion | 8004 | Document processing |
| Web UI | 3000 | Browser chat interface |

## Configuration

See `.env.example` for all configuration variables.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
