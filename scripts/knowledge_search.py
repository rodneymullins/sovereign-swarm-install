#!/usr/bin/env python3
"""
Phase 2: Hybrid Search Pipeline
Combines FTS5 full-text + vector similarity + domain filter + recency
with RRF fusion and context expansion.
"""
import sqlite3, json, numpy as np, time, re, os, math
from pathlib import Path
from collections import defaultdict
from functools import lru_cache

DB_PATH = Path.home() / ".hermes" / "knowledge.db"

# MLX model cache — loaded once, reused across queries
_mlx_model = None
_mlx_tokenizer = None

def _get_mlx_model():
    """Load Qwen3 embedding model once and cache it.
    Using base model without LoRA — the base Qwen3-Embedding is already
    a purpose-built embedding model. LoRA trained on language modeling
    degrades embedding quality."""
    global _mlx_model, _mlx_tokenizer
    if _mlx_model is None:
        import mlx.core as mx
        from mlx_lm import load
        _mlx_model, _mlx_tokenizer = load("mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ")
    return _mlx_model, _mlx_tokenizer

def _get_query_embedding(query):
    """Get Qwen3 embedding for a query string, using cached LoRA-adapted model.
    Returns float32 numpy array normalized to unit length."""
    try:
        model, tokenizer = _get_mlx_model()
        import mlx.core as mx
        tokens = tokenizer.encode(query)
        if len(tokens) > 512:
            tokens = tokens[:512]
        tokens_mx = mx.array([tokens])
        h = model.model.embed_tokens(tokens_mx)
        for layer in model.model.layers:
            h = layer(h)
        h = model.model.norm(h)
        if h.shape[1] > 2:
            emb = mx.mean(h[:, 1:-1, :], axis=1)
        else:
            emb = mx.mean(h, axis=1)
        emb = emb[0]
        norm = mx.sqrt(mx.sum(emb * emb))
        emb = emb / norm
        # Return float32 numpy array for consistent storage
        return np.array(emb.astype(mx.float32))
    except Exception as e:
        print(f"Qwen3 embedding error: {e}")
        return None

def _sanitize_fts_query(query):
    """Sanitize a query string for FTS5.
    - Removes trailing punctuation
    - Replaces ? with space (FTS5 treats ? as wildcard)
    - Keeps short terms and numbers unquoted for broader matching
    - Quotes longer terms for phrase matching
    - Returns None if query is empty after sanitization
    """
    if not query or not query.strip():
        return None
    
    # Remove trailing punctuation
    sanitized = re.sub(r'[?.,!;:]+$', '', query)
    # Replace remaining ? with space
    sanitized = sanitized.replace('?', ' ')
    # Collapse whitespace
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    
    if not sanitized:
        return None
    
    # Build FTS5 query
    # Strategy: quote multi-word terms, keep short terms bare for broader matching
    # This is better than quoting every word individually
    parts = []
    for w in sanitized.split():
        w = w.strip('\'"')
        if not w:
            continue
        # Keep short words (2 chars or less) and numbers unquoted
        if len(w) <= 2 or w.isdigit():
            parts.append(w)
        else:
            parts.append(f'"{w}"')
    
    return ' '.join(parts)

def _compute_idf_weight(term, total_docs, doc_freq):
    """Compute inverse document frequency weight for a term.
    Rare terms get higher weight, common terms get lower weight."""
    if doc_freq <= 0:
        return math.log(total_docs)
    return math.log(total_docs / doc_freq)

def search_knowledge(query, domain=None, source=None, limit=10, min_score=0.0):
    """
    Unified hybrid search across all indexed sources.
    
    Args:
        query: Search string
        domain: Filter to domain ('legal', 'systems', 'solar', 'casino', 'personal')
        source: Filter to source ('vault', 'kanban', 'solar', 'casino')
        limit: Max results to return
        min_score: Minimum relevance threshold
    
    Returns:
        dict with results list and metadata
    """
    start = time.time()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # Build base query parts
    domain_clause = ""
    domain_params = ()
    if domain:
        domain_clause = " AND d.domain = ?"
        domain_params = (domain,)
    
    source_clause = ""
    source_params = ()
    if source:
        source_clause = " AND d.source = ?"
        source_params = (source,)
    
    # === RETRIEVER 1: FTS5 Full-Text Search ===
    fts_results = {}
    try:
        fts_query = _sanitize_fts_query(query)
        
        if fts_query:
            rows = conn.execute(f"""
                SELECT c.id, c.document_id, c.contextual_text, c.question, c.summary, 
                       c.resolution, c.systems, c.code_refs,
                       d.title, d.domain, d.source, d.source_path,
                       rank as fts_score
                FROM knowledge_fts f
                JOIN knowledge_chunks c ON f.rowid = c.id
                JOIN knowledge_documents d ON c.document_id = d.id
                WHERE knowledge_fts MATCH ?
                {domain_clause}{source_clause}
                ORDER BY rank
                LIMIT 50
            """, (fts_query,) + domain_params + source_params).fetchall()
            
            for row in rows:
                fts_results[row['id']] = {
                    'id': row['id'],
                    'title': row['title'],
                    'domain': row['domain'],
                    'source': row['source'],
                    'contextual_text': row['contextual_text'],
                    'question': row['question'],
                    'summary': row['summary'],
                    'resolution': row['resolution'],
                    'systems': json.loads(row['systems']) if row['systems'] else [],
                    'code_refs': json.loads(row['code_refs']) if row['code_refs'] else [],
                    'url': f"[[{Path(row['source_path']).stem}]]" if row['source_path'] else "",
                    'fts_score': row['fts_score'],
                }
    except Exception as e:
        print(f"FTS5 search error: {e}")
    
    # === RETRIEVER 2: Vector Similarity (1024-dim Qwen3 LoRA embeddings) ===
    vec_results = {}
    try:
        query_embedding = _get_query_embedding(query)
        
        if query_embedding is not None:
            rows = conn.execute(f"""
                SELECT c.id, c.embedding, c.document_id
                FROM knowledge_chunks c
                JOIN knowledge_documents d ON c.document_id = d.id
                WHERE c.embedding IS NOT NULL
                {domain_clause}{source_clause}
            """, domain_params + source_params).fetchall()
            
            if rows:
                scored = []
                for row in rows:
                    if row['embedding']:
                        vec = np.frombuffer(row['embedding'], dtype=np.float32)
                        # Cosine similarity via dot product (both are unit-normalized)
                        sim = float(np.dot(query_embedding, vec))
                        if sim > 0.1:
                            scored.append((row['id'], sim))
                
                scored.sort(key=lambda x: x[1], reverse=True)
                
                for chunk_id, sim in scored[:50]:
                    if chunk_id in fts_results:
                        vec_results[chunk_id] = fts_results[chunk_id].copy()
                        vec_results[chunk_id]['vec_score'] = sim
                    else:
                        row = conn.execute("""
                            SELECT c.id, c.contextual_text, c.question, c.summary,
                                   c.resolution, c.systems, c.code_refs,
                                   d.title, d.domain, d.source, d.source_path
                            FROM knowledge_chunks c
                            JOIN knowledge_documents d ON c.document_id = d.id
                            WHERE c.id = ?
                        """, (chunk_id,)).fetchone()
                        if row:
                            vec_results[chunk_id] = {
                                'id': row['id'],
                                'title': row['title'],
                                'domain': row['domain'],
                                'source': row['source'],
                                'contextual_text': row['contextual_text'],
                                'question': row['question'],
                                'summary': row['summary'],
                                'resolution': row['resolution'],
                                'systems': json.loads(row['systems']) if row['systems'] else [],
                                'code_refs': json.loads(row['code_refs']) if row['code_refs'] else [],
                                'url': f"[[{Path(row['source_path']).stem}]]" if row['source_path'] else "",
                                'vec_score': sim,
                            }
    except Exception as e:
        print(f"Vector search error: {e}")
    
    # === RRF FUSION ===
    k = 60  # Smoothing constant
    
    # Rank FTS5 results
    fts_ranked = sorted(fts_results.values(), key=lambda x: x.get('fts_score', 0), reverse=True)
    fts_rank = {r['id']: i+1 for i, r in enumerate(fts_ranked)}
    
    # Rank vector results
    vec_ranked = sorted(vec_results.values(), key=lambda x: x.get('vec_score', 0), reverse=True)
    vec_rank = {r['id']: i+1 for i, r in enumerate(vec_ranked)}
    
    # Compute RRF scores
    all_ids = set(list(fts_results.keys()) + list(vec_results.keys()))
    rrf_scores = {}
    for cid in all_ids:
        score = 0.0
        if cid in fts_rank:
            score += 1.0 / (k + fts_rank[cid])
        if cid in vec_rank:
            score += 1.0 / (k + vec_rank[cid])
        rrf_scores[cid] = score
    
    # Sort by RRF score
    ranked_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    
    # Build final results
    results = []
    for cid in ranked_ids[:limit]:
        entry = fts_results.get(cid, vec_results.get(cid, {}))
        if entry:
            entry['relevance'] = round(rrf_scores[cid], 4)
            if entry['relevance'] >= min_score:
                results.append(entry)
    
    elapsed = (time.time() - start) * 1000
    
    conn.close()
    
    return {
        "results": results,
        "total": len(results),
        "query_time_ms": round(elapsed, 1),
        "sources": {
            "fts_matches": len(fts_results),
            "vector_matches": len(vec_results),
        }
    }

def search_legal(query, **kwargs):
    """Scoped search over legal domain."""
    return search_knowledge(query, domain="legal", **kwargs)

def search_solar(query, **kwargs):
    """Scoped search over solar domain."""
    return search_knowledge(query, domain="solar", **kwargs)

def search_casino(query, **kwargs):
    """Scoped search over casino domain."""
    return search_knowledge(query, domain="casino", **kwargs)

if __name__ == "__main__":
    # Demo
    print("Hybrid Search Pipeline — Phase 2 (LoRA-adapted)")
    print("=" * 50)
    
    test_queries = [
        "GAL reports 7 days hearing",
        "motion to compel discovery",
        "filing fee contempt",
        "solar battery voltage float",
        "Kelly Criterion bet sizing",
    ]
    
    for q in test_queries:
        print(f"\nQuery: '{q}'")
        result = search_knowledge(q, limit=3)
        print(f"  Found {result['total']} results in {result['query_time_ms']}ms")
        for r in result['results'][:3]:
            print(f"  [{r['domain']}] {r['title']}")
            print(f"   Score: {r['relevance']} | Summary: {r['summary'][:80]}...")
        print(f"  Sources: FTS={result['sources']['fts_matches']}, Vec={result['sources']['vector_matches']}")
