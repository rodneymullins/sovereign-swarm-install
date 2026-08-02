# Sovereign Swarm Installer

One-command install of the Hermes Agent Sovereign Swarm pipeline — a hardened 4-tier input processing system with health checks, fallback chains, circuit breakers, logging, metrics, caching, and validation.

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash
```

Or with interactive config:

```bash
curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash -s -- --configure
```

## What It Installs

| Component | Description |
|-----------|-------------|
| **Hermes Agent** | v0.19.1+ from GitHub |
| **4-Tier Pipeline** | Intent Gate → Distill → Evaluator → Heavy Reasoning |
| **Resilience Layer** | Health check, fallback chains, circuit breaker, logging, metrics, caching, validation, hard timeout |
| **11 Profiles** | pro-se, solar, systems, stochastic, interpersonal, offline, local-fast, local-heavy, cloud-brain, psychologist-child, orchestrator |
| **Ollama Models** | gemma4:12b + qwen3:0.6b for local fallback |

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

Run `configure.sh` after install to set up:

- **Your name** — for SOUL.md and AGENTS.md personalization
- **Ollama Max plan** — API endpoint for cloud models
- **Anthropic API key** — for vision model access
- **Local models** — whether to download fallback models
- **Profiles** — which domain profiles to enable
- **Defaults** — preferred model, output style, notification preferences

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
