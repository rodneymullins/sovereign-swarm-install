#!/usr/bin/env python3
"""
Phase 1A: Vault Distillation Pipeline with Contextual Retrieval
Reads all reference notes, extracts sections, generates contextual text,
and writes to knowledge.db.
"""
import os, re, json, hashlib, sqlite3, yaml
from pathlib import Path
from datetime import datetime

VAULT = Path.home() / "Obsidian-Vault" / "08-Tools" / "References"
INBOX = Path.home() / "Obsidian-Vault" / "00-Inbox" / "raw"
DB_PATH = Path.home() / ".hermes" / "knowledge.db"

# Domain mapping from tags
DOMAIN_MAP = {
    "law": "legal", "legal": "legal", "court": "legal", "ohio": "legal",
    "systems": "systems", "hermes": "systems", "infrastructure": "systems",
    "solar": "solar", "chargepro": "solar", "energy": "solar",
    "casino": "casino", "kalshi": "casino", "gambling": "casino",
    "quant-trading": "casino",
    "design": "personal", "personal": "personal",
}

def parse_frontmatter(content):
    if not content.startswith('---'):
        return {}, content
    end = content.find('---', 3)
    if end == -1:
        return {}, content
    try:
        fm = yaml.safe_load(content[3:end])
        if fm is None:
            fm = {}
        body = content[end+3:]
        return fm, body
    except:
        return {}, content

def get_title(fm, content, fname):
    if 'title' in fm:
        return fm['title']
    for line in content.split('\n'):
        if line.startswith('# '):
            return line[2:].strip()
    return fname.replace('.md', '').replace('-', ' ').title()

def extract_sections(body):
    """Split markdown body into sections by ## headings."""
    sections = []
    lines = body.split('\n')
    current_heading = "Overview"
    current_lines = []
    
    for line in lines:
        if line.startswith('## '):
            if current_lines:
                sections.append((current_heading, '\n'.join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = []
        elif line.startswith('# '):
            continue  # Skip main title
        else:
            current_lines.append(line)
    
    if current_lines:
        sections.append((current_heading, '\n'.join(current_lines).strip()))
    
    return sections

def generate_contextual_text(doc_title, section_heading, section_text, tags):
    """Prepend document context to chunk text (Anthropic method)."""
    tag_str = ", ".join(tags[:5]) if tags else ""
    context = f"This section is from {doc_title}. Section: {section_heading}. Tags: {tag_str}."
    return f"{context}\n\n{section_text}"

def generate_artifact(doc_title, section_heading, section_text, tags):
    """Generate structured artifact from section content."""
    # Question: derived from heading
    question = f"What does {doc_title} say about {section_heading.lower()}?"
    
    # Summary: first meaningful sentence
    summary = ""
    for line in section_text.split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('---') and not line.startswith('['):
            summary = line[:200]
            break
    
    # Resolution: the key actionable content
    resolution = section_text[:500]
    
    # Code refs: extract rule numbers, ORC citations, form numbers
    code_refs = []
    for match in re.finditer(r'(Ham\.\s*Juv\.\s*R\.\s*\d+|R\.C\.\s*\d+\.\d+|Sup\.\s*R\.\s*\d+|Civ\.\s*R\.\s*[\d\.]+|Juv\.\s*R\.\s*[\d\.]+|ORC\s*\d+\.\d+)', section_text, re.IGNORECASE):
        code_refs.append(match.group(0))
    
    return question, summary, resolution, list(set(code_refs))

def get_file_hash(path):
    return hashlib.md5(path.read_bytes()).hexdigest()

def process_directory(conn, directory, source_name, now):
    processed = 0
    skipped = 0
    new_chunks = 0
    
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith('.md') or fname.startswith('_'):
            continue
        
        fpath = directory / fname
        content = fpath.read_text(encoding='utf-8')
        file_hash = get_file_hash(fpath)
        
        # Check if already synced
        cursor = conn.execute("SELECT file_hash FROM knowledge_sync WHERE source=? AND source_id=?", (source_name, fname))
        row = cursor.fetchone()
        if row and row['file_hash'] == file_hash:
            skipped += 1
            continue
        
        # Parse frontmatter
        fm, body = parse_frontmatter(content)
        title = get_title(fm, content, fname)
        tags = fm.get('tags', [])
        
        # Determine domain
        domain = "general"
        for t in tags:
            if t in DOMAIN_MAP:
                domain = DOMAIN_MAP[t]
                break
        
        # Extract sections
        sections = extract_sections(body)
        if not sections:
            sections = [("Overview", body[:1000])]
        
        # Write parent document
        metadata = json.dumps({
            "tags": tags,
            "created": fm.get('created', ''),
            "updated": fm.get('updated', ''),
            "confidence": fm.get('confidence', ''),
            "sources": fm.get('sources', []),
        })
        
        conn.execute("""
            INSERT OR REPLACE INTO knowledge_documents 
            (source, source_id, source_path, domain, title, full_text, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (source_name, fname, str(fpath), domain, title, content, metadata, now, now))
        
        doc_id = conn.execute("SELECT id FROM knowledge_documents WHERE source=? AND source_id=?", (source_name, fname)).fetchone()['id']
        
        # Delete old chunks for this document
        conn.execute("DELETE FROM knowledge_chunks WHERE document_id=?", (doc_id,))
        
        # Write chunks
        for idx, (heading, section_text) in enumerate(sections):
            if len(section_text) < 20:
                continue
            
            contextual = generate_contextual_text(title, heading, section_text, tags)
            question, summary, resolution, code_refs = generate_artifact(title, heading, section_text, tags)
            
            conn.execute("""
                INSERT INTO knowledge_chunks 
                (document_id, section_heading, chunk_index, contextual_text, question, summary, resolution, systems, code_refs, char_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, heading, idx, contextual, question, summary, resolution, json.dumps(tags[:10]), json.dumps(code_refs), len(contextual), now))
            new_chunks += 1
        
        # Update sync tracking
        conn.execute("""
            INSERT OR REPLACE INTO knowledge_sync (source, source_id, file_hash, last_synced)
            VALUES (?, ?, ?, ?)
        """, (source_name, fname, file_hash, now))
        
        processed += 1
        print(f"  ✓ {fname} ({len(sections)} sections, {domain})")
    
    return processed, skipped, new_chunks

def process_vault():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    now = int(datetime.now().timestamp())
    
    # Process References
    print("=== 08-Tools/References ===")
    p1, s1, c1 = process_directory(conn, VAULT, 'vault', now)
    
    # Process Inbox
    print("=== 00-Inbox/raw ===")
    p2, s2, c2 = process_directory(conn, INBOX, 'inbox', now)
    
    conn.commit()
    
    # Rebuild FTS index
    conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
    conn.commit()
    
    conn.close()
    
    total_p = p1 + p2
    total_s = s1 + s2
    total_c = c1 + c2
    print(f"\nProcessed: {total_p}, Skipped: {total_s}, New chunks: {total_c}")
    return total_p, total_s, total_c

if __name__ == "__main__":
    print("Vault Distillation Pipeline — Phase 1A")
    print("=" * 50)
    process_vault()
