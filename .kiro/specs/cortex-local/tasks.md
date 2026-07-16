# Tasks: Cortex-Local

## Task 1: Project Scaffolding and Docker Compose Foundation

**Requirements:** NFR-1, NFR-2, NFR-4, FR-8

**Objective:** Set up the repository structure, Docker Compose stack with PostgreSQL + pgvector, and verify the database starts with vector extension enabled.

**Steps:**
1. Initialize git repo with Apache 2.0 LICENSE, README.md, .gitignore (Python + Docker patterns)
2. Create `docker-compose.yml` with PostgreSQL 16 + pgvector service on port 5432
3. Create `db/migrations/001_initial.sql` with:
   - `CREATE EXTENSION IF NOT EXISTS vector`
   - `document_chunks` table with embedding column (vector(768))
   - `ingestion_sources` table for tracking
   - Indexes for vector search and source filtering
4. Add healthcheck for PostgreSQL in Docker Compose
5. Create `.env.example` with all configuration variables (DB credentials, ports, model URLs)
6. Create initial directory structure for all services (empty `__init__.py` files, placeholder Dockerfiles)

**Tests:**
- [x] `docker compose up -d postgres` starts without errors
- [x] psql connection succeeds with configured credentials
- [x] `SELECT * FROM pg_extension WHERE extname = 'vector'` returns a row
- [x] `\dt` shows `document_chunks` and `ingestion_sources` tables
- [x] Vector column accepts 768-dimension inserts

**Demo:** `docker compose up -d postgres` starts a working pgvector database. Connect with psql and confirm vector extension is active and schema is applied.

---

## Task 2: Embedding Service Integration

**Requirements:** FR-9, FR-8

**Objective:** Create a Python client that calls the local `nomic-embed-text-v1.5` Docker model to generate embeddings, and verify vectors are stored in pgvector.

**Steps:**
1. Add `nomic-embed-text-v1.5` model service to Docker Compose (port 11435, OpenAI-compatible embeddings API)
2. Create `mcp-vector/pyproject.toml` with dependencies (fastapi, httpx, asyncpg, pgvector)
3. Create `mcp-vector/src/embeddings.py` — async client class:
   - `embed_text(text: str) -> list[float]` — single text embedding
   - `embed_batch(texts: list[str]) -> list[list[float]]` — batch embedding
   - Connects to `http://nomic-embed:11435/v1/embeddings`
4. Create `mcp-vector/src/vector_store.py` — `VectorStore` protocol + `PgvectorStore` implementation:
   - `store(chunks: list[DocumentChunk]) -> None`
   - `search(embedding: list[float], top_k: int, filters: dict?) -> list[SearchResult]`
   - `delete(source_id: str) -> None`
5. Create `mcp-vector/tests/test_embeddings.py` — integration test with live embedding service
6. Create a verification script (`scripts/test_embed_and_store.py`) that embeds sample text and queries it

**Tests:**
- [x] Embedding model container starts and responds to `/v1/embeddings` endpoint
- [x] `embed_text("hello world")` returns a list of exactly 768 floats
- [x] `embed_batch(["a", "b", "c"])` returns 3 vectors of 768 dimensions each
- [x] Stored vector retrieves via cosine similarity search
- [x] Search for "donor search" returns higher similarity to "finding a donor" than to "weather forecast"

**Demo:** Run `python scripts/test_embed_and_store.py` — embeds "What is a donor search?", stores in pgvector, queries with "finding a matching donor" and gets a similarity score > 0.7.

---

## Task 3: MCP Vector Server

**Requirements:** FR-4, FR-6, FR-8

**Objective:** Build the first MCP tool server that exposes vector search as an HTTP/REST tool endpoint following the MCP protocol.

**Steps:**
1. Create `mcp-vector/src/main.py` — FastAPI app with MCP tool registration using Anthropic's `mcp` SDK
2. Implement `GET /tools` — returns tool discovery JSON (search_documents, list_collections)
3. Implement `POST /tools/search_documents`:
   - Accepts `{ "query": str, "top_k": int, "source_filter": str? }`
   - Embeds query via embedding service
   - Performs pgvector cosine similarity search
   - Returns ranked results with content, score, and metadata
4. Implement `POST /tools/list_collections` — queries `ingestion_sources` table
5. Create `mcp-vector/Dockerfile` (Python 3.12, uvicorn)
6. Add `mcp-vector` service to Docker Compose (port 8001, depends on postgres + nomic-embed)
7. Create `mcp-vector/tests/test_tools.py` — unit tests with mocked DB

**Tests:**
- [ ] `GET /tools` returns JSON with 2 tools and valid schemas
- [ ] `POST /tools/search_documents` with seeded data returns ranked results
- [ ] Results include `content`, `score`, `metadata.source_type`, `metadata.title`, `metadata.source_url`
- [ ] Empty query returns empty results (not an error)
- [ ] `source_filter` correctly limits results to specified source type
- [ ] Server handles PostgreSQL connection errors gracefully (503 response)

**Demo:** Seed pgvector with 5 sample chunks. `curl -X POST http://localhost:8001/tools/search_documents -d '{"query": "donor matching"}'` returns ranked results with metadata.

---

## Task 4: Ingestion Pipeline — Core Chunking and Storage

**Requirements:** FR-2, FR-3

**Objective:** Build the document chunking engine and storage pipeline that processes raw text into embedded chunks stored in pgvector.

**Steps:**
1. Create `ingestion/pyproject.toml` with dependencies (fastapi, typer, httpx, asyncpg, beautifulsoup4)
2. Create `ingestion/src/chunker.py`:
   - `ChunkingStrategy` enum: FIXED_SIZE, PARAGRAPH, HEADING
   - `chunk_text(text: str, strategy: ChunkingStrategy, chunk_size: int, overlap: int) -> list[TextChunk]`
   - Each `TextChunk` has: content, chunk_index, total_chunks, char_start, char_end
3. Create `ingestion/src/models.py` — Pydantic models for RawDocument, DocumentChunk, IngestionResult
4. Create `ingestion/src/pipeline.py` — orchestrates: fetch → chunk → embed (batch) → store
5. Create `ingestion/src/main.py` — FastAPI app with `POST /ingest` endpoint
6. Create `ingestion/src/cli.py` — Typer CLI: `cortex ingest --source <type> --path <path> --mode <example|live>`
7. Create `ingestion/Dockerfile` and add to Docker Compose (port 8004)
8. Create `ingestion/tests/test_chunker.py` — unit tests for all chunking strategies

**Tests:**
- [ ] Fixed-size chunking: 1000-char doc with chunk_size=300, overlap=50 produces expected chunk count
- [ ] Paragraph chunking: text with `\n\n` delimiters splits at paragraph boundaries
- [ ] Heading chunking: markdown with `#` headers splits at heading boundaries
- [ ] Overlap: adjacent chunks share expected number of characters
- [ ] CLI `cortex ingest --source file --path ./test.md` ingests and stores chunks
- [ ] API `POST /ingest` with same input produces identical chunk count and content
- [ ] Metadata (source_type, chunk_index, total_chunks, ingested_at) is stored correctly

**Demo:** Ingest a sample markdown file via CLI and via API. Query pgvector directly to verify chunks with correct metadata.

---

## Task 5: Ingestion — Confluence Source Connector

**Requirements:** FR-2, FR-3

**Objective:** Build the Confluence data source connector that fetches pages and feeds them into the chunking pipeline. Use example JSON data for development.

**Steps:**
1. Create `example-data/confluence/` with 5-10 sample pages as JSON files:
   - Each file: `{ "id": "...", "title": "...", "space": { "key": "..." }, "body": { "storage": { "value": "<html>..." } }, "metadata": { ... } }`
   - Topics: architecture decisions, onboarding guides, API documentation, troubleshooting
2. Create `ingestion/src/sources/confluence.py`:
   - `ConfluenceConnector(SourceConnector)` class
   - Mode: `example` (reads from example-data JSON) or `live` (calls Confluence REST API)
   - HTML-to-text conversion using BeautifulSoup (strip tags, preserve structure)
   - Metadata extraction: title, space_key, page_id, URL, labels, last_modified
3. Use HEADING chunking strategy for Confluence content (split on `<h1>`, `<h2>`, etc.)
4. Create `ingestion/tests/test_confluence.py` — tests for parsing, metadata extraction, chunking

**Tests:**
- [ ] Example JSON files load without errors
- [ ] HTML `<h1>Title</h1><p>Content</p>` converts to clean text preserving structure
- [ ] Confluence tables render as readable text
- [ ] Metadata extracted correctly: title, space, URL, labels
- [ ] End-to-end: `cortex ingest --source confluence --mode example` stores chunks in pgvector
- [ ] Vector search for terms in example pages returns relevant results with Confluence URLs

**Demo:** `cortex ingest --source confluence --mode example` ingests all sample pages. `curl` the vector server searching for a topic from the examples and get a result with a Confluence page URL as citation.

---

## Task 6: Ingestion — Git Repository Source Connector

**Requirements:** FR-2, FR-3

**Objective:** Build the Git repository connector that indexes code files and documentation from local repos.

**Steps:**
1. Create `example-data/repos/sample-project/` — small Python project:
   - `main.py`, `auth.py`, `models.py`, `utils.py`, `README.md`, `config.yaml`
   - Include docstrings and comments for semantic search targets
2. Create `ingestion/src/sources/git_repo.py`:
   - `GitRepoConnector(SourceConnector)` class
   - Walk directory tree, filter by file extensions (configurable include/exclude patterns)
   - Skip binary files, `.git/`, `node_modules/`, `__pycache__/`
   - For Python: attempt AST-aware chunking (function/class level)
   - For Markdown: heading-based chunking
   - For other text: fixed-size chunking
   - Metadata: repo_name, file_path, language (from extension), commit_hash (if git repo)
3. Create `ingestion/tests/test_git_repo.py`

**Tests:**
- [ ] File discovery walks directory and respects include/exclude patterns
- [ ] Binary files (images, compiled) are skipped
- [ ] `.git/` and `__pycache__/` are excluded
- [ ] Python files chunk at function/class boundaries
- [ ] Markdown files chunk at headings
- [ ] Metadata includes file_path, language, repo_name
- [ ] CLI: `cortex ingest --source git --path ./example-data/repos/sample-project`
- [ ] Search "authentication" returns relevant code from `auth.py`

**Demo:** Ingest the example repo. Search "how does authentication work" via the vector server and get code snippets from `auth.py` with file path citations.

---

## Task 7: Ingestion — Video Transcript Source Connector

**Requirements:** FR-2, FR-3

**Objective:** Build the video transcript connector that parses SRT/VTT subtitle files and indexes them with timestamp metadata.

**Steps:**
1. Create `example-data/transcripts/` with 2-3 sample files:
   - `demo-donor-search.srt` — mock demo recording about donor search workflow
   - `release-notes-q4.vtt` — mock release notes walkthrough
   - Include realistic timestamps and dialogue
2. Create `ingestion/src/sources/transcript.py`:
   - `TranscriptConnector(SourceConnector)` class
   - Parse SRT format: index, timestamp range, text content
   - Parse VTT format: timestamp range, text content (with optional cue settings)
   - Merge strategy: combine segments within configurable time windows (default 30-60 seconds)
   - Metadata: video_title (from filename), timestamp_start, timestamp_end, source_file
3. Create `ingestion/tests/test_transcript.py`

**Tests:**
- [ ] SRT file parses correctly (index, time range, text for each subtitle)
- [ ] VTT file parses correctly (handles WEBVTT header, cue timing)
- [ ] Time-window merging combines 5-second subtitles into 30-60 second chunks
- [ ] Merged chunks maintain accurate start/end timestamps
- [ ] Metadata preserves video title and timestamp range
- [ ] CLI: `cortex ingest --source transcript --path ./example-data/transcripts/`
- [ ] Search "create a new donor" returns transcript chunk with timestamp citation

**Demo:** Ingest sample transcripts. Search for a topic discussed in the mock demo and get results citing "demo-donor-search.srt — 2:34-3:12".

---

## Task 8: MCP Git Server

**Requirements:** FR-4, FR-6

**Objective:** Build the MCP Git tool server that provides real-time code search and file reading capabilities.

**Steps:**
1. Create `mcp-git/pyproject.toml` with dependencies (fastapi, mcp)
2. Create `mcp-git/src/main.py` — FastAPI app with MCP tool registration
3. Implement `GET /tools` — discovery endpoint listing 3 tools
4. Implement `POST /tools/search_code`:
   - Accepts `{ "query": str, "file_pattern": str?, "repo": str? }`
   - Performs recursive grep-style text search across mounted repos
   - Returns matches with file path, line number, surrounding context (2 lines above/below)
5. Implement `POST /tools/read_file`:
   - Accepts `{ "path": str, "start_line": int?, "end_line": int? }`
   - Returns file content with line numbers
   - Validates path is within allowed repo directories (security)
6. Implement `POST /tools/list_files`:
   - Accepts `{ "path": str, "pattern": str? }`
   - Returns directory listing with file types and sizes
7. Create `mcp-git/Dockerfile`, add to Docker Compose (port 8002, volume mount example-data/repos)
8. Create `mcp-git/tests/test_tools.py`

**Tests:**
- [ ] `GET /tools` returns 3 tools with valid schemas
- [ ] `search_code` with query "def authenticate" finds match in auth.py
- [ ] `search_code` with file_pattern "*.py" excludes .md files
- [ ] `read_file` returns content with accurate line numbers
- [ ] `read_file` with path traversal attempt (`../../etc/passwd`) returns 403
- [ ] `list_files` returns directory contents with metadata
- [ ] Missing file returns 404 (not 500)

**Demo:** `curl http://localhost:8002/tools/search_code -d '{"query": "authenticate"}'` returns matches from the example repo with file paths and line numbers.

---

## Task 9: MCP Transcript Server

**Requirements:** FR-4, FR-6

**Objective:** Build the MCP Transcript tool server that provides transcript search with timestamp-aware results.

**Steps:**
1. Create `mcp-transcript/pyproject.toml` with dependencies (fastapi, mcp, httpx, asyncpg)
2. Create `mcp-transcript/src/main.py` — FastAPI app with MCP tool registration
3. Implement `GET /tools` — discovery endpoint listing 2 tools
4. Implement `POST /tools/search_transcripts`:
   - Accepts `{ "query": str, "top_k": int }`
   - Embeds query, performs pgvector search filtered to source_type='transcript'
   - Returns results with video_title, timestamp_start, timestamp_end, content, score
5. Implement `POST /tools/get_transcript_segment`:
   - Accepts `{ "video_id": str, "start_time": float, "end_time": float }`
   - Returns all chunks for that video within the time range (expanded context)
6. Create `mcp-transcript/Dockerfile`, add to Docker Compose (port 8003, depends on postgres + nomic-embed)
7. Create `mcp-transcript/tests/test_tools.py`

**Tests:**
- [ ] `GET /tools` returns 2 tools with valid schemas
- [ ] `search_transcripts` returns results with timestamp metadata
- [ ] Results are filtered to transcript source type only
- [ ] `get_transcript_segment` returns correct chunks for time range
- [ ] Expanded context includes adjacent segments
- [ ] Empty search returns empty results gracefully

**Demo:** With transcript data ingested, `curl http://localhost:8003/tools/search_transcripts -d '{"query": "donor matching process"}'` returns timestamped transcript segments.

---

## Task 10: API Gateway and LLM Orchestration

**Requirements:** FR-5, FR-6, FR-7

**Objective:** Build the central API gateway that receives user queries, sends them to Qwen with MCP tool descriptions, and orchestrates the tool-calling loop.

**Steps:**
1. Create `gateway/pyproject.toml` with dependencies (fastapi, httpx, mcp)
2. Create `gateway/src/models.py` — Pydantic models: QueryRequest, QueryResponse, Citation, ToolCall
3. Create `gateway/src/mcp_router.py`:
   - Discover tools from all MCP servers at startup (`GET /tools` from each)
   - Convert MCP tool schemas to OpenAI function-calling format
   - `execute_tool(server: str, tool_name: str, args: dict) -> dict` — calls MCP server
4. Create `gateway/src/llm_client.py`:
   - Connect to Qwen at `http://qwen:11434/v1/chat/completions`
   - Send messages with tools, handle tool_call responses
   - Implement orchestration loop (max 5 iterations to prevent infinite loops)
5. Create `gateway/src/main.py`:
   - `POST /query` — full query flow with tool orchestration
   - `GET /query/stream` — SSE streaming variant
   - `GET /health` — checks connectivity to LLM + all MCP servers
   - Session management (in-memory dict of conversation histories)
6. Add `docker.io/qwen3:8B-Q4_K_M` to Docker Compose (port 11434)
7. Create `gateway/Dockerfile`, add to Docker Compose (port 8000, depends on all MCP servers + qwen)
8. Create `gateway/tests/test_orchestration.py` — tests with mocked LLM responses

**Tests:**
- [ ] `GET /health` reports all services status
- [ ] Tool discovery aggregates tools from all 3 MCP servers
- [ ] Simple query triggers at least one tool call and returns synthesized answer
- [ ] Response includes citations with source metadata
- [ ] Multi-tool query (needs vector + git) calls both servers
- [ ] Orchestration loop terminates after max iterations
- [ ] LLM timeout returns appropriate error (not hang)
- [ ] Session ID maintains conversation context across requests
- [ ] Unavailable MCP server is excluded from tool list (graceful degradation)

**Demo:** `curl -X POST http://localhost:8000/query -d '{"question": "How does the authentication module work?"}'` returns a synthesized answer citing both code (from git server) and documentation (from vector server).

---

## Task 11: Terminal CLI Chat Client

**Requirements:** FR-7

**Objective:** Build an interactive terminal chat interface that connects to the API gateway.

**Steps:**
1. Create `cli/pyproject.toml` with dependencies (typer, rich, httpx, sseclient-py)
2. Create `cli/src/chat.py`:
   - `cortex chat` command: interactive REPL loop
   - Connect to gateway at configurable URL (default `http://localhost:8000`)
   - Display streaming responses using Rich Live display
   - Format citations in a Rich Panel below the answer
   - Commands: `/sources`, `/clear`, `/quit`, `/help`
3. Create `cli/src/query.py`:
   - `cortex query "question"` — non-interactive single question mode
   - Print answer + citations and exit
4. Update `cli/pyproject.toml` entry point: `cortex = "src.chat:app"`
5. Create `cli/tests/test_chat.py` — test command parsing and response formatting

**Tests:**
- [ ] `cortex query "test"` connects to gateway and prints a response
- [ ] `/quit` exits the REPL cleanly
- [ ] `/clear` resets session (new session_id)
- [ ] `/sources` displays available source types
- [ ] Citations render in a bordered panel with source type indicators
- [ ] Network error (gateway down) displays friendly error message
- [ ] Streaming responses update display progressively

**Demo:** Run `cortex chat`, type "What documents do we have about authentication?", see a streamed response with citations showing source types and links.

---

## Task 12: Web UI

**Requirements:** FR-7

**Objective:** Build a simple web interface for querying the knowledge base.

**Steps:**
1. Create `web-ui/` with Streamlit app:
   - `web-ui/app.py` — main Streamlit application
   - `web-ui/requirements.txt` — streamlit, requests
2. Implement chat interface:
   - Message input at bottom
   - Chat history display (user + assistant messages)
   - Streaming response display using Streamlit's streaming API
3. Implement citations panel:
   - Expandable section below each response
   - Source type icons/badges (Confluence, Code, Transcript)
   - Clickable links for Confluence URLs, file paths for code
   - Timestamp display for transcript citations
4. Implement source filter sidebar:
   - Checkboxes for each source type
   - Pass `source_filter` to gateway API
5. Create `web-ui/Dockerfile` (Python 3.12, streamlit)
6. Add to Docker Compose (port 3000, depends on gateway)

**Tests:**
- [ ] Streamlit app starts without errors
- [ ] Chat input submits to gateway API
- [ ] Response displays in chat format
- [ ] Citations section shows source metadata
- [ ] Source filter checkboxes pass filter to API
- [ ] Conversation history persists within session
- [ ] UI handles gateway errors gracefully (displays error message)

**Demo:** Open `http://localhost:3000` in browser, type a question, see formatted response with expandable citations section showing sources from Confluence, code, and transcripts.

---

## Task 13: End-to-End Integration Testing and Documentation

**Requirements:** NFR-1, NFR-2, NFR-6

**Objective:** Verify the complete stack works together, write user documentation, and create a one-command startup experience.

**Steps:**
1. Create `Makefile` with targets:
   - `make setup` — pull models, build containers, start stack, run migrations, ingest example data
   - `make start` — start all services (assumes setup done)
   - `make stop` — stop all services
   - `make test` — run all unit tests
   - `make test-integration` — run integration tests against running stack
   - `make clean` — remove containers, volumes, generated data
2. Create `scripts/start.sh` — shell script alternative to Makefile
3. Create integration test suite (`tests/integration/`):
   - `test_full_query_path.py` — query that exercises all 3 MCP servers
   - `test_ingestion_pipeline.py` — ingest from all sources, verify searchable
   - `test_health_endpoints.py` — all services report healthy
4. Write `README.md`:
   - Project overview and architecture diagram
   - Quickstart (prerequisites: Docker, ~16GB RAM)
   - Configuration guide (.env variables)
   - Usage examples (CLI, API, Web UI)
   - Development setup
5. Write `docs/contributing.md`:
   - Development environment setup
   - How to add a new MCP server
   - How to add a new ingestion source
   - Testing guidelines
   - PR process
6. Add GitHub Actions workflow (`.github/workflows/ci.yml`):
   - Lint with ruff
   - Run unit tests for all services
   - Build all Docker images

**Tests:**
- [ ] Fresh clone → `make setup` → all services running in under 5 minutes (excluding model download)
- [ ] `make test` passes all unit tests across all services
- [ ] Integration: ingest all example data sources without errors
- [ ] Integration: query "authentication" returns results from both code and docs
- [ ] Integration: query about a topic in transcripts returns timestamped citation
- [ ] `GET /health` on gateway reports all services green
- [ ] GitHub Actions CI passes on a clean run

**Demo:** Clone the repo on a fresh machine, run `make setup`, wait for startup, open the web UI, ask "How does donor matching work?" and get a comprehensive answer citing Confluence docs, code files, and demo transcript timestamps.
