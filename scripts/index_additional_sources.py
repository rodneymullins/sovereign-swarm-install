#!/usr/bin/env python3
"""
Index additional data sources into the knowledge base.
Phase 5: Kanban tasks, solar readings, past sessions.
"""
import sqlite3, json, time, numpy as np
from pathlib import Path
import mlx.core as mx
from mlx_lm import load

DB_PATH = Path.home() / ".hermes" / "knowledge.db"
KANBAN_DB = Path.home() / ".hermes" / "kanban.db"
SOLAR_DB = Path.home() / "chargepro_data.db"

print("Loading Qwen3-Embedding...")
model, tokenizer = load("mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ")
print("Model loaded.")

def get_embedding(text, max_tokens=512):
    tokens = tokenizer.encode(text)
    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]
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
    return np.array(emb.astype(mx.float32))

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

# === 1. Index Kanban tasks ===
print("\nIndexing kanban tasks...")
try:
    kb = sqlite3.connect(str(KANBAN_DB))
    kb.row_factory = sqlite3.Row
    tasks = kb.execute("SELECT id, title, body, status, workspace_kind FROM tasks ORDER BY id").fetchall()
    kb.close()
    
    kanban_count = 0
    for task in tasks:
        text = f"Task: {task['title']}\nDescription: {task['body'] or ''}\nStatus: {task['status']}\nBoard: {task['workspace_kind']}"
        contextual = f"This section is from Kanban board {task['workspace_kind']}. Task: {task['title']}. Status: {task['status']}.\n\n{text}"
        
        conn.execute("""INSERT OR REPLACE INTO knowledge_documents 
            (source, source_id, title, domain, source_path)
            VALUES (?, ?, ?, ?, ?)""",
            ("kanban", f"kanban-task-{task['id']}", task['title'], "systems", ""))
        doc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        emb = get_embedding(contextual)
        conn.execute("""INSERT INTO knowledge_chunks 
            (document_id, contextual_text, question, summary, embedding)
            VALUES (?, ?, ?, ?, ?)""",
            (doc_id, contextual, f"What is the status of {task['title']}?", f"Kanban task: {task['title']} - {task['status']}", emb.tobytes()))
        kanban_count += 1
    
    conn.commit()
    print(f"  Indexed {kanban_count} kanban tasks")
except Exception as e:
    print(f"  Kanban error: {e}")

# === 2. Index solar readings (summary) ===
print("\nIndexing solar data...")
try:
    sd = sqlite3.connect(str(SOLAR_DB))
    sd.row_factory = sqlite3.Row
    # Get daily summaries
    readings = sd.execute("""
        SELECT date, total_wh, min_v, max_v
        FROM daily_summary
        ORDER BY date DESC
        LIMIT 30
    """).fetchall()
    sd.close()
    
    solar_count = 0
    for r in readings:
        text = f"Day: {r['date']}, Min Voltage: {r['min_v']}V, Max Voltage: {r['max_v']}V, Energy: {r['total_wh']}Wh"
        contextual = f"This section is from ChargePro solar monitoring. Daily summary for {r['date']}.\n\n{text}"
        
        conn.execute("""INSERT OR REPLACE INTO knowledge_documents 
            (source, source_id, title, domain, source_path)
            VALUES (?, ?, ?, ?, ?)""",
            ("solar", f"solar-day-{r['date']}", f"Solar Summary {r['date']}", "solar", ""))
        doc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        emb = get_embedding(contextual)
        conn.execute("""INSERT INTO knowledge_chunks 
            (document_id, contextual_text, question, summary, embedding)
            VALUES (?, ?, ?, ?, ?)""",
            (doc_id, contextual, f"What was the solar production on {r['date']}?", f"Solar: {r['total_wh']}Wh, {r['min_v']}V-{r['max_v']}V", emb.tobytes()))
        solar_count += 1
    
    conn.commit()
    print(f"  Indexed {solar_count} solar daily summaries")
except Exception as e:
    print(f"  Solar error: {e}")

# === 3. Index past sessions (recent) ===
print("\nIndexing past sessions...")
try:
    session_db = Path.home() / ".hermes" / "sessions.db"
    if session_db.exists() and session_db.stat().st_size > 0:
        ss = sqlite3.connect(str(session_db))
        ss.row_factory = sqlite3.Row
        tables = ss.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        print(f"  Sessions tables: {table_names}")
        
        if 'sessions' in table_names:
            sessions = ss.execute("""
                SELECT id, title, created_at, summary 
                FROM sessions 
                ORDER BY created_at DESC 
                LIMIT 50
            """).fetchall()
            
            session_count = 0
            for s in sessions:
                text = f"Session: {s['title'] or 'Untitled'}\nDate: {s['created_at']}\nSummary: {s['summary'] or 'No summary'}"
                contextual = f"This section is from Hermes session history. Session: {s['title'] or 'Untitled'} on {s['created_at']}.\n\n{text}"
                
                conn.execute("""INSERT OR REPLACE INTO knowledge_documents 
                    (source, source_id, title, domain, source_path)
                    VALUES (?, ?, ?, ?, ?)""",
                    ("sessions", f"session-{s['id']}", s['title'] or f"Session {s['id']}", "general", ""))
                doc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                
                emb = get_embedding(contextual)
                conn.execute("""INSERT INTO knowledge_chunks 
                    (document_id, contextual_text, question, summary, embedding)
                    VALUES (?, ?, ?, ?, ?)""",
                    (doc_id, contextual, f"What happened in session {s['id']}?", s['summary'] or f"Session from {s['created_at']}", emb.tobytes()))
                session_count += 1
            
            conn.commit()
            print(f"  Indexed {session_count} past sessions")
        else:
            print("  No sessions table found")
        ss.close()
    else:
        print("  No sessions.db found (0 bytes or missing)")
except Exception as e:
    print(f"  Sessions error: {e}")

# === Stats ===
stats = conn.execute("""
    SELECT source, COUNT(*) as count FROM knowledge_documents GROUP BY source
""").fetchall()
print("\n=== Knowledge Base Stats ===")
for s in stats:
    print(f"  {s['source']}: {s['count']} documents")
total = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
print(f"  Total chunks: {total}")

conn.close()
print("\n✅ Additional data sources indexed")
