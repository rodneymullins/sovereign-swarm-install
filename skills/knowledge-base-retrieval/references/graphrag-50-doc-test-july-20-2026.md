# GraphRAG 50-Document Test — July 20, 2026

## Setup
- **Project:** /tmp/graphrag-test/
- **Input:** 50 .md files from F25 custody case vault
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
- People: Rodney Mullins, J.C., John Treleven, Alex van der Zee, Emma Cotto, Ryan Maxton, Stacey DeGraffenreid, Sara Hein, Kylie Lippa, Shelli Deskins
- Organizations: HCJFS, Best Point, Mt. Healthy Learning Center, Rocket Mortgage
- Legal concepts: R.C. 2323.311, Juv.R. 37, Fourteenth Amendment, Due Process, Civ.R. 60(B), ORPC 3.7, Evid.R. 403

## Relationship Quality
Correctly extracted:
- Rodney Mullins → J.C. (father/son)
- John Treleven → Alex van der Zee (professional relationship, undisclosed conflict)
- Mother → John Treleven (represented by)
- Rodney Mullins → John Treleven (opposing parties)
- Treleven → ORPC 3.3, 3.4, 8.4 (alleged violations)
- Rodney Mullins → CA 30712 (appellant)
- Rodney Mullins → Rocket Mortgage (foreclosure defendant)

## Bottlenecks
1. **Embedding step** — nomic-embed-text is slow for 89 text units. Snowflake-arctic-embed2 (68.5 MTEB) is even slower at 1.2GB.
2. **Community reports** — require embeddings to complete. Without them, local/global search queries fail with "Could not find community_reports.parquet"
3. **Ollama rate limits** — on the $20 Pro plan (2 concurrent), GraphRAG's parallel entity extraction hits 429 errors. On Max plan ($100, 10 concurrent), set concurrent_requests: 5.

## Next Steps
- Phase 2: Full 13K vault index (overnight, use nomic-embed-text for speed)
- Phase 3: Replace knowledge_search.py with graph queries for relationship questions
- Phase 4: Hybrid mode — graph for relationships, vector for fuzzy text search
