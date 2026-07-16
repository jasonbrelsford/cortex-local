# Requirements: Cortex-Local

## Overview

Cortex-Local is a self-hosted, local-first RAG (Retrieval-Augmented Generation) system that provides a unified AI-powered interface to query internal knowledge across multiple sources — without sending data to external cloud services. It uses a modular MCP (Model Context Protocol) architecture for extensibility.

## Functional Requirements

### FR-1: Local LLM Inference
- **Description:** The system must run all LLM inference locally using a containerized model.
- **Details:** Uses `docker.io/qwen3:8B-Q4_K_M` as the local inference engine. No queries or data are sent to external cloud AI services.
- **Acceptance Criteria:**
  - LLM container starts and accepts OpenAI-compatible API requests
  - Responses are generated entirely on the local machine
  - No outbound network calls to AI providers

### FR-2: Multi-Source Data Ingestion
- **Description:** The system must ingest and index content from three source types: Confluence pages, Git repositories, and video transcripts.
- **Details:** Each source has a dedicated connector. Initial development uses example/mock data; live source integration is deferred.
- **Acceptance Criteria:**
  - Confluence HTML pages are parsed, chunked, embedded, and stored
  - Git repo files (.py, .md, .yaml, etc.) are indexed with file-level metadata
  - SRT/VTT transcript files are parsed with timestamp metadata preserved
  - All sources produce searchable vector embeddings in pgvector

### FR-3: Ingestion via CLI and API
- **Description:** Ingestion must be triggerable via both a command-line interface and a REST API.
- **Details:** The CLI wraps the same core library as the API. Both produce identical results for the same input.
- **Acceptance Criteria:**
  - CLI command `cortex ingest --source <type> --path <path>` ingests documents
  - API endpoint `POST /ingest` accepts source configuration and triggers ingestion
  - Both interfaces report progress and errors consistently

### FR-4: MCP Tool Server Architecture
- **Description:** The system must use the Model Context Protocol (MCP) to structure retrieval as modular, independent tool servers.
- **Details:** Each data source domain (vector search, git, transcripts) is a separate HTTP/REST service that the LLM can invoke as tools.
- **Acceptance Criteria:**
  - MCP Vector Server exposes `search_documents` and `list_collections` tools
  - MCP Git Server exposes `search_code`, `read_file`, and `list_files` tools
  - MCP Transcript Server exposes `search_transcripts` and `get_transcript_segment` tools
  - All servers register tools via Anthropic's `mcp` Python SDK
  - LLM can discover and invoke tools dynamically

### FR-5: API Gateway with LLM Orchestration
- **Description:** A central gateway receives user queries, routes them to the LLM, orchestrates tool calls, and returns synthesized answers.
- **Details:** The gateway manages the tool-calling loop: LLM decides which tools to call, gateway executes them, returns context to LLM for final synthesis.
- **Acceptance Criteria:**
  - `/query` endpoint accepts natural language questions
  - Gateway constructs system prompt with available MCP tools
  - Multi-tool queries invoke multiple MCP servers as needed
  - Final response includes synthesized answer with source citations
  - Multi-turn conversation context is maintained per session

### FR-6: Source Citations
- **Description:** Every response must include verifiable citations linking to the original source material.
- **Details:** Citations include metadata sufficient to locate the original content: page URLs for Confluence, file paths + line numbers for code, video title + timestamps for transcripts.
- **Acceptance Criteria:**
  - Confluence results cite page title, space, and URL
  - Git results cite repository name, file path, and line range
  - Transcript results cite video title and timestamp range
  - Citations are displayed in all interfaces (API, CLI, Web UI)

### FR-7: Multiple Query Interfaces
- **Description:** Users can query the system through three interfaces: REST API, terminal CLI, and web UI.
- **Details:** All interfaces hit the same API gateway backend. The CLI provides an interactive chat REPL. The web UI provides a browser-based chat interface.
- **Acceptance Criteria:**
  - REST API: `POST /query` returns JSON response with answer and citations
  - Terminal CLI: Interactive REPL with streaming responses and formatted citations
  - Web UI: Browser-based chat with message history and clickable citation links
  - Source filtering available (search only specific source types)

### FR-8: Vector Storage with Pgvector
- **Description:** Document embeddings are stored in PostgreSQL using the pgvector extension.
- **Details:** A `VectorStore` abstraction interface allows future backends (Qdrant, Milvus) without changing application code.
- **Acceptance Criteria:**
  - PostgreSQL 16 with pgvector extension stores 768-dimension vectors
  - Cosine similarity search returns ranked results
  - Metadata (source type, URL, title, timestamps) stored alongside vectors
  - Abstraction layer enables backend swaps via configuration

### FR-9: Local Embedding Generation
- **Description:** Text-to-vector embedding is performed locally using a containerized embedding model.
- **Details:** Uses `nomic-embed-text-v1.5` running as a Docker model, producing 768-dimension vectors.
- **Acceptance Criteria:**
  - Embedding model container starts and accepts text input
  - Produces consistent 768-dim vectors for the same input
  - Handles batch embedding for ingestion efficiency
  - No external API calls for embedding generation

## Non-Functional Requirements

### NFR-1: Fully Containerized
- **Description:** The entire system runs via Docker Compose with no host-level dependencies beyond Docker.
- **Acceptance Criteria:**
  - `docker compose up` starts all services
  - No manual installation steps required on the host
  - Works on macOS and Linux

### NFR-2: One-Command Startup
- **Description:** A fresh clone should reach a working state with a single command (excluding model download time).
- **Acceptance Criteria:**
  - `make setup` or `./start.sh` handles model pulls, container startup, migrations, and example data ingestion
  - System is queryable within 5 minutes of startup (excluding model download)

### NFR-3: Small Footprint
- **Description:** The system must be runnable on a developer laptop without dedicated GPU hardware.
- **Acceptance Criteria:**
  - Total idle RAM usage under 8GB (including LLM model)
  - Qwen 3 8B Q4_K_M quantization enables CPU inference
  - Example data set is small enough to ingest in under 60 seconds

### NFR-4: Apache 2.0 License
- **Description:** The project is licensed under Apache 2.0 to maximize adoption and preserve future commercial options.
- **Acceptance Criteria:**
  - LICENSE file contains Apache 2.0 text
  - All source files include appropriate headers
  - No dependencies with incompatible licenses (GPL, AGPL)

### NFR-5: Extensibility
- **Description:** New data sources and backends can be added without modifying existing code.
- **Acceptance Criteria:**
  - Adding a new MCP server requires only deploying a new container and registering it
  - Adding a new vector backend requires implementing the `VectorStore` interface
  - Adding a new ingestion source requires implementing a source connector class

### NFR-6: Testability
- **Description:** All components must be independently testable.
- **Acceptance Criteria:**
  - Unit tests for chunking, parsing, and embedding logic
  - Integration tests for each MCP server independently
  - End-to-end test for the full query path
  - CI pipeline runs linting and tests on every push

## Constraints

- LLM model: `docker.io/qwen3:8B-Q4_K_M` (fixed for v1)
- Embedding model: `nomic-embed-text-v1.5` (fixed for v1)
- Vector DB: PostgreSQL 16 + pgvector (primary for v1)
- MCP transport: HTTP/REST (stdio deferred to post-v1)
- Language: Python 3.12+
- Framework: FastAPI + Anthropic `mcp` SDK (no LangChain)
- Initial data: Example/mock only — live Confluence/repo integration deferred
