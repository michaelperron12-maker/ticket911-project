-- ScanTicket V1 — Setup pgvector
-- Executer avec: psql -U n8n -d tickets_qc_on -f setup_pgvector.sql

-- Extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Colonne embedding (si pas deja fait)
ALTER TABLE jurisprudence ADD COLUMN IF NOT EXISTS embedding vector(4096);

-- Index HNSW pour recherche rapide (cosine distance)
-- m=16, ef_construction=64 = bon compromis qualite/vitesse pour <100K docs
CREATE INDEX IF NOT EXISTS idx_jurisprudence_embedding_hnsw
ON jurisprudence
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Permissions
GRANT USAGE ON SCHEMA public TO ticketdb_user;
GRANT ALL ON ALL TABLES IN SCHEMA public TO ticketdb_user;

-- Verification
SELECT 'pgvector' AS check, extversion FROM pg_extension WHERE extname = 'vector'
UNION ALL
SELECT 'embedding_column', data_type FROM information_schema.columns
WHERE table_name = 'jurisprudence' AND column_name = 'embedding'
UNION ALL
SELECT 'hnsw_index', indexname FROM pg_indexes
WHERE tablename = 'jurisprudence' AND indexname LIKE '%embedding%';
