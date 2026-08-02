#!/usr/bin/env python3
"""
Phase 1B v4: Qwen3 Embedding Model
Uses Qwen3-Embedding-0.6B-4bit-DWQ — a proper embedding model, not hacked hidden states.
Purpose-built for semantic search, 16K+ downloads, tiny footprint.
"""
import sqlite3, numpy as np, time
from pathlib import Path
import mlx.core as mx
from mlx_lm import load

DB_PATH = Path.home() / ".hermes" / "knowledge.db"

# Cached model (singleton)
_model = None
_tokenizer = None

def get_model():
    global _model, _tokenizer
    if _model is None:
        _model, _tokenizer = load("mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ")
    return _model, _tokenizer

def get_embedding(text, max_tokens=512):
    """Get embedding from Qwen3 embedding model."""
    model, tokenizer = get_model()
    
    # Qwen3 embedding models use a specific format
    # They expect: "<s>instruction</s>text"
    # For general purpose, just pass the text
    tokens = tokenizer.encode(text)
    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]
    
    tokens_mx = mx.array([tokens])
    
    # Get hidden states from the last layer
    h = model.model.embed_tokens(tokens_mx)
    for layer in model.model.layers:
        h = layer(h)
    h = model.model.norm(h)
    
    # Mean pool over content tokens
    if h.shape[1] > 2:
        emb = mx.mean(h[:, 1:-1, :], axis=1)
    else:
        emb = mx.mean(h, axis=1)
    
    # Normalize
    emb_np = np.array(emb[0].astype(mx.float32))
    norm = np.linalg.norm(emb_np)
    if norm > 0:
        emb_np = emb_np / norm
    
    return emb_np

def regenerate_embeddings():
    print("Loading Qwen3-Embedding-0.6B-4bit-DWQ...")
    start = time.time()
    
    model, tokenizer = get_model()
    
    load_time = time.time() - start
    print(f"Model loaded in {load_time:.1f}s")
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    chunks = conn.execute(
        "SELECT id, contextual_text FROM knowledge_chunks ORDER BY id"
    ).fetchall()
    
    print(f"Regenerating embeddings for {len(chunks)} chunks...")
    
    batch_size = 10
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        
        for chunk in batch:
            try:
                emb = get_embedding(chunk['contextual_text'])
                conn.execute(
                    "UPDATE knowledge_chunks SET embedding = ? WHERE id = ?",
                    (emb.tobytes(), chunk['id'])
                )
            except Exception as e:
                print(f"  Error on chunk {chunk['id']}: {e}")
        
        conn.commit()
        
        if (i + batch_size) % 50 == 0 or (i + batch_size) >= len(chunks):
            pct = min(100, (i + batch_size) * 100 // len(chunks))
            print(f"  {min(i+batch_size, len(chunks))}/{len(chunks)} ({pct}%)")
    
    conn.close()
    
    # Get embedding dimension
    conn = sqlite3.connect(str(DB_PATH))
    first = conn.execute("SELECT embedding FROM knowledge_chunks LIMIT 1").fetchone()
    dims = len(np.frombuffer(first[0], dtype=np.float32)) if first else 0
    conn.close()
    
    total = time.time() - start
    print(f"✅ Qwen3 embeddings done: {len(chunks)} chunks, {dims} dims, {total:.1f}s")

if __name__ == "__main__":
    print("Qwen3 Embedding Generation — Phase 1B v4")
    print("=" * 50)
    regenerate_embeddings()
