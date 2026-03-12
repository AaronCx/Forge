-- v1.6.0: Knowledge Base + RAG
-- Document storage, chunks with embeddings, knowledge collections

-- ========================================
-- Knowledge Collections
-- ========================================
CREATE TABLE IF NOT EXISTS knowledge_collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    embedding_model TEXT DEFAULT 'text-embedding-3-small',
    chunk_size INTEGER DEFAULT 1000,
    chunk_overlap INTEGER DEFAULT 200,
    document_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_collections_user ON knowledge_collections(user_id);

ALTER TABLE knowledge_collections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own collections"
    ON knowledge_collections FOR ALL
    USING (auth.uid() = user_id);

-- ========================================
-- Knowledge Documents
-- ========================================
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    collection_id UUID NOT NULL REFERENCES knowledge_collections(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT DEFAULT 'text/plain',
    file_size INTEGER DEFAULT 0,
    raw_text TEXT DEFAULT '',
    chunk_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    -- status: pending, processing, ready, error
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_documents_collection ON knowledge_documents(collection_id);
CREATE INDEX idx_knowledge_documents_user ON knowledge_documents(user_id);
CREATE INDEX idx_knowledge_documents_status ON knowledge_documents(status);

ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own documents"
    ON knowledge_documents FOR ALL
    USING (auth.uid() = user_id);

-- ========================================
-- Knowledge Chunks (with embedding as JSONB array)
-- ========================================
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    collection_id UUID NOT NULL REFERENCES knowledge_collections(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    embedding JSONB,
    -- Stores embedding vector as JSON array for cosine similarity search
    token_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_chunks_document ON knowledge_chunks(document_id);
CREATE INDEX idx_knowledge_chunks_collection ON knowledge_chunks(collection_id);
CREATE INDEX idx_knowledge_chunks_user ON knowledge_chunks(user_id);

ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own chunks"
    ON knowledge_chunks FOR ALL
    USING (auth.uid() = user_id);
