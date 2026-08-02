<div align="center">
  <h1>🧠 Sovereign Swarm</h1>
  <p><strong>Turn Hermes Agent into a self-healing, domain-aware reasoning engine</strong></p>
  <p>
    <a href="#-quick-install">Install</a> •
    <a href="#-why-sovereign-swarm">Why</a> •
    <a href="#-how-it-works">How It Works</a> •
    <a href="#-pipeline-architecture">Architecture</a> •
    <a href="#-configuration">Configure</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/macOS-Apple_Silicon-brightgreen" alt="macOS">
    <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT">
    <img src="https://img.shields.io/badge/hermes-v0.19.1+-purple" alt="Hermes">
  </p>
</div>

> **You ramble. It cleans. You get better answers.**

---

## 📦 Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash
```

At launch, pick your path:

```
How would you like to configure?

  1) Default setup — quick install with standard domains
  2) Custom setup — choose your domains, keywords, models, and more

  Enter 1 or 2 [1]:
```

**Option 1** — up and running in 2 minutes. **Option 2** — full control.

### Flags (skip the prompt)

```bash
# Quick default
curl -fsSL ... | bash -s -- --default

# Full interactive config
curl -fsSL ... | bash -s -- --configure
```

---

## 🤔 Why Sovereign Swarm?

Hermes Agent is powerful out of the box. But it has one problem: **every message costs the same as every other message.** A simple "what time is it?" burns the same tokens as drafting a legal motion. The heavy model reads your full conversation history just to figure out what domain you're talking about.

**Sovereign Swarm fixes that.** It adds a lightweight pre-processing layer that runs *before* the heavy model ever sees your message. This layer:

| Problem | Hermes Alone | With Sovereign Swarm |
|---------|-------------|---------------------|
| **Context bloat** | Heavy model reads 20K+ tokens of history just to classify your domain | Classification happens in a zero-cost keyword matcher before the model runs |
| **Wasted tokens on filler** | "So like, I was thinking, you know, maybe we could..." goes straight to the expensive model | Filler is stripped by a cheap model first — the heavy model gets clean, structured input |
| **Simple questions cost the same** | "What's the capital of France?" costs $0.02+ | Evaluator gate catches simple queries and answers them directly — heavy model never called |
| **No failure recovery** | If Ollama hiccups, the message fails silently | Health check, fallback chains, and circuit breaker keep the pipeline running |
| **No visibility** | No way to see what's happening inside | Every decision logged. Metrics on evaluator hit rate, latency, savings. |
| **One-size-fits-all** | Same system prompt for every topic | Domain-tagged routing — legal gets legal treatment, health gets health treatment |

**Bottom line:** Sovereign Swarm makes Hermes **faster, cheaper, and more reliable** without changing how you talk to it. You ramble. It cleans. You get better answers.

> **You ramble. It cleans. You get better answers.**

---

## 🏗️ How It Works

Every message passes through 4 tiers before the heavy model sees it:

```
You type: "So like, I was thinking about the custody case and I feel like we need to file
          a motion for contempt because the other side missed the last three weekends..."

         ▼
[Tier 1: Intent Gate]  ← Zero cost, zero latency
  Scans for keywords → "legal" domain
  (court, custody, motion, contempt, trial...)

         ▼
[Tier 2: Distill]  ← Cheap model (gemma4:31b-cloud)
  Strips filler, restructures:
  "File a contempt motion in the custody case.
   The other side missed three visitation weekends.
   Decide between show-cause and straight contempt."

         ▼
[Tier 3: Evaluator Gate]  ← Same cheap model
  "Can I answer this without tools or research?"
  → NO (needs legal research) → passes to heavy model
  → YES ("What's the capital of France?") → answers directly, saves $0.02

         ▼
[Tier 4: Heavy Reasoning]  ← deepseek-v4-flash:cloud
  Gets clean, organized input. No filler. No history bloat.
  Produces better answers, faster.
```

**Real result from a 6,232-character ramble:**

> *"File a contempt motion in the custody case. The other side missed three visitation weekends. Decide between a show-cause motion and a straight contempt motion. Check if a fee waiver applies to post-decree motions. Verify the solar battery voltage; it may be low due to little sun. Confirm whether the new model download has finished. Tell the client the court has not set a visitation date yet."*

**61% reduction.** Every topic extracted. Every filler word removed. The heavy model gets clean, organized input instead of a wall of text.

---

## 🛡️ Resilience Features

| Feature | What It Does |
|---------|-------------|
| **Health Check** | Verifies Ollama is running before any API call. Fails fast (3s) instead of waiting 30s. |
| **Fallback Chains** | If the primary cloud model fails, falls back to other cloud models before returning the original text. |
| **Circuit Breaker** | After 3 consecutive API failures, stops trying for 5 minutes. Prevents cascading failures. State persists across restarts. |
| **Logging** | Every pipeline decision logged with timestamps and latency. View at `~/.hermes/logs/pipeline.log`. |
| **Metrics** | Tracks evaluator hit rate, distill success rate, latency (avg/P50/P95), domain distribution, circuit opens, cache hits. |
| **Caching** | LRU cache (100 entries) for repeated queries. Same question twice? Second call is instant. |
| **Input/Output Validation** | Rejects empty/binary/overlong input. Validates output has all required fields. Safe fallback on failure. |
| **Hard Timeout** | 15-second kill switch prevents the script from hanging. Returns safe fallback if exceeded. |

---

## 🎯 Domain Customization

The pipeline classifies every message into a domain. You define what matters to you.

**Default domains:** legal, finance, systems, solar, stochastic, interpersonal, health, career, education

**Or define your own.** The configure script shows a checkbox menu:

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

Toggle on/off. Add custom domains. Each gets its own keywords, description, and profile.

**Examples of custom domains:**

| Person | Domains |
|--------|---------|
| **Doctor** | cardiology, radiology, pediatrics, practice_management |
| **Gamer** | fps_games, rpgs, hardware_builds, streaming |
| **Lawyer** | family_law, criminal_defense, contracts, appeals |
| **Trader** | crypto, equities, options, macro_economics |
| **Student** | math, physics, history, study_skills |
| **Parent** | health, education, activities, budgeting |

**How it works:** Every message is checked against ALL domains' keywords. The domain with the most keyword matches wins. If nothing matches, it falls to "general". Zero model calls, zero latency — just string matching.

---

## 📊 Viewing Metrics

```bash
python3 ~/.hermes/scripts/pipeline_metrics.py
```

```
==================================================
  Pipeline Metrics Report
==================================================
  Total queries:     47

  ── By Domain ──
    legal           22 (46.8%) ██████████░
    systems         12 (25.5%) █████░░░░░░
    solar            6 (12.8%) ██░░░░░░░░░
    general          7 (14.9%) ███░░░░░░░░

  ── Distill ──
    Success rate:    45/47 (95.7%)
    Fallback used:   2 times

  ── Evaluator Gate ──
    Hit rate:        8/32 (25.0%)
    Est. savings:    $0.16

  ── Latency ──
    Average:         1526 ms
    Median (P50):    1703 ms
    P95:             1833 ms

  ── Health ──
    Circuit opens:   0
    Health failures: 1
    Cache hits:      3
```

---

## 📁 What Gets Installed

```
~/.hermes/
├── config.yaml              # Main configuration
├── SOUL.md                  # Core identity & pipeline docs
├── AGENTS.md                # Agent instructions
├── scripts/
│   ├── pre_process.py       # Combined 4-tier pipeline
│   ├── pipeline_metrics.py  # Metrics reporter
│   ├── configure.sh         # Interactive config
│   └── generate_config.py   # Template-based file generator
├── skills/
│   └── sovereign-swarm/
│       └── skill.yaml       # Pre_process hook (fires on every message)
├── profiles/                # One per domain
│   ├── legal/
│   ├── finance/
│   ├── systems/
│   ├── ...
│   └── orchestrator/
├── logs/
│   └── pipeline.log         # Every decision, timestamped
├── state/
│   ├── pipeline_metrics.json
│   └── pipeline_circuit.json
└── cron/                    # Scheduled jobs
```

---

## 🔧 Requirements

- **macOS** (Apple Silicon)
- **Homebrew**
- **8GB+ RAM** (16GB+ recommended)
- **10GB+ free disk space**
- **Ollama** (with Ollama Pro subscription for cloud models)

---

## 🧩 Optional Add-Ons

| Component | What It Does | How to Add |
|-----------|-------------|------------|
| **GraphRAG** | Microsoft GraphRAG — turns your vault into a queryable knowledge graph with semantic search | **Installed by default** — run `cd ~/.hermes/graphrag && graphrag index --root .` |
| **Knowledge Base** | Hybrid search (semantic + FTS5) over distilled notes — 500+ searchable chunks | **Installed by default** — run `python3 ~/.hermes/scripts/knowledge_distill.py` to index your vault |
| **Cron Jobs** | Automated tasks: monitoring, notifications, data collection, daily briefs | Configured via `hermes cron` |

---

## 📝 License

MIT

---

<div align="center">
  <p>Built by <a href="https://github.com/rodneymullins">rodneymullins</a> · Sovereign Swarm</p>
</div>
