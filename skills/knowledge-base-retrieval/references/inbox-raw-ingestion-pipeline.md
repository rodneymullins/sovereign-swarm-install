# Inbox/Raw Ingestion Pipeline

## Pattern

User shares X thread / article / paper → extract content via browser → write structured markdown to `00-Inbox/raw/` → morning cron classifies and files → knowledge_distill indexes.

## Why This Works

- `00-Inbox/raw/` is scanned by `knowledge_distill.py` (source='inbox') alongside `08-Tools/References` (source='vault')
- The morning cron (`vault-morning-cron.py`) processes inbox items, classifies them, and moves them to the appropriate vault directory
- After classification, `knowledge_distill.py` picks them up on its next run (every 6h)
- Result: X threads become searchable knowledge base entries within 24 hours

## File Format

```markdown
---
date: YYYY-MM-DD
source: https://x.com/user/status/123456
author: "@username"
tags:
  - relevant
  - tags
  - here
---

# Title

## Summary

Key points extracted from the thread.

## Swarm Relevance

How this applies to our infrastructure, pipeline, or strategy.
```

## When to File

- Research papers, frameworks, or architectures that validate or extend our approach
- New models or tools relevant to the Swarm
- Infrastructure discoveries (CUDA on Apple Silicon, etc.)
- Health/performance knowledge the user cares about
- Trading/strategy patterns applicable to Kalshi

## When NOT to File

- General news or entertainment
- Threads the user shares for quick consumption only
- Duplicate topics already well-covered in the vault

## Index Update

After filing, update `~/Obsidian-Vault/INDEX.md` with the new entry under the appropriate section. This ensures the entry is discoverable before the morning cron runs.
