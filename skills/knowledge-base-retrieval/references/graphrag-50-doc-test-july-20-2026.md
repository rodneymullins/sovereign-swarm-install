# GraphRAG 50-Document Test — July 20, 2026

## Setup
- **Project:** /tmp/graphrag-test/
- **Input:** 50 .md files from a custody case vault
- **Chat model:** gemma4:31b-cloud via Ollama (http://localhost:11434/v1)
- **Embedding model:** nomic-embed-text via Ollama
- **Concurrent requests:** 5 (Ollama Max plan, 10 concurrent connections)

## Results
- **Documents:** 50 → 94 chunks
- **Entities extracted:** 545 (93 people, 118 organizations, 245 legal concepts, 46 events, 43 locations)
- **Relationships extracted:** 1,380
- **Communities:** 4
- **Entity extraction time:** ~3.3 minutes (199s)
- **Embedding step:** Timed out at 10+ minutes (nomic-embed-text, 89 text units)

## Entity Quality
Gemma4:31b-cloud correctly identified:
- People: Petitioner, Respondent, Guardian ad Litem, Magistrate, Judge, opposing counsel, expert witnesses
- Organizations: Child Protective Services, supervised visitation provider, school district, mortgage lender
- Legal concepts: R.C. 2323.311, Juv.R. 37, Fourteenth Amendment, Due Process, Civ.R. 60(B), ORPC 3.7, Evid.R. 403

## Relationship Quality
Correctly extracted:
- Petitioner → Child (father/son)
- Guardian ad Litem → Opposing Counsel (professional relationship, undisclosed conflict)
- Respondent → Opposing Counsel (represented by)
- Petitioner → Opposing Counsel (opposing parties)
- Opposing Counsel → ORPC 3.3, 3.4, 8.4 (alleged violations)
- Petitioner → Appeal Case (appellant)
- Petitioner → Mortgage Lender (foreclosure defendant)

## Bottlenecks
1. **Embedding step** — nomic-embed-text is slow for 89 text units. Snowflake-arctic-embed2 (68.5 MTEB) is even slower at 1.2GB.
2. **Community reports** — require embeddings to complete. Without them, local/global search queries fail with "Could not find community_reports.parquet"
3. **Ollama rate limits** — on the $20 Pro plan (2 concurrent), GraphRAG's parallel entity extraction hits 429 errors. On Max plan ($100, 10 concurrent), set concurrent_requests: 5.

## Next Steps
- Phase 2: Full vault index (overnight, use nomic-embed-text for speed)
- Phase 3: Replace knowledge_search.py with graph queries for relationship questions
- Phase 4: Hybrid mode — graph for relationships, vector for fuzzy text search
