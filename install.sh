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
SKIP_PROMPT=false
for arg in "$@"; do
    if [[ "$arg" == "--configure" || "$arg" == "-c" ]]; then
        RUN_CONFIGURE=true
        SKIP_PROMPT=true
    fi
    if [[ "$arg" == "--default" || "$arg" == "-d" ]]; then
        RUN_CONFIGURE=false
        SKIP_PROMPT=true
    fi
done

# ── If no flag, ask at launch ──
if ! $SKIP_PROMPT; then
    echo ""
    echo -e "${CYAN}How would you like to configure?${NC}"
    echo ""
    echo "  1) Default setup — quick install with standard domains"
    echo "     (legal, finance, systems, solar, stochastic, interpersonal,"
    echo "      health, career, education)"
    echo ""
    echo "  2) Custom setup — choose your domains, keywords, models, and more"
    echo ""
    read -p "  Enter 1 or 2 [1]: " choice
    choice="${choice:-1}"
    if [[ "$choice" == "2" ]]; then
        RUN_CONFIGURE=true
    fi
    echo ""
fi

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
fi
ok "Ollama: $(ollama --version 2>&1)"

# ── Ensure Ollama server is running ──
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    info "Starting Ollama server..."
    ollama serve &>/dev/null &
    sleep 3
    # Verify it started
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        ok "  Ollama server started"
    else
        warn "  Could not start Ollama server — run 'ollama serve' manually"
    fi
else
    ok "  Ollama server already running"
fi

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
download_file "${RAW_BASE}/scripts/generate_config.py" "${SCRIPTS_DIR}/generate_config.py"
download_file "${RAW_BASE}/skills/sovereign-swarm/skill.yaml" "${SKILLS_DIR}/sovereign-swarm/skill.yaml"

if $RUN_CONFIGURE; then
    # Download templates for config generation
    download_file "${RAW_BASE}/templates/pre_process.py.j2" "${SCRIPTS_DIR}/../templates/pre_process.py.j2"
    download_file "${RAW_BASE}/templates/SOUL.md.j2" "${SCRIPTS_DIR}/../templates/SOUL.md.j2"
    download_file "${RAW_BASE}/templates/AGENTS.md.j2" "${SCRIPTS_DIR}/../templates/AGENTS.md.j2"
    download_file "${RAW_BASE}/templates/skill.yaml.j2" "${SCRIPTS_DIR}/../templates/skill.yaml.j2"
    download_file "${RAW_BASE}/scripts/configure.sh" "${SCRIPTS_DIR}/configure.sh"
    chmod +x "${SCRIPTS_DIR}/configure.sh" "${SCRIPTS_DIR}/generate_config.py"
else
    # Download static defaults
    download_file "${RAW_BASE}/templates/SOUL.md" "${HERMES_HOME}/SOUL.md"
    download_file "${RAW_BASE}/templates/AGENTS.md" "${HERMES_HOME}/AGENTS.md"
fi

chmod +x "${SCRIPTS_DIR}/pre_process.py" "${SCRIPTS_DIR}/pipeline_metrics.py"
ok "Pipeline files installed"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Install Profiles
# ══════════════════════════════════════════════════════════════════════════════
info "Installing profiles..."

# Default profiles match the 9 default domains
for profile in legal finance systems solar stochastic interpersonal health career education orchestrator; do
    mkdir -p "${PROFILES_DIR}/${profile}/skills/sovereign-swarm"
    mkdir -p "${PROFILES_DIR}/${profile}/cron"
    mkdir -p "${PROFILES_DIR}/${profile}/plugins"
    mkdir -p "${PROFILES_DIR}/${profile}/memories"
    cp "${SKILLS_DIR}/sovereign-swarm/skill.yaml" "${PROFILES_DIR}/${profile}/skills/sovereign-swarm/skill.yaml"
done
ok "Profiles created: legal, finance, systems, solar, stochastic, interpersonal, health, career, education, orchestrator"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4b: Install Knowledge Base
# ══════════════════════════════════════════════════════════════════════════════
info "Installing Knowledge Base..."

# Download knowledge scripts
download_file "${RAW_BASE}/scripts/knowledge_search.py" "${SCRIPTS_DIR}/knowledge_search.py"
download_file "${RAW_BASE}/scripts/knowledge_distill.py" "${SCRIPTS_DIR}/knowledge_distill.py"
download_file "${RAW_BASE}/scripts/knowledge_embed_qwen.py" "${SCRIPTS_DIR}/knowledge_embed_qwen.py"
download_file "${RAW_BASE}/scripts/index_additional_sources.py" "${SCRIPTS_DIR}/index_additional_sources.py"
download_file "${RAW_BASE}/scripts/graphrag_query.py" "${SCRIPTS_DIR}/graphrag_query.py"
chmod +x "${SCRIPTS_DIR}/knowledge_search.py" "${SCRIPTS_DIR}/knowledge_distill.py" "${SCRIPTS_DIR}/knowledge_embed_qwen.py"

# Download knowledge skill
download_file "${RAW_BASE}/skills/knowledge-base-retrieval/SKILL.md" "${SKILLS_DIR}/knowledge-base-retrieval/SKILL.md"

# Create empty knowledge.db if it doesn't exist
if [[ ! -f "${HERMES_HOME}/knowledge.db" ]]; then
    python3 -c "
import sqlite3
conn = sqlite3.connect('${HERMES_HOME}/knowledge.db')
conn.executescript('''
    CREATE TABLE IF NOT EXISTS knowledge_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        source TEXT,
        domain TEXT DEFAULT 'general',
        full_text TEXT,
        tags TEXT,
        file_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER REFERENCES knowledge_documents(id),
        chunk_index INTEGER,
        contextual_text TEXT NOT NULL,
        embedding BLOB,
        question TEXT,
        summary TEXT,
        resolution TEXT,
        code_refs TEXT,
        domain TEXT DEFAULT 'general',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
        contextual_text, question, summary, resolution,
        content='knowledge_chunks', content_rowid='id'
    );
    CREATE TABLE IF NOT EXISTS knowledge_sync (
        file_path TEXT PRIMARY KEY,
        file_hash TEXT NOT NULL,
        last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
')
conn.close()
" 2>/dev/null && ok "  knowledge.db created" || warn "  Could not create knowledge.db"
fi

ok "Knowledge Base installed"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4d: Install GraphRAG
# ══════════════════════════════════════════════════════════════════════════════
info "Installing GraphRAG..."

GRAPH_DIR="${HERMES_HOME}/graphrag"
if [[ ! -d "$GRAPH_DIR" ]]; then
    mkdir -p "$GRAPH_DIR/input" "$GRAPH_DIR/output" "$GRAPH_DIR/cache" "$GRAPH_DIR/logs"
    mkdir -p "$GRAPH_DIR/prompts"

    # Create GraphRAG venv
    python3 -m venv "${HERMES_HOME}/venvs/graphrag"
    source "${HERMES_HOME}/venvs/graphrag/bin/activate"
    pip install -q graphrag 2>/dev/null
    deactivate

    # Download settings.yaml template
    download_file "${RAW_BASE}/templates/graphrag_settings.yaml" "${GRAPH_DIR}/settings.yaml"

    # Download graphrag skill
    download_file "${RAW_BASE}/skills/graphrag-ollama-index/SKILL.md" "${SKILLS_DIR}/graphrag-ollama-index/SKILL.md"

    # Apply litellm patches for gemma4 JSON code-block wrapping
    GRAPHRAG_LITELLM=$(find "${HERMES_HOME}/venvs/graphrag" -path "*/graphrag_llm/completion/lite_llm_completion.py" 2>/dev/null | head -1)
    GRAPHRAG_STRUCTURE=$(find "${HERMES_HOME}/venvs/graphrag" -path "*/graphrag_llm/utils/structure_response.py" 2>/dev/null | head -1)

    if [[ -n "$GRAPHRAG_LITELLM" ]]; then
        sed -i '' 's/litellm.enable_json_schema_validation = True/litellm.enable_json_schema_validation = False/' "$GRAPHRAG_LITELLM"
        ok "  Patched litellm JSON validation"
    fi

    if [[ -n "$GRAPHRAG_STRUCTURE" ]]; then
        # Add import re if not present
        if ! grep -q "^import re" "$GRAPHRAG_STRUCTURE"; then
            sed -i '' '1s/^/import re\n/' "$GRAPHRAG_STRUCTURE"
        fi
        # Add code-block stripping before json.loads
        python3 -c "
import re
with open('$GRAPHRAG_STRUCTURE', 'r') as f:
    content = f.read()
# Add code-block stripping before json.loads
old = 'parsed_dict: dict[str, Any] = json.loads(response)'
new = '''    cleaned = response.strip()
    if cleaned.startswith(\"```\"):
        cleaned = re.sub(r\"^```(?:json)?\\\\s*\", \"\", cleaned)
        cleaned = re.sub(r\"\\\\s*```$\", \"\", cleaned)
        cleaned = cleaned.strip()
    parsed_dict: dict[str, Any] = json.loads(cleaned)'''
content = content.replace(old, new)
with open('$GRAPHRAG_STRUCTURE', 'w') as f:
    f.write(content)
" 2>/dev/null
        ok "  Patched structure_response for code-block stripping"
    fi

    ok "GraphRAG installed"
else
    ok "  GraphRAG already exists at $GRAPH_DIR"
    # Still download the skill
    download_file "${RAW_BASE}/skills/graphrag-ollama-index/SKILL.md" "${SKILLS_DIR}/graphrag-ollama-index/SKILL.md"
fi

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
         "${SCRIPTS_DIR}/knowledge_search.py" \
         "${SCRIPTS_DIR}/knowledge_distill.py" \
         "${SCRIPTS_DIR}/knowledge_embed_qwen.py" \
         "${SCRIPTS_DIR}/graphrag_query.py" \
         "${SKILLS_DIR}/sovereign-swarm/skill.yaml" \
         "${SKILLS_DIR}/knowledge-base-retrieval/SKILL.md" \
         "${SKILLS_DIR}/graphrag-ollama-index/SKILL.md"; do
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
echo -e "  ${GREEN}Knowledge:${NC}  ${SCRIPTS_DIR}/knowledge_search.py"
echo -e "  ${GREEN}GraphRAG:${NC}   ${GRAPH_DIR}"
echo -e "  ${GREEN}Profiles:${NC}   $(ls ${PROFILES_DIR} | tr '\n' ' ')"
echo -e "  ${GREEN}Logs:${NC}       ${LOGS_DIR}/pipeline.log"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  1. Start Hermes:  hermes"
echo -e "  2. View metrics:  python3 ${SCRIPTS_DIR}/pipeline_metrics.py"
echo -e "  3. Search knowledge:  python3 ${SCRIPTS_DIR}/knowledge_search.py"
echo -e "  4. Index vault:    python3 ${SCRIPTS_DIR}/knowledge_distill.py"
echo -e "  5. Index GraphRAG: cd ${GRAPH_DIR} && graphrag index --root ."
echo -e "  6. Configure:     curl -fsSL ${RAW_BASE}/install.sh | bash -s -- --configure"
echo ""

if [[ $ERRORS -gt 0 ]]; then
    echo -e "  ${RED}${ERRORS} warnings/errors — review above.${NC}"
else
    echo -e "  ${GREEN}All checks passed. Ready to go.${NC}"
fi
echo ""
