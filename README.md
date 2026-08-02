# Sovereign Swarm Installer

One-command install of the Hermes Agent Sovereign Swarm pipeline — a hardened 4-tier input processing system with health checks, fallback chains, circuit breakers, logging, metrics, caching, and validation.

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash
```

At launch, you'll be asked:

```
How would you like to configure?

  1) Default setup — quick install with standard domains
     (legal, finance, systems, solar, stochastic, interpersonal,
      health, career, education)

  2) Custom setup — choose your domains, keywords, models, and more

  Enter 1 or 2 [1]:
```

Pick **1** for a quick default install. Pick **2** for the full interactive config.

### Flags (skip the prompt)

```bash
# Default install (no prompt)
curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash -s -- --default

# Custom install (no prompt)
curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash -s -- --configure
```

## What It Installs

| Component | Description |
|-----------|-------------|
| **Hermes Agent** | v0.19.1+ from GitHub |
| **4-Tier Pipeline** | Intent Gate → Distill → Evaluator → Heavy Reasoning |
| **Resilience Layer** | Health check, fallback chains, circuit breaker, logging, metrics, caching, validation, hard timeout |
| **Domain Profiles** | One per default domain — legal, finance, systems, solar, stochastic, interpersonal, health, career, education, plus orchestrator |
| **Ollama Models** | gemma4:12b + qwen3:0.6b for local fallback |

## What You Can Add

The installer sets up the foundation. These optional components extend it:

| Component | What It Does | How to Add |
|-----------|-------------|------------|
| **Obsidian Vault** | Markdown knowledge base with 7,000+ indexed notes, entity profiles, case files, and reference materials | Clone or create a vault at `~/Obsidian-Vault/` |
| **GraphRAG** | Microsoft GraphRAG indexing — turns your vault into a queryable knowledge graph with semantic search, entity resolution, and community detection | Run `graphrag-indexing` skill after vault is set up |
| **Knowledge Base** | Hybrid search (semantic + FTS5) over distilled vault notes — 513 searchable chunks across all domains | Built-in via `knowledge_search.py` |
| **Cron Jobs** | 30+ automated tasks: solar watchdog, email triage, Kalshi tracker, vault ingestion, daily briefs, swing detection | Configured via `hermes cron` |

## Pipeline Architecture

```
User Message (6,000+ chars rambling)
    │
    ▼
Health Check (3s fast-fail)
    │
    ▼
Intent Gate → domain tag (word-boundary keywords, zero cost)
    │
    ▼
Distill → gemma4:31b-cloud → 60%+ reduction, grouped by topic
    │  Fallback: gpt-oss:20b-cloud → gemma4:12b → qwen3:0.6b → original
    │
    ▼
Evaluator Gate → can cheap model answer? (saves ~$0.02/query)
    │  Fallback: gpt-oss:20b-cloud → gemma4:12b → pass to heavy
    │
    ▼
Heavy Model → deepseek-v4-flash:cloud gets clean, organized input
    │
    ▼
Circuit Breaker (3 strikes, 5-min cooldown)
Logging (every step)
Metrics (view with pipeline_metrics.py)
Caching (LRU, 100 entries)
Validation (input/output)
Hard Timeout (15s kill switch)
```

## Configuration

Run the installer with `--configure` to set up your preferences:

```bash
curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash -s -- --configure
```

You'll be prompted for:

1. **Your profile** — name, description, use case
2. **Your domains** — define your own or use defaults (legal, finance, systems, solar, stochastic, interpersonal, health, career, education)
3. **Keywords** — what words trigger each domain
4. **Models** — Ollama endpoint, default model, distill model, reasoning model
5. **API keys** — Anthropic (optional, for vision)

### Customizing Domains

Domains are categories the pipeline uses to understand what you're talking about. Name them after your areas of work, interest, or expertise.

The configure script shows a **checkbox menu** of default domains. Toggle them on/off by number:

```
  [✓]  1) legal
  [✓]  2) finance
  [✓]  3) systems
  [ ]  4) solar
  [✓]  5) stochastic
  [✓]  6) interpersonal
  [✓]  7) health
  [✓]  8) career
  [✓]  9) education

  Toggle number (or blank to finish):
```

Then you can add custom domains. Each domain gets keywords and a description:

```
  ── cardiology ──
    Keywords are words that trigger this domain.
    Keywords (comma-separated): heart, artery, stent, bypass, echo, cholesterol
    Description (one line): Cardiology, cardiovascular health, heart disease treatment
```

**How it works:** Every message is checked against ALL domains' keywords. The domain with the most keyword matches wins. If nothing matches, it falls to "general". You can have as many domains as you want — the check is zero-cost (no model calls, just string matching).

**Tips for good domains:**
- Use short, descriptive names (snake_case if multi-word)
- Pick 5-15 keywords per domain that you actually use in conversation
- Don't overlap keywords between domains — if two domains share too many words, messages will bounce between them
- "general" is automatic — no need to define it

Each domain gets its own profile directory with the pre_process hook wired in.

### Manual Customization

Edit these files after install to tweak your setup:

| File | What to Change |
|------|----------------|
| `~/.hermes/scripts/pre_process.py` | `INTENT_KEYWORDS` dict — add/remove domains and keywords |
| `~/.hermes/SOUL.md` | Domain Boundaries section |
| `~/.hermes/AGENTS.md` | ASSUME section — your role and use case |
| `~/.hermes/skills/sovereign-swarm/skill.yaml` | `specialists` list |
| `~/.hermes/profiles/` | Add/remove profile directories |

### Re-running Configuration

```bash
# Re-run the interactive config
curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/scripts/configure.sh | bash
```

Or if you cloned the repo:

```bash
cd sovereign-swarm-install
bash scripts/configure.sh
```

## Requirements

- macOS (Apple Silicon)
- Homebrew
- 8GB+ RAM (16GB+ recommended)
- 10GB+ free disk space
- Ollama Max subscription (for cloud models) or local models

## File Structure

```
~/.hermes/
├── config.yaml          # Main configuration
├── SOUL.md              # Core identity & pipeline docs
├── AGENTS.md            # Agent instructions
├── scripts/
│   ├── pre_process.py   # Combined 4-tier pipeline
│   └── pipeline_metrics.py  # Metrics reporter
├── skills/
│   └── sovereign-swarm/
│       └── skill.yaml   # Pre_process hook
├── profiles/            # 11 domain profiles
├── logs/
│   └── pipeline.log     # Pipeline decisions
├── state/
│   ├── pipeline_metrics.json  # Usage stats
│   └── pipeline_circuit.json  # Circuit breaker state
└── cron/                # Scheduled jobs
```

## Viewing Metrics

```bash
python3 ~/.hermes/scripts/pipeline_metrics.py
```

Shows: domain distribution, distill success rate, evaluator hit rate, estimated savings, latency (avg/P50/P95), circuit opens, cache hits.

## License

MIT
