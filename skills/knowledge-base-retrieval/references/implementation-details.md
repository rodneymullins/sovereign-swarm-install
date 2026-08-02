# Knowledge Base Implementation — Session Artifacts

## Schema (SQLite)
```sql
-- Parent table: full document metadata
CREATE TABLE knowledge_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_path TEXT,
    domain TEXT,
    title TEXT,
    full_text TEXT,
    metadata TEXT,
    created_at INTEGER,
    updated_at INTEGER,
    UNIQUE(source, source_id)
);

-- Child table: sections with contextualized text
CREATE TABLE knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES knowledge_documents(id),
    section_heading TEXT,
    chunk_index INTEGER,
    contextual_text TEXT,
    question TEXT,
    summary TEXT,
    resolution TEXT,
    systems TEXT,
    code_refs TEXT,
    embedding BLOB,
    char_count INTEGER,
    created_at INTEGER
);

-- FTS5 index on contextualized text
CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    contextual_text, question, summary, resolution,
    content='knowledge_chunks',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Sync tracking
CREATE TABLE knowledge_sync (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    file_hash TEXT,
    last_synced INTEGER,
    PRIMARY KEY(source, source_id)
);
```

## Scripts

### `knowledge_distill.py` — Vault Distillation
- Reads all `.md` files from `08-Tools/References/`
- Parses frontmatter (title, tags, created, updated)
- Extracts sections by `##` headings
- Generates contextual text: `"This section is from [title]. Section: [heading]. Tags: [tags]."`
- Generates structured artifacts: question, summary, resolution, code_refs
- Writes parent to `knowledge_documents`, children to `knowledge_chunks`
- Tracks file hashes in `knowledge_sync` for incremental updates
- Rebuilds FTS index after insert

### `knowledge_embed_v3.py` — MLX Embeddings
- Loads `mlx-community/functiongemma-270m-it-8bit` (304MB, 640-dim hidden states)
- For each chunk, passes `contextual_text` through the model
- Extracts hidden states from the last transformer layer (before lm_head)
- Mean-pools over content tokens (skipping BOS/EOS)
- Normalizes to unit vector
- Stores as numpy float32 blob
- 513 chunks in 7.6 seconds

### `knowledge_search.py` — Hybrid Search
- **Retriever 1: FTS5** — SQLite FTS5 BM25 ranking over contextual_text
- **Retriever 2: MLX Vector** — loads functiongemma-270m once (singleton), embeds query, compares against all stored embeddings via dot product
- **RRF Fusion** — `score = 1.0 / (60 + rank)` per retriever, combined
- **Domain filter** — SQL WHERE d.domain = ?
- **Source filter** — SQL WHERE d.source = ?
- MLX model cached in global `_mlx_model` / `_mlx_tokenizer` — first call ~4s, subsequent ~0s

## Current State (July 18, 2026)
- 82 documents indexed
- 513 chunks with contextual text
- 640-dim MLX embeddings on all chunks
- 6 domains: legal, systems, solar, casino, personal, general
- Source: vault only (kanban, solar DB, sessions not yet indexed)
- Cron: `knowledge-vault-sync` every 6 hours

## Known Issues
- **Hash-based placeholder was deployed first** — the initial `knowledge_embed.py` used a simple TF-IDF-like hash approach that produced near-random vector search results. This was replaced by `knowledge_embed_v3.py` with proper MLX hidden-state embeddings. The hash approach should never have been deployed — always use proper embeddings from the start.
- **MLX model reloads on cron ticks** — the singleton cache is per-process. Each cron job run is a new process, so the model reloads every 6 hours. Acceptable for now.
- **FTS5 query syntax** — multi-word queries need proper escaping. Use `'"exact phrase"'` for exact matches.
