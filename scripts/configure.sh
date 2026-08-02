#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Sovereign Swarm — Interactive Configuration Script
# Collects user preferences, then calls generate_config.py to produce
# custom pre_process.py, SOUL.md, AGENTS.md, and skill.yaml from templates.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }

HERMES_HOME="${HOME}/.hermes"
CONFIG_FILE="${HERMES_HOME}/config.yaml"
SCRIPTS_DIR="${HERMES_HOME}/scripts"
SKILLS_DIR="${HERMES_HOME}/skills"
PROFILES_DIR="${HERMES_HOME}/profiles"

# Find template directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATES_DIR="${REPO_DIR}/templates"
GENERATOR="${SCRIPT_DIR}/generate_config.py"

echo -e "\n${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Sovereign Swarm — Configuration${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}\n"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: User Profile
# ══════════════════════════════════════════════════════════════════════════════
echo -e "${YELLOW}── User Profile ──${NC}"
read -p "Your name: " USER_NAME
USER_NAME="${USER_NAME:-User}"

read -p "Brief description of who you are (e.g. 'software developer', 'small business owner', 'pro se litigant'): " USER_DESCRIPTION
USER_DESCRIPTION="${USER_DESCRIPTION:-a user of the Sovereign Swarm}"

read -p "Primary use case (e.g. 'legal research', 'coding assistant', 'business analytics'): " USE_CASE
USE_CASE="${USE_CASE:-general assistance}"

ok "Profile: ${USER_NAME} — ${USER_DESCRIPTION}"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Domain Configuration
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}── Domain Configuration ──${NC}"
echo "Domains are categories the pipeline uses to understand what you're talking about."
echo "Name them after your areas of work, interest, or expertise."
echo ""
echo "  Examples:"
echo "    A doctor might use:  cardiology, radiology, pediatrics, practice_management"
echo "    A gamer might use:   fps_games, rpgs, hardware_builds, streaming"
echo "    A lawyer might use:  family_law, criminal_defense, contracts, appeals"
echo "    A trader might use:  crypto, equities, options, macro_economics"
echo ""
echo "Default domains: legal, finance, systems, solar, stochastic, interpersonal"
read -p "Customize domains? (y/N): " CUSTOM_DOMAINS

DOMAINS=()
declare -A DOMAIN_KEYWORDS
declare -A DOMAIN_DESCRIPTIONS

if [[ "$CUSTOM_DOMAINS" =~ ^[Yy] ]]; then
    echo ""
    echo "Enter your domain names, one per line. Empty line to finish."
    echo "Use short, descriptive names (snake_case if multi-word)."
    while true; do
        read -p "  Domain name (or blank to finish): " domain
        [[ -z "$domain" ]] && break
        domain=$(echo "$domain" | tr '[:upper:]' '[:lower:]' | tr ' ' '_' | sed 's/[^a-z0-9_]//g')
        DOMAINS+=("$domain")
    done

    for domain in "${DOMAINS[@]}"; do
        echo ""
        echo "  Domain: ${domain}"
        echo "    Keywords are words that trigger this domain. When you use them,"
        echo "    the pipeline knows what you're talking about."
        read -p "    Keywords (comma-separated, e.g. court, judge, filing): " keywords
        DOMAIN_KEYWORDS["$domain"]="$keywords"
        echo "    Description appears in SOUL.md and helps the agent understand the domain."
        read -p "    Description (one line, e.g. 'Legal research, court filings, case law'): " desc
        DOMAIN_DESCRIPTIONS["$domain"]="$desc"
    done
else
    DOMAINS=("legal" "finance" "systems" "solar" "stochastic" "interpersonal")
    DOMAIN_KEYWORDS["legal"]="court, custody, filing, motion, judge, subpoena, contempt, trial, evidence, hearing, plaintiff, defendant, petition, order, decree, attorney, lawyer, legal, statute, docket, brief, objection, appeal, affidavit, complaint, summons, discovery, deposition"
    DOMAIN_DESCRIPTIONS["legal"]="Law, custody, filings, motions, trial prep, court rules"
    DOMAIN_KEYWORDS["finance"]="money, cost, fee, bill, income, expense, budget, payment, receipt, invoice, debt, credit, pay, bank, account, dollar, paypal, venmo, financial"
    DOMAIN_DESCRIPTIONS["finance"]="Income, expenses, court costs, fee waivers, billing, assets"
    DOMAIN_KEYWORDS["systems"]="computer, config, cron, gateway, hermes, mlx, hardware, script, ollama, tui, dashboard, profile, process, install, update, upgrade, deploy, server, ssh, terminal, python, git, repo, mac, linux, disk, memory, cpu, gpu, token, model, api, provider"
    DOMAIN_DESCRIPTIONS["systems"]="MLX, Ollama, Hermes config, cron, gateway, hardware"
    DOMAIN_KEYWORDS["solar"]="battery, voltage, panel, chargepro, inverter, power, energy, charge, solar, lifepo4, watt, volt, amp, ble, controller"
    DOMAIN_DESCRIPTIONS["solar"]="Charge controllers, battery, panels, inverter, power budget"
    DOMAIN_KEYWORDS["stochastic"]="casino, slot, vlt, gambling, probability, odds, kalshi, trade, bet, expected value, advantage, stochastic, market, mlb, nfl, nba"
    DOMAIN_DESCRIPTIONS["stochastic"]="Gambling, probability, expected value, casino strategy"
    DOMAIN_KEYWORDS["interpersonal"]="psychology, relationship, family, communication, attachment, therapy, counseling, emotion, borderline, narcissist, alienation"
    DOMAIN_DESCRIPTIONS["interpersonal"]="Psychology, relationships, communication, family dynamics"
fi

# Build domain list string
DOMAIN_LIST=""
for d in "${DOMAINS[@]}"; do
    DOMAIN_LIST+="${d}, "
done
DOMAIN_LIST="${DOMAIN_LIST%, }"

ok "${#DOMAINS[@]} domains configured: ${DOMAIN_LIST}"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Model Configuration
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}── Model Configuration ──${NC}"
read -p "Ollama API endpoint [http://127.0.0.1:11434/v1]: " OLLAMA_ENDPOINT
OLLAMA_ENDPOINT="${OLLAMA_ENDPOINT:-http://127.0.0.1:11434/v1}"

read -p "Default model [deepseek-v4-flash:cloud]: " DEFAULT_MODEL
DEFAULT_MODEL="${DEFAULT_MODEL:-deepseek-v4-flash:cloud}"

read -p "Distill model [gemma4:31b-cloud]: " DISTILL_MODEL
DISTILL_MODEL="${DISTILL_MODEL:-gemma4:31b-cloud}"

read -p "Heavy reasoning model [deepseek-v4-flash:cloud]: " REASONING_MODEL
REASONING_MODEL="${REASONING_MODEL:-deepseek-v4-flash:cloud}"

echo ""
echo -e "${YELLOW}── Anthropic (Vision) — Optional ──${NC}"
echo "Used for image analysis. Leave blank to skip."
read -p "Anthropic API key (sk-ant-...): " ANTHROPIC_KEY

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Generate Files from Templates
# ══════════════════════════════════════════════════════════════════════════════
echo ""
info "Generating configuration files from templates..."

# Build JSON for Python generator
DOMAINS_JSON=$(printf '%s\n' "${DOMAINS[@]}" | python3 -c "import json,sys; print(json.dumps([l.strip() for l in sys.stdin]))")

KEYWORDS_JSON="{"
first=true
for d in "${DOMAINS[@]}"; do
    $first || KEYWORDS_JSON+=", "
    first=false
    KEYWORDS_JSON+="\"$d\": \"${DOMAIN_KEYWORDS[$d]}\""
done
KEYWORDS_JSON+="}"

DESCRIPTIONS_JSON="{"
first=true
for d in "${DOMAINS[@]}"; do
    $first || DESCRIPTIONS_JSON+=", "
    first=false
    DESCRIPTIONS_JSON+="\"$d\": \"${DOMAIN_DESCRIPTIONS[$d]}\""
done
DESCRIPTIONS_JSON+="}"

# Export to environment for Python generator
export TEMPLATES_DIR SCRIPTS_DIR
export SOUL_PATH="${HERMES_HOME}/SOUL.md"
export AGENTS_PATH="${HERMES_HOME}/AGENTS.md"
export SKILL_PATH="${SKILLS_DIR}/sovereign-swarm/skill.yaml"
export DOMAINS_JSON KEYWORDS_JSON DESCRIPTIONS_JSON
export USER_DESCRIPTION USE_CASE DISTILL_MODEL REASONING_MODEL

python3 "$GENERATOR"

ok "Configuration files generated"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Write config.yaml
# ══════════════════════════════════════════════════════════════════════════════
info "Writing config.yaml..."

DATE=$(date +%Y-%m-%d)

CLOUD_MODELS=$(cat << 'CMDEOF'
      - deepseek-v4-flash:cloud
      - deepseek-v4-pro:cloud
      - gemma4:31b-cloud
      - gpt-oss:20b-cloud
      - gpt-oss:120b-cloud
      - gemma4:cloud
      - minimax-m2.1:cloud
      - gemini-3-flash-preview:cloud
      - glm-4.7:cloud
      - kimi-k2.5:cloud
      - kimi-k2.6:cloud
      - minimax-m2.5:cloud
      - glm-5:cloud
      - minimax-m2.7:cloud
      - minimax-m3:cloud
      - kimi-k2.7-code:cloud
      - nemotron-3-super:cloud
      - glm-5.1:cloud
      - rnj-1:8b-cloud
      - glm-5.2:cloud
      - max:latest
      - fast:latest
      - offline:latest
CMDEOF
)

cat > "$CONFIG_FILE" << CONFIGEOF
# ── Hermes Agent Configuration — Sovereign Swarm ──
# Generated by configure.sh on ${DATE}

model:
  base_url: ''
  default: ${DEFAULT_MODEL}
  provider: ollama-launch

providers:
  ollama-launch:
    api: ${OLLAMA_ENDPOINT}
    default_model: ${DEFAULT_MODEL}
    models:
${CLOUD_MODELS}
    name: Ollama
CONFIGEOF

if [[ -n "$ANTHROPIC_KEY" ]]; then
    cat >> "$CONFIG_FILE" << ANTHROPICEOF

  anthropic:
    api: https://api.anthropic.com/v1
    api_key: ${ANTHROPIC_KEY}
    default_model: claude-sonnet-4-20250514
    models:
      - claude-sonnet-4-20250514
      - claude-sonnet-5
      - claude-fable-5
    name: Anthropic
ANTHROPICEOF
fi

cat >> "$CONFIG_FILE" << CONFIGEOF2

fallback_providers: []

toolsets:
  - hermes-cli
  - web

max_live_sessions: 16

agent:
  max_turns: 90
  gateway_timeout: 1800
  restart_drain_timeout: 180
  api_max_retries: 3
  service_tier: ''
  tool_use_enforcement: auto
  task_completion_guidance: true
  parallel_tool_call_guidance: true
  environment_probe: true
  environment_hint: ''
  coding_context: auto
  verify_on_stop: false
  gateway_timeout_warning: 900
  clarify_timeout: 600
  gateway_notify_interval: 180
  gateway_auto_continue_freshness: 3600
  image_input_mode: auto
  disabled_toolsets: []
  personalities: '{"legal-drafter": "You are a legal drafting assistant for a pro se litigant. Use IRAC format (Issue, Rule, Analysis, Conclusion) for all analysis. Cite relevant state law: revised codes, civil rules, supreme court rules, and local court rules. Write for a family court judge. Be precise, cite specific statutes and rules, and flag evidentiary issues (hearsay, relevance, evidentiary rules, foundation) proactively.", "cross-exam": "You are a cross-examination strategist for a pro se litigant in a custody trial. Focus on impeachment, internal contradiction, and foundational attacks. Flag hearsay, relevance, evidentiary rules, and lack of foundation proactively. Structure questions as short, leading, closed-ended. One fact per question. Never ask a question you don''t already know the answer to. Identify impeachment targets from contradictory evidence.", "concise": "One sentence answers. No formatting. No explanations unless asked. State the fact or answer directly and stop."}'

terminal:
  backend: local
  modal_mode: auto
  cwd: .
  timeout: 180
  daemon_term_grace_seconds: 2
  env_passthrough: []
  home_mode: auto
  shell_init_files: []

web:
  backend: ddgs
  search_backend: ddgs
  extract_backend: ddgs

compression:
  enabled: true
  threshold: 0.5
  target_ratio: 0.2

auxiliary:
  vision:
    provider: ollama-launch
    model: minicpm-v4.6:1b

display:
  tool_progress: all

memory:
  memory_char_limit: 3000

delegation:
  model: ${DISTILL_MODEL}
  provider: ollama-launch
  child_timeout_seconds: 300
  max_concurrent_children: 8
  max_spawn_depth: 1

kanban:
  dispatch_in_gateway: true
  dispatch_interval_seconds: 60
  orchestrator_profile: orchestrator
  auto_decompose: true
  auto_decompose_per_tick: 3

plugins:
  enabled: []

tts:
  provider: edge
  voice: en-US-JennyNeural
  speed: 1.0

vision_provider: anthropic
vision_model: claude-sonnet-4-20250514
CONFIGEOF2
ok "config.yaml written"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: Create Profiles
# ══════════════════════════════════════════════════════════════════════════════
info "Creating profiles..."

for domain in "${DOMAINS[@]}"; do
    mkdir -p "${PROFILES_DIR}/${domain}/skills/sovereign-swarm"
    mkdir -p "${PROFILES_DIR}/${domain}/cron"
    mkdir -p "${PROFILES_DIR}/${domain}/plugins"
    mkdir -p "${PROFILES_DIR}/${domain}/memories"
    cp "${SKILLS_DIR}/sovereign-swarm/skill.yaml" "${PROFILES_DIR}/${domain}/skills/sovereign-swarm/skill.yaml"
done

# Always create orchestrator profile
mkdir -p "${PROFILES_DIR}/orchestrator/skills/sovereign-swarm"
mkdir -p "${PROFILES_DIR}/orchestrator/cron"
mkdir -p "${PROFILES_DIR}/orchestrator/plugins"
mkdir -p "${PROFILES_DIR}/orchestrator/memories"
cp "${SKILLS_DIR}/sovereign-swarm/skill.yaml" "${PROFILES_DIR}/orchestrator/skills/sovereign-swarm/skill.yaml"

ok "${#DOMAINS[@]} domain profiles + orchestrator created"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 7: Verify
# ══════════════════════════════════════════════════════════════════════════════
info "Verifying generated files..."

ERRORS=0
for f in "$CONFIG_FILE" "${HERMES_HOME}/SOUL.md" "${HERMES_HOME}/AGENTS.md" "${SCRIPTS_DIR}/pre_process.py" "${SKILLS_DIR}/sovereign-swarm/skill.yaml"; do
    if [[ -f "$f" ]]; then
        ok "  $(basename "$f")"
    else
        warn "  MISSING: $f"
        ERRORS=$((ERRORS+1))
    fi
done

if echo "What is the capital of France?" | python3 "${SCRIPTS_DIR}/pre_process.py" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['evaluator_answered']==True" 2>/dev/null; then
    ok "  Pipeline test passed"
else
    warn "  Pipeline test failed — check Ollama is running"
    ERRORS=$((ERRORS+1))
fi

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Configuration Complete${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${GREEN}User:${NC}         ${USER_NAME}"
echo -e "  ${GREEN}Domains:${NC}      ${DOMAIN_LIST}"
echo -e "  ${GREEN}Default model:${NC} ${DEFAULT_MODEL}"
echo -e "  ${GREEN}Distill model:${NC} ${DISTILL_MODEL}"
echo -e "  ${GREEN}Reasoning:${NC}    ${REASONING_MODEL}"
echo -e "  ${GREEN}Profiles:${NC}     ${DOMAINS[*]} orchestrator"
echo ""
echo -e "  ${YELLOW}Start Hermes:${NC}  hermes"
echo -e "  ${YELLOW}View metrics:${NC}  python3 ${SCRIPTS_DIR}/pipeline_metrics.py"
echo ""

if [[ $ERRORS -gt 0 ]]; then
    echo -e "  ${RED}${ERRORS} warnings/errors — review above.${NC}"
else
    echo -e "  ${GREEN}All checks passed. Ready to go.${NC}"
fi
echo ""
