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

Run the installer with `--configure` to set up your preferences:

```bash
curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash -s -- --configure
```

You'll be prompted for:

1. **Your profile** — name, description, use case
2. **Your domains** — define your own or use defaults (legal, finance, systems, solar, stochastic, interpersonal)
3. **Keywords** — what words trigger each domain
4. **Models** — Ollama endpoint, default model, distill model, reasoning model
5. **API keys** — Anthropic (optional, for vision)

### Customizing Domains

The pipeline classifies every message into a domain using keyword matching. You can define any domains you want:

```
Domain name: medical
  Keywords: doctor, diagnosis, treatment, prescription, patient, symptom
  Description: Healthcare, medical research, clinical trials

Domain name: gaming
  Keywords: game, steam, xbox, playstation, fps, rpg, multiplayer
  Description: Video games, game development, gaming hardware
```

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
