#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Sovereign Swarm Installer — One-command Hermes Agent + Pipeline Setup
# Usage: curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash
#        curl -fsSL https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main/install.sh | bash -s -- --configure
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $1"; exit 1; }

# ── Detect if --configure flag was passed ──
RUN_CONFIGURE=false
for arg in "$@"; do
    if [[ "$arg" == "--configure" || "$arg" == "-c" ]]; then
        RUN_CONFIGURE=true
    fi
done

# ── Paths ──
HERMES_HOME="${HOME}/.hermes"
HERMES_REPO="${HERMES_HOME}/hermes-agent"
SCRIPTS_DIR="${HERMES_HOME}/scripts"
SKILLS_DIR="${HERMES_HOME}/skills"
STATE_DIR="${HERMES_HOME}/state"
LOGS_DIR="${HERMES_HOME}/logs"
CRON_DIR="${HERMES_HOME}/cron"
PLANS_DIR="${HERMES_HOME}/plans"
PROFILES_DIR="${HERMES_HOME}/profiles"
REPO_URL="https://github.com/rodneymullins/sovereign-swarm-install.git"
RAW_BASE="https://raw.githubusercontent.com/rodneymullins/sovereign-swarm-install/main"

echo -e "\n${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Sovereign Swarm Installer${NC}"
echo -e "${CYAN}  Hermes Agent + 4-Tier Pipeline + 11 Profiles${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}\n"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 0: Prerequisites
# ══════════════════════════════════════════════════════════════════════════════
info "Checking prerequisites..."

if [[ "$(uname)" != "Darwin" ]]; then
    warn "This script is designed for macOS (Apple Silicon)."
    warn "Continuing anyway — some paths may differ on $(uname)."
fi

if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
ok "Homebrew: $(brew --version 2>/dev/null | head -1)"

PYTHON=$(command -v python3 || true)
if [[ -z "$PYTHON" ]]; then
    info "Installing Python..."
    brew install python@3.11
    PYTHON=$(command -v python3)
fi
PYVER=$($PYTHON --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
if (( $(echo "$PYVER < 3.10" | bc -l) )); then
    fail "Python 3.10+ required, got $PYVER"
fi
ok "Python: $($PYTHON --version 2>&1)"

if ! command -v git &>/dev/null; then
    info "Installing Git..."
    brew install git
fi
ok "Git: $(git --version 2>&1)"

if ! command -v ollama &>/dev/null; then
    info "Installing Ollama..."
    brew install ollama
    info "Starting Ollama server..."
    ollama serve &>/dev/null &
    sleep 3
fi
ok "Ollama: $(ollama --version 2>&1)"

# ── Create directory structure ──
info "Creating directory structure..."
mkdir -p "$SCRIPTS_DIR" "$STATE_DIR" "$LOGS_DIR" "$CRON_DIR" "$PLANS_DIR"
mkdir -p "$SKILLS_DIR" "$PROFILES_DIR"
mkdir -p "${SCRIPTS_DIR}/legacy"
ok "Directories created"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Install Hermes Agent
# ══════════════════════════════════════════════════════════════════════════════
info "Installing Hermes Agent..."

if [[ -d "$HERMES_REPO" ]]; then
    warn "Hermes already installed at $HERMES_REPO"
    info "Updating..."
    cd "$HERMES_REPO"
    git pull --ff-only 2>/dev/null || warn "Could not pull (local changes?)"
else
    git clone https://github.com/NousResearch/hermes-agent.git "$HERMES_REPO"
    cd "$HERMES_REPO"
fi

$PYTHON -m pip install -e "$HERMES_REPO" 2>/dev/null || \
    $PYTHON -m pip install --user -e "$HERMES_REPO"

if command -v hermes &>/dev/null; then
    ok "Hermes: $(hermes --version 2>&1)"
else
    warn "hermes command not in PATH — adding to ~/.zshrc"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
    export PATH="$HOME/.local/bin:$PATH"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Download Pipeline Files from GitHub
# ══════════════════════════════════════════════════════════════════════════════
info "Downloading pipeline files..."

download_file() {
    local url="$1"
    local dest="$2"
    mkdir -p "$(dirname "$dest")"
    if curl -fsSL "$url" -o "$dest"; then
        ok "  Downloaded $(basename "$dest")"
    else
        fail "  Failed to download $url"
    fi
}

# Download core pipeline files
download_file "${RAW_BASE}/scripts/pre_process.py" "${SCRIPTS_DIR}/pre_process.py"
download_file "${RAW_BASE}/scripts/pipeline_metrics.py" "${SCRIPTS_DIR}/pipeline_metrics.py"
download_file "${RAW_BASE}/skills/sovereign-swarm/skill.yaml" "${SKILLS_DIR}/sovereign-swarm/skill.yaml"
download_file "${RAW_BASE}/templates/SOUL.md" "${HERMES_HOME}/SOUL.md"
download_file "${RAW_BASE}/templates/AGENTS.md" "${HERMES_HOME}/AGENTS.md"

chmod +x "${SCRIPTS_DIR}/pre_process.py" "${SCRIPTS_DIR}/pipeline_metrics.py"
ok "Pipeline files installed"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Install Profiles
# ══════════════════════════════════════════════════════════════════════════════
info "Installing profiles..."

for profile in pro-se solar systems stochastic interpersonal offline local-fast local-heavy cloud-brain psychologist-child orchestrator; do
    mkdir -p "${PROFILES_DIR}/${profile}/skills/sovereign-swarm"
    mkdir -p "${PROFILES_DIR}/${profile}/cron"
    mkdir -p "${PROFILES_DIR}/${profile}/plugins"
    mkdir -p "${PROFILES_DIR}/${profile}/memories"
    cp "${SKILLS_DIR}/sovereign-swarm/skill.yaml" "${PROFILES_DIR}/${profile}/skills/sovereign-swarm/skill.yaml"
done
ok "Profiles created: pro-se, solar, systems, stochastic, interpersonal, offline, local-fast, local-heavy, cloud-brain, psychologist-child, orchestrator"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Install Ollama Models
# ══════════════════════════════════════════════════════════════════════════════
info "Checking Ollama models..."

LOCAL_MODELS=("gemma4:12b" "qwen3:0.6b")
for model in "${LOCAL_MODELS[@]}"; do
    if ollama list 2>/dev/null | grep -q "$model"; then
        ok "  $model already installed"
    else
        info "  Pulling $model (background)..."
        ollama pull "$model" &
    fi
done
wait 2>/dev/null || true
ok "Local models installed"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Run Configuration (if --configure flag)
# ══════════════════════════════════════════════════════════════════════════════
if $RUN_CONFIGURE; then
    info "Running interactive configuration..."
    if [[ -f "${SCRIPTS_DIR}/configure.sh" ]]; then
        bash "${SCRIPTS_DIR}/configure.sh"
    else
        # Download and run configure script
        TMP_CONFIGURE=$(mktemp)
        curl -fsSL "${RAW_BASE}/scripts/configure.sh" -o "$TMP_CONFIGURE"
        bash "$TMP_CONFIGURE"
        rm -f "$TMP_CONFIGURE"
    fi
else
    # Write default config.yaml
    info "Writing default config.yaml..."
    TMP_CONFIG=$(mktemp)
    curl -fsSL "${RAW_BASE}/templates/config.yaml" -o "$TMP_CONFIG"
    cp "$TMP_CONFIG" "${HERMES_HOME}/config.yaml"
    rm -f "$TMP_CONFIG"
    ok "Default config.yaml written"
    warn "Run with --configure to set up API keys and personalization:"
    warn "  curl -fsSL ${RAW_BASE}/install.sh | bash -s -- --configure"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: Verify Installation
# ══════════════════════════════════════════════════════════════════════════════
info "Verifying installation..."

ERRORS=0
for f in "${HERMES_HOME}/config.yaml" \
         "${HERMES_HOME}/SOUL.md" \
         "${HERMES_HOME}/AGENTS.md" \
         "${SCRIPTS_DIR}/pre_process.py" \
         "${SCRIPTS_DIR}/pipeline_metrics.py" \
         "${SKILLS_DIR}/sovereign-swarm/skill.yaml"; do
    if [[ -f "$f" ]]; then
        ok "  $(basename "$f")"
    else
        fail "  MISSING: $f"
        ERRORS=$((ERRORS+1))
    fi
done

# Test pipeline
if echo "What is the capital of France?" | python3 "${SCRIPTS_DIR}/pre_process.py" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['evaluator_answered']==True" 2>/dev/null; then
    ok "  Pipeline test passed"
else
    warn "  Pipeline test failed — check Ollama is running"
    ERRORS=$((ERRORS+1))
fi

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
echo -e "\n${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Installation Complete${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${GREEN}Hermes:${NC}     $(hermes --version 2>&1)"
echo -e "  ${GREEN}Pipeline:${NC}   ${SCRIPTS_DIR}/pre_process.py"
echo -e "  ${GREEN}Metrics:${NC}    ${SCRIPTS_DIR}/pipeline_metrics.py"
echo -e "  ${GREEN}Profiles:${NC}   $(ls ${PROFILES_DIR} | tr '\n' ' ')"
echo -e "  ${GREEN}Logs:${NC}       ${LOGS_DIR}/pipeline.log"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  1. Start Hermes:  hermes"
echo -e "  2. View metrics:  python3 ${SCRIPTS_DIR}/pipeline_metrics.py"
echo -e "  3. Configure:     curl -fsSL ${RAW_BASE}/install.sh | bash -s -- --configure"
echo ""

if [[ $ERRORS -gt 0 ]]; then
    echo -e "  ${RED}${ERRORS} warnings/errors — review above.${NC}"
else
    echo -e "  ${GREEN}All checks passed. Ready to go.${NC}"
fi
echo ""
