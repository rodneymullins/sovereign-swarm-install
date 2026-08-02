# Pipeline: Cross-Domain Knowledge Synthesis

**Script:** `~/.hermes/scripts/pipeline_knowledge_synthesis.py`
**Architecture plan:** Use Case 5 in `agentworld-architecture-plans.md`
**Built:** July 25, 2026

## Purpose
Daily morning synthesis pipeline that runs 4 parallel domain analysis nodes (legal, financial, solar, personal), then synthesizes cross-domain connections via qwen-agentworld:35b. Outputs 3 lines: what changed, what contradicts, what I forgot.

## Architecture
```
Phase 1 (parallel): 4 domain nodes via ThreadPoolExecutor
  ├── analyze_legal()    → FTS5 search knowledge.db (legal domain)
  ├── analyze_financial() → finances.db + kalshi_tracker.json
  ├── analyze_solar()    → knowledge.db (solar) + Open-Meteo weather
  └── analyze_personal() → knowledge.db (personal) + vault scan

Phase 2: synthesize() → qwen-agentworld:35b via Ollama /api/chat
Phase 3: Format 3-line brief → stdout + ~/.hermes/state/synthesis_pipeline.json
```

## Key Technical Patterns

### FTS5-Only Search (Thread-Safe)
The pipeline uses direct SQLite FTS5 queries instead of importing `knowledge_search` (which loads MLX). This avoids `Segmentation fault: 11` from MLX's Metal backend in threaded contexts.

```python
def _search_kb(query, domain=None, limit=8):
    fts_query = _sanitize_fts_query(query)  # preserves OR/AND/NOT
    conn = sqlite3.connect(str(KNOWLEDGE_DB))
    rows = conn.execute("""
        SELECT ... FROM knowledge_fts f
        JOIN knowledge_chunks c ON f.rowid = c.id
        JOIN knowledge_documents d ON c.document_id = d.id
        WHERE knowledge_fts MATCH ? AND d.domain = ?
        ORDER BY rank LIMIT ?
    """, (fts_query, domain, limit)).fetchall()
```

### FTS5 Operator Handling
The sanitizer must preserve FTS5 operators (OR, AND, NOT) as unquoted tokens while quoting regular words:

```python
FTS5_OPS = {'OR', 'AND', 'NOT'}
for w in query.split():
    if w.upper() in FTS5_OPS:
        parts.append(w.upper())  # unquoted operator
    else:
        parts.append(f'"{w}"')   # quoted term
```

### AgentWorld API Quirk
qwen-agentworld:35b via `/api/chat` returns output in `message.thinking`, not `message.content`. The thinking field contains a "Thinking Process:" preamble followed by the actual response. Parse by extracting from `body["message"]["thinking"]` and using `rfind("CHANGED:")` to locate the output after the reasoning block.

### Fallback Values
When the model call fails (timeout, API error), the pipeline uses hardcoded fallback values derived from the domain data. This ensures the script always produces output even if the model is unavailable.

## Data Sources
| Domain | Source | Schema |
|--------|--------|--------|
| Legal | `knowledge.db` (FTS5, domain=legal) | 22 docs, 1695 chunks |
| Financial | `finances.db` (receipts, income) + `kalshi_tracker.json` | 6 receipts, 1 income entry |
| Solar | `knowledge.db` (FTS5, domain=solar) + Open-Meteo API | 8 docs |
| Personal | `knowledge.db` (FTS5, domain=personal) + vault scan | 12 docs |

## Output Format
```
☀️ MORNING SYNTHESIS — YYYY-MM-DD
==================================================

CHANGED: [one specific pattern that shifted recently]

CONTRADICTS: [two things that cannot both be true]

FORGOTTEN: [a thread that dropped off but still matters]

──────────────────────────────────────────────────
Domains scanned: legal (N findings) | financial ($X spent) | solar (X.XV) | personal (N insights)
```

## Cron Integration
Intended to run daily at 6:30 AM via cron, replacing or enhancing the existing `daily-brief.py`.
