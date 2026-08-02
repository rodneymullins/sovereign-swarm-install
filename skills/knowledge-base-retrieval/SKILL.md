---
name: knowledge-base-retrieval
title: Knowledge Base Retrieval Layer
description: Build and maintain a hybrid search knowledge base from vault notes, kanban tasks, solar data, and other sources. Combines FTS5 full-text search with MLX embeddings, RRF fusion, contextual retrieval (Anthropic method), and parent-child chunking. All data lands in a single SQLite DB queryable through MCP-style search tools.
category: systems
---

# Knowledge Base Retrieval Layer

## When to Use
- Building a searchable knowledge base from vault notes, documents, or data sources
- Adding a new data source to the knowledge base (plugin pattern)
- Running the distillation pipeline to index new or changed notes
- Regenerating MLX embeddings after data changes
- Querying the knowledge base via hybrid search (FTS5 + vector + RRF)
- Debugging search quality — why a result did or didn't surface

## Architecture

### Core Data Model
Single SQLite database (`~/.hermes/knowledge.db`) with parent-child table structure:

- **`knowledge_documents`** — Full document metadata (title, source, domain, full_text, tags)
- **`knowledge_chunks`** — Individual sections with contextualized text, MLX embeddings (1024 dims from Qwen3-Embedding-0.6B), structured artifacts (question, summary, resolution, code_refs)
- **`knowledge_fts`** — FTS5 full-text index over contextualized text
- **`knowledge_sync`** — Tracks which files have been processed (by file hash)

### Data Flow
```
RAW SOURCE → DISTILLATION → CONTEXTUALIZE → MLX EMBED → KNOWLEDGE DB → 
HYBRID SEARCH (FTS5 + vector + domain + recency) → RRF FUSE → 
TINY SPECIALIST RERANK → CONTEXT EXPAND → SYNTHESIS
```

## Scripts

### `~/.hermes/scripts/knowledge_distill.py` — Vault Distillation Pipeline
Reads all reference notes from `08-Tools/References/` AND `00-Inbox/raw/`, extracts sections by `##` headings, generates contextual text (Anthropic method), and writes to knowledge.db.

**Updated July 23, 2026:** Now scans TWO directories — `08-Tools/References` (source='vault') and `00-Inbox/raw` (source='inbox'). This ensures ingested emails and research briefs are indexed alongside reference notes. The `process_directory()` helper is parameterized by source name so both directories use the same extraction/chunking/embedding pipeline. Previously only scanned `08-Tools/References`, leaving 264+ ingested emails unindexed.

**Contextual Retrieval (Anthropic method):** Before embedding, prepend a short context string to each chunk explaining where it came from:
```
Before: "GAL reports shall be filed 7 days before hearing."
After: "This section is from Hamilton County Juvenile Court Rule 8(F)(3) — GAL reports must be filed 7 days before the scheduled review hearing. GAL reports shall be filed 7 days before hearing."
```
This reduces retrieval failures by 49% (Anthropic, 2024).

**Run:**
```bash
python3 ~/.hermes/scripts/knowledge_distill.py
```

### `~/.hermes/scripts/knowledge_embed_qwen.py` — Qwen3 Embedding Generation (CURRENT)
Generates 1024-dimension embeddings from **Qwen3-Embedding-0.6B-4bit-DWQ** — a purpose-built embedding model, not hacked hidden states from a general LLM. 16K+ downloads on HuggingFace, 320MB on disk.

**Why Qwen3 over functiongemma:** Qwen3-Embedding is a dedicated embedding model. The earlier approach used functiongemma-270m hidden states (640 dims), which worked but was a hack. Qwen3 produces 1024-dim vectors with better semantic separation, especially for legal terminology.

**Run:**
```bash
python3 ~/.hermes/scripts/knowledge_embed_qwen.py
```

**Model caching:** The model is loaded once via a singleton pattern (`_get_mlx_model()`) and reused across queries. First call takes ~4s (model load), subsequent calls take ~0s. The model stays in memory for the lifetime of the Python process.

### `~/.hermes/scripts/finetune_qwen3_embedding.py` — Legal-Domain Fine-Tuning
Fine-tunes the Qwen3 embedding model for Ohio family law using contrastive learning. Trains a small projection head (1024→256 dims) on top of frozen base model hidden states using InfoNCE loss with in-batch negatives.

**Training data:** 344 HCJF Q&A pairs + 513 knowledge base chunks = 857 training pairs, 1,481 unique texts.

**Training results:** Loss dropped from 2.73 → 0.46 over 5 epochs (85% reduction). ~3 minutes total training time.

**Current status:** The projection head approach shows the model is learning (clean loss curve) but top results for legal queries aren't hitting the right documents yet. The base Qwen3 model already has good general embeddings — what's needed is LoRA fine-tuning on the base model itself, not just a projection head on top. The projection head is a fast lightweight approach; for "excellent" quality, LoRA on the base model is the right answer.

**Saved to:** `~/Documents/qwen3-legal-embedding/adapter/`

### `~/.hermes/scripts/knowledge_search.py` — Hybrid Search
Combines FTS5 full-text + Qwen3 vector similarity (1024 dims) + domain filter + recency with RRF fusion.

**Key functions:**
- `search_knowledge(query, domain=None, source=None, limit=10)` — Unified search
- `search_legal(query)` — Scoped to legal domain
- `search_solar(query)` — Scoped to solar domain
- `search_casino(query)` — Scoped to casino domain

**RRF Fusion formula:** `score = 1.0 / (60 + rank)` per retriever list. The smoothing constant (60) makes consensus across retrievers matter more than a single strong vote.

**Model caching:** The Qwen3 model is loaded once via a singleton pattern and reused across queries. First call takes ~4s (model load), subsequent calls take ~0s.

**Run:**
```bash
python3 ~/.hermes/scripts/knowledge_search.py
```

## Adding a New Data Source (Plugin Pattern)

1. Write a Python module that reads from the source and emits rows matching the knowledge_chunks schema
2. For each record, generate:
   - `contextual_text` — The content with prepended document context
   - `question` — What someone would search for
   - `summary` — One-line description
   - `resolution` — The answer or procedure
   - `systems` — Tags or system names (JSON array)
   - `code_refs` — Rule numbers, citations (JSON array)
3. Insert into knowledge_chunks and update knowledge_documents
4. Run knowledge_embed_qwen.py to generate embeddings for the new chunks
5. Rebuild FTS index: `INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')`

### Example: `index_additional_sources.py`
The script at `~/.hermes/scripts/index_additional_sources.py` demonstrates the plugin pattern for three data sources:

**Kanban tasks:** Reads from `~/.hermes/kanban.db` (tasks table with id, title, body, status, workspace_kind). Maps to 'systems' domain.

**Solar daily summaries:** Reads from `~/chargepro_data.db` (daily_summary table with date, total_wh, min_v, max_v). Maps to 'solar' domain.

**Past sessions:** Reads from `~/.hermes/sessions.db` (sessions table with id, title, created_at, summary). Maps to 'general' domain.

**Run:**
```bash
python3 ~/.hermes/scripts/index_additional_sources.py
```

**Caveats:**
- Kanban DB may have 0 tasks if the board is empty — the script handles this gracefully
- Sessions DB may be 0 bytes (no session history stored) — the script checks file size before connecting
- Solar daily_summary table may have limited data — the script indexes what's available
- Each source uses the same Qwen3-Embedding model for consistent vector space

## CRITICAL: Embedding Model Selection — Use Base Model, Not LoRA

**The single most important lesson from July 18, 2026:** For embedding quality, use the **base Qwen3-Embedding-0.6B model without LoRA adapters.** LoRA trained on language modeling (next-token prediction) actively degrades embedding quality because it optimizes for text generation, not semantic similarity.

### What was tried and why it failed:

1. **functiongemma-270m hidden states (640 dims)** — Worked but was a hack. Not a purpose-built embedding model. Replaced with Qwen3.

2. **Qwen3-Embedding-0.6B with LoRA (language modeling)** — `mlx_lm.lora` trains on next-token prediction. The adapter changed the hidden states (MSE 1.24 vs base) but did NOT improve semantic similarity. Related queries scored only 1.19x higher than unrelated — barely better than random.

3. **Qwen3-Embedding-0.6B with projection head (contrastive)** — Trained a 1024→256 dim MLP using InfoNCE loss. Loss dropped 85% (2.73→0.46) but top search results were wrong (e.g., "How do I file a motion" returned Bill Friedman Casino Design Pioneer). The projection head is too small to capture legal-domain patterns.

4. **Qwen3-Embedding-0.6B with LoRA (contrastive, custom training loop)** — Attempted to train LoRA adapters with InfoNCE loss directly on embedding similarity. The custom training loop had architectural issues with MLX's gradient tracking through in-place weight modifications. The `mlx_lm.lora` tool doesn't support contrastive loss.

### The correct approach:

**Use the base Qwen3-Embedding-0.6B model without any adapter.** It's a purpose-built embedding model with 16K+ downloads on HuggingFace. The hybrid search (FTS5 for exact matches + base Qwen3 vectors for semantic) is the proven pattern from Cerebras, Anthropic, and every production RAG system.

### If you must fine-tune an embedding model:

- Use a dedicated embedding fine-tuning framework (not `mlx_lm.lora`)
- Train with contrastive/InfoNCE loss, not language modeling loss
- The training data must be (anchor, positive, negative) triplets, not (text) pairs
- Consider Sentence Transformers' `sentence_transformers` package for proper contrastive training
- MLX can be used for inference but the training loop needs to be custom-built

## MLX Array Storage (Critical)

MLX uses bfloat16 internally. When storing embeddings in SQLite, you MUST convert to float32 first:

```python
# WRONG — causes 'Item size 2 for PEP 3118 buffer format string B does not match'
emb_np = np.array(emb)  # tries to use MLX bfloat16 buffer directly

# RIGHT
emb_np = np.array(emb.astype(mx.float32))  # explicit float32 conversion
```

The error message is: `Item size 2 for PEP 3118 buffer format string B does not match the dtype B item size 1`. This means MLX's bfloat16 (2 bytes) doesn't match numpy's default float64 (8 bytes). Always cast to float32 before converting to numpy.

## FTS5 Query Sanitization

FTS5 treats `?` as a wildcard character. Queries containing question marks will fail with:
```
fts5: syntax error near "?"
```

**Fix:** Strip trailing punctuation and replace `?` with space before passing to FTS5:

```python
sanitized = re.sub(r'[?.,!;:]+$', '', query)
sanitized = sanitized.replace('?', ' ')
```

## FTS5 Query Sanitization (Critical)

FTS5 treats `?` as a wildcard character. Queries containing question marks will fail with:
```
fts5: syntax error near "?"
```

**Fix in `knowledge_search.py`:** Strip trailing punctuation and replace `?` with space before passing to FTS5:
```python
sanitized = re.sub(r'[?.,!;:]+$', '', query)
sanitized = sanitized.replace('?', ' ')
sanitized = re.sub(r'\s+', ' ', sanitized).strip()
```

Then quote each word individually for FTS5:
```python
fts_parts = []
for w in sanitized.split():
    w = w.strip('\'"')
    if len(w) > 2 and not w.isdigit():
        fts_parts.append(f'"{w}"')
    else:
        fts_parts.append(w)
fts_query = ' '.join(fts_parts)
```

## MLX Array Storage (Critical)

MLX uses bfloat16 internally. When storing embeddings in SQLite, you MUST convert to float32 first:

```python
# WRONG — causes 'Item size 2 for PEP 3118 buffer format string B does not match'
emb_np = np.array(emb)  # tries to use MLX bfloat16 buffer directly

# RIGHT
emb_np = np.array(emb.astype(mx.float32))  # explicit float32 conversion
```

The error message is: `Item size 2 for PEP 3118 buffer format string B does not match the dtype B item size 1`. This means MLX's bfloat16 (2 bytes) doesn't match numpy's default float64 (8 bytes). Always cast to float32 before converting to numpy.

## Pitfalls
- **Qwen3 model loads on every query** — the search script loads Qwen3-Embedding-0.6B for each vector search. **FIXED:** The search script now uses a singleton pattern (`_get_mlx_model()`) that loads the model once and caches it in a global variable. First call takes ~4s (model load), subsequent calls take ~0s. If the script is run in a subprocess (cron job), the cache is lost — each cron tick reloads the model. For production, run the search as a persistent server.
- **MLX model segfaults in threaded contexts** — Importing `knowledge_search` (which loads Qwen3-Embedding-0.6B via MLX) from a `ThreadPoolExecutor` worker causes `Segmentation fault: 11`. MLX's Metal backend is not fork/thread-safe. **Fix:** Use direct SQLite FTS5 queries (no MLX) when searching from threaded code. The FTS5-only approach is fast, thread-safe, and sufficient for keyword/domain searches. Reserve MLX vector search for single-threaded contexts. See `pipeline_knowledge_synthesis.py` for the FTS5-only `_search_kb()` pattern.
- **FTS5 multi-word queries need OR operators** — Quoting every word individually (e.g., `"trial" "preparation" "August"`) requires ALL terms to appear in the same chunk, which often returns zero results. **Fix:** Use FTS5 OR operators: `"trial" OR "preparation" OR "August"`. The sanitizer must preserve OR/AND/NOT as unquoted operators. See `_sanitize_fts_query()` in `pipeline_knowledge_synthesis.py` for the correct pattern that handles FTS5 operators.
- **Don't use hash-based placeholder embeddings** — the first version used a simple TF-IDF-like hash approach that produced near-random vector search results. Always use proper MLX hidden-state embeddings (mean-pooled over content tokens from Qwen3-Embedding-0.6B). The hash approach was a placeholder that should never have been deployed.
- **Do NOT use LoRA on embedding models** — `mlx_lm.lora` trains on language modeling, which degrades embedding quality. The base Qwen3-Embedding model is already purpose-built for this task. See "CRITICAL: Embedding Model Selection" above.
- **FTS5 query syntax** — multi-word queries need proper escaping. Use `'"exact phrase"'` for exact matches, bare words for fuzzy. Strip `?` characters first.
- **Contextual text is critical** — without it, chunks lose document-level identifiers (rule numbers, statute citations, form names). Always prepend context.
- **Domain detection** — the distill script maps tags to domains. If a note has no matching tag, it defaults to 'general'. Add domain tags to frontmatter for proper scoping.
- **Embedding dimension** — Qwen3-Embedding-0.6B produces 1024-dim hidden states. If you switch models, update the dimension in both embed and search scripts.
- **Incremental updates** — the sync table tracks file hashes. Only changed files are re-processed. Run `knowledge_distill.py` on a cron (every 6h) to keep fresh.
- **FTS index rebuild** — after inserting new chunks, rebuild the FTS index: `conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")`

## GraphRAG / Knowledge Graph Alternative

**Validated July 20, 2026:** Microsoft GraphRAG was installed and tested on a 50-document subset of the F25 custody case. Results: 545 entities, 1,380 relationships extracted from 50 documents using gemma4:31b-cloud + nomic-embed-text via Ollama.

### When to Use GraphRAG Instead of Vector Search

| Query Type | Vector Search (Current) | Knowledge Graph (GraphRAG) |
|-----------|------------------------|---------------------------|
| "Find documents about GAL reports" | ✅ Good | ✅ Good |
| "What connects Treleven to van der Zee?" | ❌ Misses relationship | ✅ Returns: professional relationship, undisclosed conflict |
| "What evidence supports my custody case?" | ❌ Returns similar chunks | ✅ Traverses: Rod → filed → motions → references → evidence |
| "Show me the chain of events" | ❌ Flat results | ✅ Traverses entity→relationship→entity paths |

### Setup

```bash
# Install
python3.12 -m venv ~/.hermes/venvs/graphrag
source ~/.hermes/venvs/graphrag/bin/activate
pip install graphrag

# Initialize
cd /tmp/graphrag-test
graphrag init --root .

# Configure for Ollama (settings.yaml)
# completion model: gemma4:31b-cloud via http://localhost:11434/v1
# embedding model: nomic-embed-text via http://localhost:11434/v1

# Index
graphrag index --root .

# Query
graphrag query -m local "What evidence supports the custody case?"
```

### Model Selection for Indexing

| Model | Quality | Speed | Cost |
|-------|---------|-------|------|
| gemma4:31b-cloud (chat) | Good — correctly extracts legal entities | Fast (Level 2) | $0 (Ollama Pro flat fee) |
| deepseek-v4-flash:cloud (chat) | Very good — better at implicit relationships | Slower (Level 3) | $0 (Ollama Pro flat fee) |
| nomic-embed-text (embeddings) | Baseline (62.4 MTEB) | Fast, 274MB | $0 |
| snowflake-arctic-embed2 (embeddings) | Best (68.5 MTEB) | Slower, 1.2GB | $0 |

### Known Limitations

- **Embedding step is the bottleneck** — nomic-embed-text is fast but lower quality; snowflake-arctic-embed2 is better (68.5 MTEB) but 1.2GB and slow on first run. The text embeddings step (`generate_text_embeddings`) consistently times out at 10+ minutes on 50 documents. This is the step that prevents local/global search queries from working.
- **Community reports step fails silently** — the `create_community_reports` workflow can complete (4/4 communities) but then fail on the actual report generation with `KeyError: 'community'`. The pipeline reports "completed with errors" but doesn't surface this clearly. Check `logs/*.log` for the actual error.
- **Without community reports + embeddings, only raw parquet queries work** — you can query entities.parquet and relationships.parquet directly with pandas, but the built-in `graphrag query -m local` and `graphrag query -m global` commands will fail.
- **Ollama Pro usage** — 1,500+ requests for 50 documents at ~25% allocation on the $20 plan. Full 13K index would be significant
- **Concurrent requests matter** — GraphRAG fires parallel LLM calls during entity extraction. On Ollama Pro ($20/mo, 2 concurrent), set `concurrent_requests: 1` in settings.yaml. On Ollama Max ($100/mo, 10 concurrent), set `concurrent_requests: 5` for faster indexing without hitting 429 rate limits.
- **The Ollama port of Unlimited-OCR runs in evaluation mode** — bounding boxes + "Ground Truth" analysis instead of text extraction. Proper inference requires CUDA/NVIDIA GPU (Gandalf)

### Migration Path

1. **Phase 1 (done):** 50-doc test — proved entity extraction works, relationships are accurate
2. **Phase 2:** Full 13K vault index (overnight, use nomic-embed-text for speed)
3. **Phase 3:** Replace knowledge_search.py with graph queries for relationship questions
4. **Phase 4:** Hybrid mode — graph for relationships, vector for fuzzy text search

### Python (in-session)
```python
import sys
sys.path.insert(0, '/Users/rod/.hermes/scripts')
from knowledge_search import search_knowledge, search_legal, search_solar, search_casino
result = search_knowledge("GAL reports 7 days", domain="legal", limit=5)
```

### Terminal (cron / subprocess)
```bash
python3 -c "
import sys; sys.path.insert(0, '/Users/rod/.hermes/scripts')
from knowledge_search import search_knowledge
r = search_knowledge('GAL reports 7 days', domain='legal', limit=3)
for res in r['results']: print(f\"[{res['domain']}] {res['title']} — {res['summary'][:80]}\")
"
```

### Response Format
When presenting search results to the user:
```
**Results for "[query]":**
1. [Title] — [domain]
   [summary first 100 chars]
   Score: [relevance]
```

## Cron Jobs
- `knowledge-vault-sync` — Every 6 hours, re-indexes changed vault notes (no_agent mode)
- Run manually: `python3 ~/.hermes/scripts/knowledge_distill.py`

## Database
- Location: `~/.hermes/knowledge.db`
- Current state: 82 documents, 513 chunks, 1024-dim Qwen3 embeddings
- 6 domains: legal, systems, solar, casino, personal, general
- Source: vault (kanban/solar/telegram not yet indexed)

## Support Files
- `references/twilio-sms-setup.md` — Twilio SMS configuration
- `references/implementation-details.md` — Implementation details and architecture decisions
- `references/embedding-model-experiments-july-18-2026.md` — Full history of embedding model experiments
- `references/graphrag-50-doc-test-july-20-2026.md` — GraphRAG 50-document test results
- `references/inbox-raw-ingestion-pipeline.md` — X thread → inbox/raw → knowledge base pipeline (July 23, 2026)
