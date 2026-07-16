-- Cortex-Local: Initial database schema
-- Enables pgvector extension and creates core tables for document storage.

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Document chunks with embeddings
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding vector(768) NOT NULL,

    -- Source metadata
    source_type VARCHAR(50) NOT NULL,  -- 'confluence', 'git', 'transcript'
    source_id VARCHAR(500) NOT NULL,   -- unique identifier for dedup
    source_url TEXT,

    -- Document metadata
    title VARCHAR(500),
    chunk_index INTEGER NOT NULL,
    total_chunks INTEGER,

    -- Source-specific metadata (JSON for flexibility)
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Deduplication constraint
    UNIQUE(source_id, chunk_index)
);

-- Index for vector similarity search (ivfflat with cosine distance)
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Index for source filtering
CREATE INDEX idx_chunks_source_type ON document_chunks(source_type);
CREATE INDEX idx_chunks_source_id ON document_chunks(source_id);

-- Collections/sources tracking
CREATE TABLE ingestion_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(50) NOT NULL,
    name VARCHAR(500) NOT NULL,
    config JSONB DEFAULT '{}',
    last_ingested_at TIMESTAMP WITH TIME ZONE,
    chunk_count INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
