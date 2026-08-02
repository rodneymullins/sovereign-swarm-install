---
name: graphrag-ollama-index
description: Run GraphRAG indexing and queries with Ollama backend. Covers settings.yaml fixes, litellm patches for gemma4 JSON code-block wrapping, and full pipeline execution.
---

# GraphRAG + Ollama Indexing Workflow

Run a full GraphRAG index on a document set using Ollama (gemma4:31b-cloud for chat, nomic-embed-text for embeddings).

## Prerequisites

- GraphRAG installed in a Python 3.12+ venv
- Ollama running locally with models: `gemma4:31b-cloud`, `nomic-embed-text`
- Input documents in a directory (markdown files)

## Step 1: Configure settings.yaml

Create `/path/to/project/settings.yaml`:

```yaml
### GraphRAG config for Ollama
concurrent_requests: 2
completion_models:
  default_completion_model:
    model_provider: openai
    model: gemma4:31b-cloud
    api_base: http://localhost:11434/v1
    api_key: ollama
    retry:
      type: exponential_backoff
    concurrent_requests: 2

embedding_models:
  default_embedding_model:
    model_provider: openai
    model: nomic-embed-text
    api_base: http://localhost:11434/v1
    api_key: ollama
    retry:
      type: exponential_backoff
    concurrent_requests: 2

input:
  type: text
  file_pattern: ".*\\.md"

chunking:
  type: tokens
  size: 1200
  overlap: 100
  encoding_model: o200k_base

input_storage:
  type: file
  base_dir: "input"

output_storage:
  type: file
  base_dir: "output"

reporting:
  type: file
  base_dir: "logs"

cache:
  type: json
  storage:
    type: file
    base_dir: "cache"

vector_store:
  type: lancedb
  db_uri: output/lancedb

embed_text:
  embedding_model_id: default_embedding_model

extract_graph:
  completion_model_id: default_completion_model
  prompt: "prompts/extract_graph.txt"
  entity_types: [organization, person, geo, event, legal_concept]
  max_gleanings: 1

summarize_descriptions:
  completion_model_id: default_completion_model
  prompt: "prompts/summarize_descriptions.txt"
  max_length: 500

extract_graph_nlp:
  text_analyzer:
    extractor_type: regex_english

cluster_graph:
  max_cluster_size: 10

extract_claims:
  enabled: false

community_reports:
  completion_model_id: default_completion_model
  graph_prompt: "prompts/community_report_graph.txt"
  text_prompt: "prompts/community_report_text.txt"
  max_length: 2000
  max_input_length: 8000

snapshots:
  graphml: false
  embeddings: false

local_search:
  completion_model_id: default_completion_model
  embedding_model_id: default_embedding_model
  prompt: "prompts/local_search_system_prompt.txt"

global_search:
  completion_model_id: default_completion_model
  map_prompt: "prompts/global_search_map_system_prompt.txt"
  reduce_prompt: "prompts/global_search_reduce_system_prompt.txt"
  knowledge_prompt: "prompts/global_search_knowledge_system_prompt.txt"

drift_search:
  completion_model_id: default_completion_model
  embedding_model_id: default_embedding_model
  prompt: "prompts/drift_search_system_prompt.txt"
  reduce_prompt: "prompts/drift_search_reduce_prompt.txt"

basic_search:
  completion_model_id: default_completion_model
  embedding_model_id: default_embedding_model
  prompt: "prompts/basic_search_system_prompt.txt"
```

**Key settings to get right:**
- `concurrent_requests: 2` at the **global level** (not just per-model) — without this, GraphRAG defaults to 25 concurrent requests and overwhelms Ollama
- `file_pattern: ".*\\.md"` — must NOT end with `$` (GraphRAG's config parser interprets `$` as a template variable)
- `retry: type: exponential_backoff` — essential for handling Ollama rate limits

## Step 2: Patch litellm for gemma4 JSON code-block wrapping

Gemma4 wraps JSON responses in markdown code blocks (```json ... ```). litellm's JSON schema validation rejects this. Two patches needed:

### Patch 1: Disable JSON schema validation

File: `graphrag_llm/completion/lite_llm_completion.py`
Change line 42 from:
```python
litellm.enable_json_schema_validation = True
```
to:
```python
litellm.enable_json_schema_validation = False
```

### Patch 2: Strip markdown code fences from structured responses

File: `graphrag_llm/utils/structure_response.py`
Add `import re` at the top, and before `json.loads(response)`, add:
```python
cleaned = response.strip()
if cleaned.startswith("```"):
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()
parsed_dict: dict[str, Any] = json.loads(cleaned)
```

## Step 3: Run the index

```bash
source ~/.hermes/venvs/graphrag/bin/activate
cd /path/to/project
# Clear stale cache for a fresh run
rm -rf output/* cache/* logs/*
graphrag index --root .
```

The index runs through these workflows:
1. `load_input_documents` — fast
2. `create_base_text_units` — fast
3. `create_final_documents` — fast
4. `extract_graph` — **slow** (~28 min for 50 docs, 94 chunks, 1394 relationships)
5. `finalize_graph` — fast
6. `extract_covariates` — fast
7. `create_communities` — fast
8. `create_final_text_units` — fast
9. `create_community_reports` — **slow** (~16 min for 97 communities)
10. `generate_text_embeddings` — moderate (~22 sec)

Total runtime for 50 documents: ~45 minutes.

## Step 4: Run queries

```bash
# Local search (contextual, entity-focused)
graphrag query -m local "Your question here"

# Global search (broad, community-focused)
graphrag query -m global "Your question here"

# Drift search (exploratory)
graphrag query -m drift "Your question here"

# Basic search (simple keyword)
graphrag query -m basic "Your question here"
```

## Step 5: Verify output

Check `output/stats.json` for all 10 workflows with non-zero runtimes. Check `output/` for parquet files: `documents.parquet`, `text_units.parquet`, `entities.parquet`, `relationships.parquet`, `communities.parquet`, `community_reports.parquet`.

## Pitfalls

1. **`concurrent_requests` must be set globally** — per-model settings alone don't override the global default of 25
2. **`file_pattern` must not end with `$`** — GraphRAG's YAML parser treats `$` as a template variable, causing the pattern to resolve to `null`
3. **Gemma4 wraps JSON in markdown code blocks** — litellm's JSON schema validation rejects this; must patch both `lite_llm_completion.py` and `structure_response.py`
4. **Ollama rate limits** — with `concurrent_requests: 2` and exponential backoff, retries handle 429 errors gracefully
5. **Cache invalidation** — if a previous run failed mid-way, clear `output/*`, `cache/*`, and `logs/*` before retrying
6. **Long runtime** — the `extract_graph` and `create_community_reports` workflows are the bottlenecks; set terminal timeout to 900+ seconds
7. **Vector size mismatch** — nomic-embed-text produces 768-dim vectors; GraphRAG auto-overrides the default 3072-dim setting
