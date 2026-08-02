#!/usr/bin/env python3
"""
Pre-processor — Combined Intent Gate + Distill + Evaluator Gate.
Runs on EVERY message automatically via skill.yaml pre_process hook.
Reads ONLY the current message — NO conversation history.

Three tiers:
1. Intent Gate: classify domain via keywords (zero model calls)
2. Distill: strip filler via gpt-oss:20b-cloud (cheap model)
3. Evaluator Gate: can the cheap model answer this? If yes, skip heavy model.

Resilience features (Aug 2, 2026):
- Health check: fast-fail if Ollama is down
- Fallback chain: cloud → local 12B → tiny local → original text
- Circuit breaker: 3 strikes, 5-min cooldown
- Logging: every decision with timestamps and latency
- Metrics: evaluator hit rate, savings, latency, domain distribution
- Caching: LRU cache for repeated queries
- Input/output validation
- Hard timeout: 15-second kill switch

Output: domain tag + distilled text + evaluator decision as JSON.
"""
import json
import sys
import time
import urllib.request
import logging
import os
import socket
import signal
from collections import OrderedDict
from datetime import datetime

# ── Constants ──

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
MODEL = "gemma4:31b-cloud"

LOG_DIR = os.path.expanduser("~/.hermes/logs")
STATE_DIR = os.path.expanduser("~/.hermes/state")
CIRCUIT_BREAKER_FILE = os.path.join(STATE_DIR, "pipeline_circuit.json")
METRICS_FILE = os.path.join(STATE_DIR, "pipeline_metrics.json")

CIRCUIT_BREAKER_THRESHOLD = 3   # Consecutive failures before open
CIRCUIT_BREAKER_RESET = 300     # Seconds before trying again (5 min)
HARD_TIMEOUT = 15               # Max seconds for entire pipeline
HEALTH_CHECK_TIMEOUT = 3        # Seconds for health check
API_TIMEOUT = 30                # Seconds for API calls
CACHE_MAXSIZE = 100             # LRU cache entries

# ── Fallback Chains ──

FALLBACK_CHAIN_DISTILL = [
    "gemma4:31b-cloud",    # Level 2 cloud (faster, better quality)
    "gpt-oss:20b-cloud",   # Level 1 cloud (cheaper fallback)
    "gemma4:12b",          # Local 12B (7.6GB, always available)
    "qwen3:0.6b",          # Tiny local (522MB, last resort)
]

FALLBACK_CHAIN_EVALUATOR = [
    "gemma4:31b-cloud",    # Level 2 cloud
    "gpt-oss:20b-cloud",   # Level 1 cloud fallback
    "gemma4:12b",          # Local fallback
]

# ── Intent Gate Keywords ──

INTENT_KEYWORDS = {
    "legal": [
        "court", "custody", "filing", "motion", "judge", "subpoena",
        "contempt", "trial", "guardian ad litem", "evidence", "hearing",
        "plaintiff", "defendant", "petition", "order", "decree",
        "attorney", "lawyer", "legal", "statute", "orc ", "rule ",
        "f25", "juvenile", "parenting", "visitation", "parental",
        "guardian", "docket", "brief", "objection", "appeal",
        "affidavit", "complaint", "summons", "discovery", "deposition",
    ],
    "finance": [
        "money", "cost", "fee", "bill", "income", "expense", "budget",
        "payment", "receipt", "invoice", "debt", "credit", "pay",
        "bank", "account", "$", "dollar", "paypal", "venmo",
        "indigent", "fee waiver", "financial",
    ],
    "systems": [
        "computer", "config", "cron", "gateway", "hermes", "mlx",
        "hardware", "script", "ollama", "tui", "dashboard", "profile",
        "process", "install", "update", "upgrade", "deploy",
        "server", "ssh", "terminal", "python", "git", "repo",
        "mac", "linux", "disk", "memory", "cpu", "gpu",
        "token", "model", "api", "provider",
    ],
    "solar": [
        "battery", "voltage", "panel", "chargepro", "inverter",
        "power", "energy", "charge", "solar", "lifepo4", "ah ",
        "watt", "volt", "amp", "ble", "controller",
    ],
    "stochastic": [
        "casino", "slot", "vlt", "gambling", "probability", "odds",
        "kalshi", "trade", "bet", "ev ", "expected value", "advantage",
        "stochastic", "market", "mlb", "nfl", "nba",
    ],
    "interpersonal": [
        "psychology", "relationship", "family", "communication",
        "attachment", "therapy", "counseling", "emotion",
        "borderline", "narcissist", "alienation",
    ],
}

# ── Distill System Prompt ──

DISTILL_SYSTEM = """Rewrite the user's message to be shorter and clearer.

Rules:
1. Remove filler words: "I think", "maybe", "sort of", "you know", "like", "kind of"
2. Use active voice. "Check the battery." NOT "The battery should be checked."
3. Short sentences. Max 20 words each. One idea per sentence.
4. Keep the meaning and intent. Do not add information.
5. Use simple words. No idioms or metaphors.

Examples:
Input: "I think maybe we should check the battery voltage because it seems like it might be getting low"
Output: Check the battery voltage. The voltage may be low.

Input: "I was wondering if you could help me draft a motion for contempt because the other party hasn't been following the order"
Output: Draft a motion for contempt. The other party did not follow the court order.

Input: "So like I was thinking we could try to install the new model and see if it works better"
Output: Install the new model. Test its performance.

Output only the rewritten version. No explanations."""

# ── Evaluator System Prompt ──

EVALUATOR_SYSTEM = """You are a triage evaluator. Your job is to decide if YOU can answer the user's question right now, without any tools, without any research, and without any data from their system.

Answer YES only if ALL of these are true:
1. The answer is a simple fact you know for certain (definitions, common knowledge, simple math)
2. The answer does NOT require: live data, tool access, file reads, API calls, or system-specific knowledge
3. The answer does NOT require: legal research, case citations, statute lookups, or domain expertise
4. You are 100% confident in the answer

Answer NO if ANY of these are true:
1. The question needs live data (battery voltage, account balance, weather, time, etc.)
2. The question needs a tool (read a file, run a command, search the web, check a database)
3. The question needs legal research (case law, statutes, court rules, filing procedures)
4. The question needs system-specific knowledge (how this particular setup works, what's installed, config details)
5. The question is about the user's specific situation (their case, their battery, their config)
6. You're not 100% sure

Examples of YES:
- "What is the capital of France?" → YES, Paris
- "What is 15% of 200?" → YES, 30
- "What is the boiling point of water?" → YES, 100°C
- "What does CPU stand for?" → YES, Central Processing Unit

Examples of NO:
- "What's the battery voltage?" → NO, needs live data
- "Draft a motion for contempt" → NO, needs legal research
- "How do I restart Hermes?" → NO, needs system-specific knowledge
- "What's my Kalshi balance?" → NO, needs API call
- "Research Ohio defective service law" → NO, needs legal research
- "What's the standard for changing custody in Ohio?" → NO, needs legal research

Output format for YES:
YES
<your complete answer>

Output format for NO:
NO"""

# ── Logging Setup ──

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s|%(levelname)s|%(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'pipeline.log')),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger('pipeline')

# ── LRU Cache ──

class LRUCache:
    """Simple LRU cache with max size."""
    def __init__(self, maxsize=CACHE_MAXSIZE):
        self.cache = OrderedDict()
        self.maxsize = maxsize

    def get(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)

    def clear(self):
        self.cache.clear()

# Module-level caches
_distill_cache = LRUCache()
_evaluator_cache = LRUCache()

# ── Health Check ──

def health_check(timeout=HEALTH_CHECK_TIMEOUT):
    """Check if Ollama is running. Returns True/False. Fast fail."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex(('127.0.0.1', 11434))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def model_available(model_name, timeout=5):
    """Check if a model exists in Ollama. Returns True/False."""
    try:
        req = urllib.request.Request(OLLAMA_TAGS_URL)
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read())
        models = [m['name'] for m in data.get('models', [])]
        return model_name in models
    except Exception:
        return False

# ── Circuit Breaker ──

def _load_circuit_state():
    """Load circuit breaker state from disk."""
    try:
        with open(CIRCUIT_BREAKER_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"failures": 0, "last_failure": 0, "open": False}


def _save_circuit_state(state):
    """Save circuit breaker state to disk."""
    with open(CIRCUIT_BREAKER_FILE, 'w') as f:
        json.dump(state, f)


def circuit_allows():
    """Check if circuit breaker allows API calls. Returns True/False."""
    state = _load_circuit_state()
    if not state.get("open"):
        return True
    # Check if enough time has passed to try again
    elapsed = time.time() - state.get("last_failure", 0)
    if elapsed > CIRCUIT_BREAKER_RESET:
        state["open"] = False
        state["failures"] = 0
        _save_circuit_state(state)
        logger.info("CIRCUIT|closed (reset after cooldown)")
        return True
    remaining = int(CIRCUIT_BREAKER_RESET - elapsed)
    logger.warning(f"CIRCUIT|open (cooldown: {remaining}s remaining)")
    return False


def record_success():
    """Record a successful API call — reset circuit breaker."""
    state = _load_circuit_state()
    state["failures"] = 0
    state["open"] = False
    _save_circuit_state(state)


def record_failure():
    """Record a failed API call — may open circuit breaker."""
    state = _load_circuit_state()
    state["failures"] = state.get("failures", 0) + 1
    state["last_failure"] = time.time()
    if state["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
        state["open"] = True
        logger.warning(f"CIRCUIT|opened after {state['failures']} consecutive failures")
        record_metric("circuit_open_count")
    _save_circuit_state(state)

# ── Metrics ──

def _load_metrics():
    """Load metrics from disk."""
    try:
        with open(METRICS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "total_queries": 0,
            "by_domain": {},
            "by_mode": {},
            "by_intensity": {},
            "distill_success": 0,
            "distill_failure": 0,
            "distill_fallback_used": 0,
            "evaluator_answered": 0,
            "evaluator_passed": 0,
            "evaluator_fallback_used": 0,
            "latency_ms": [],
            "circuit_open_count": 0,
            "health_check_failures": 0,
            "cache_hits": 0,
            "input_validation_failures": 0,
        }


def _save_metrics(metrics):
    """Save metrics to disk."""
    with open(METRICS_FILE, 'w') as f:
        json.dump(metrics, f, indent=2)


def record_metric(key, value=None):
    """Record a metric. If value is None, increment counter. Otherwise append to list."""
    try:
        metrics = _load_metrics()
        if value is None:
            metrics[key] = metrics.get(key, 0) + 1
        elif isinstance(value, (int, float)):
            # For list metrics (latency), keep last 1000
            lst = metrics.get(key, [])
            lst.append(value)
            metrics[key] = lst[-1000:]
        _save_metrics(metrics)
    except Exception:
        pass  # Don't let metrics failure crash the pipeline

# ── Input/Output Validation ──

def validate_input(text):
    """Validate input before processing. Returns (is_valid, error_msg)."""
    if not text or not text.strip():
        return False, "Empty input"
    if len(text) > 10000:
        return False, "Input too long (>10K chars)"
    # Check for binary content in first 1000 chars
    if any(ord(c) < 32 and c not in '\n\r\t' for c in text[:1000]):
        return False, "Binary content detected"
    return True, None


def validate_output(result):
    """Validate the output dict has all required fields."""
    required = ["domain", "distilled", "original", "mode", "intensity",
                 "evaluator_answered", "evaluator_answer"]
    for field in required:
        if field not in result:
            return False, f"Missing field: {field}"
    valid_domains = ["legal", "finance", "systems", "solar",
                     "stochastic", "interpersonal", "general"]
    if result["domain"] not in valid_domains:
        return False, f"Invalid domain: {result['domain']}"
    return True, None

# ── Intent Gate ──

def classify_domain(text):
    """Keyword-based intent classification. No model call, zero latency.
    Uses word-boundary matching to prevent false positives like 'api' in 'capital'."""
    text_lower = text.lower()
    scores = {}
    for domain, keywords in INTENT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            # Use word-boundary matching: keyword must appear as a whole word
            # or at a word boundary (space, start/end of string, punctuation)
            kw_lower = kw.lower()
            if kw_lower in text_lower:
                # Check it's a word boundary match, not substring
                idx = text_lower.find(kw_lower)
                while idx != -1:
                    # Check char before keyword
                    before_ok = (idx == 0 or not text_lower[idx - 1].isalnum())
                    # Check char after keyword
                    after_idx = idx + len(kw_lower)
                    after_ok = (after_idx >= len(text_lower) or not text_lower[after_idx].isalnum())
                    if before_ok and after_ok:
                        score += 1
                        break  # Count this keyword once
                    idx = text_lower.find(kw_lower, idx + 1)
        if score > 0:
            scores[domain] = score
    if not scores:
        return "general"
    return max(scores, key=scores.get)

# ── API Call ──

def call_model(model, messages, max_tokens=512, temperature=0):
    """Call Ollama model with retry on transient errors and circuit breaker."""
    if not circuit_allows():
        return None

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature}
    }
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}

    max_retries = 3
    for attempt in range(max_retries):
        req = urllib.request.Request(OLLAMA_URL, data=data, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=API_TIMEOUT)
            result = json.loads(resp.read())
            content = result.get("message", {}).get("content", "").strip()
            if content:
                record_success()
                return content
            # Empty response — treat as failure
            if attempt == max_retries - 1:
                record_failure()
                return None
            time.sleep(2 ** attempt)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            if attempt == max_retries - 1:
                record_failure()
                return None
            time.sleep(2 ** attempt)
        except Exception as e:
            if attempt == max_retries - 1:
                record_failure()
                return None
            time.sleep(2 ** attempt)
    return None

# ── Fallback Wrappers ──

def call_model_with_fallback(text, system_prompt, fallback_chain, max_tokens=512, temperature=0):
    """Try each model in the fallback chain until one succeeds."""
    for model in fallback_chain:
        if not model_available(model):
            logger.info(f"FALLBACK|{model} not available, skipping")
            continue
        logger.info(f"FALLBACK|trying {model}")
        result = call_model(model, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ], max_tokens=max_tokens, temperature=temperature)
        if result:
            if model != fallback_chain[0]:
                logger.info(f"FALLBACK|used {model} (primary failed)")
            return result
        logger.warning(f"FALLBACK|{model} returned no result")
    return None

# ── Distill ──

def distill_text(text, mode, ollama_healthy):
    """Distill input text. Returns (distilled_text, used_fallback)."""
    if mode == "minimal":
        return text, False

    # Check cache first
    cache_key = f"distill:{hash(text)}"
    cached = _distill_cache.get(cache_key)
    if cached is not None:
        logger.info("DISTILL|cache hit")
        record_metric("cache_hits")
        return cached, False

    if not ollama_healthy:
        logger.warning("DISTILL|skipped (Ollama unhealthy)")
        return text, False

    result = call_model_with_fallback(text, DISTILL_SYSTEM, FALLBACK_CHAIN_DISTILL)
    if result:
        _distill_cache.set(cache_key, result)
        record_metric("distill_success")
        if result != text:
            logger.info(f"DISTILL|reduced {len(text)} → {len(result)} chars")
        return result, False

    logger.warning("DISTILL|all fallbacks failed, using original text")
    record_metric("distill_failure")
    return text, False

# ── Evaluator ──

def evaluate_with_fallback(text, domain, ollama_healthy):
    """Try evaluator with fallback chain. Returns (can_answer, answer)."""
    if not ollama_healthy:
        logger.warning("EVALUATOR|skipped (Ollama unhealthy)")
        return False, None

    # Check cache first
    cache_key = f"evaluator:{hash(text)}"
    cached = _evaluator_cache.get(cache_key)
    if cached is not None:
        logger.info("EVALUATOR|cache hit")
        record_metric("cache_hits")
        return cached

    for model in FALLBACK_CHAIN_EVALUATOR:
        if not model_available(model):
            continue
        result = call_model(model, [
            {"role": "system", "content": EVALUATOR_SYSTEM},
            {"role": "user", "content": f"[Domain: {domain}] {text}"}
        ], max_tokens=1024, temperature=0)
        if not result:
            continue
        if model != FALLBACK_CHAIN_EVALUATOR[0]:
            record_metric("evaluator_fallback_used")
            logger.info(f"EVALUATOR|fallback used {model}")

        if result.startswith("NO"):
            _evaluator_cache.set(cache_key, (False, None))
            record_metric("evaluator_passed")
            return False, None
        if result.startswith("YES"):
            answer = result[3:].strip()
            _evaluator_cache.set(cache_key, (True, answer))
            record_metric("evaluator_answered")
            logger.info(f"EVALUATOR|answered ({len(answer)} chars)")
            return True, answer

    # Model didn't follow format — assume can't answer
    _evaluator_cache.set(cache_key, (False, None))
    record_metric("evaluator_passed")
    return False, None

# ── Main Processing ──

def process(text):
    """Run the full pipeline: validate → classify → distill → evaluate."""
    start_time = time.time()
    record_metric("total_queries")

    # ── Input Validation ──
    is_valid, error = validate_input(text)
    if not is_valid:
        logger.warning(f"VALIDATION|input rejected: {error}")
        record_metric("input_validation_failures")
        return {
            "domain": "general",
            "distilled": text or "",
            "original": text or "",
            "mode": "minimal",
            "intensity": "MINIMAL",
            "evaluator_answered": False,
            "evaluator_answer": None,
            "error": error
        }

    logger.info(f"INPUT|{len(text)} chars")

    # ── Mode Detection ──
    brevity_keywords = ["quick:", "briefly:", "short:", "tl;dr", "one word", "yes/no"]
    is_brevity = False
    text_lower_for_mode = text.lower()
    for kw in brevity_keywords:
        if kw in text_lower_for_mode:
            # Word-boundary check
            idx = text_lower_for_mode.find(kw)
            while idx != -1:
                before_ok = (idx == 0 or not text_lower_for_mode[idx - 1].isalnum())
                after_idx = idx + len(kw)
                after_ok = (after_idx >= len(text_lower_for_mode) or not text_lower_for_mode[after_idx].isalnum())
                if before_ok and after_ok:
                    is_brevity = True
                    break
                idx = text_lower_for_mode.find(kw, idx + 1)
            if is_brevity:
                break
    is_short = len(text.strip()) < 30
    mode = "minimal" if (is_brevity or is_short) else "standard"
    logger.info(f"MODE|{mode}")

    # ── Intensity Detection ──
    full_keywords = ["research", "analyze", "draft", "motion", "brief", "deep dive", "comprehensive"]
    is_full = any(kw in text.lower() for kw in full_keywords)

    if mode == "minimal":
        intensity = "MINIMAL"
    elif is_full:
        intensity = "FULL"
    else:
        intensity = "STANDARD"
    logger.info(f"INTENSITY|{intensity}")

    record_metric(f"by_mode.{mode}")
    record_metric(f"by_intensity.{intensity}")

    # ── Health Check ──
    ollama_healthy = health_check()
    if not ollama_healthy:
        logger.warning("HEALTH|Ollama not reachable, running in degraded mode")
        record_metric("health_check_failures")
    else:
        logger.info("HEALTH|Ollama reachable")

    # ── Step 1: Classify Domain ──
    domain = classify_domain(text)
    logger.info(f"DOMAIN|{domain}")
    record_metric(f"by_domain.{domain}")

    # ── Step 2: Distill ──
    distill_start = time.time()
    distilled, _ = distill_text(text, mode, ollama_healthy)
    distill_time = (time.time() - distill_start) * 1000
    logger.info(f"DISTILL|{len(distilled)} chars in {distill_time:.0f}ms")

    # ── Step 3: Evaluator Gate ──
    evaluator_answered = False
    evaluator_answer = None

    if intensity != "FULL" and ollama_healthy:
        eval_start = time.time()
        can_answer, answer = evaluate_with_fallback(distilled, domain, ollama_healthy)
        eval_time = (time.time() - eval_start) * 1000
        if can_answer:
            evaluator_answered = True
            evaluator_answer = answer
            logger.info(f"EVALUATOR|answered in {eval_time:.0f}ms")
        else:
            logger.info(f"EVALUATOR|passed to heavy model in {eval_time:.0f}ms")
    elif intensity == "FULL":
        logger.info("EVALUATOR|skipped (FULL intensity)")
    elif not ollama_healthy:
        logger.info("EVALUATOR|skipped (Ollama unhealthy)")

    # ── Build Result ──
    result = {
        "domain": domain,
        "distilled": distilled,
        "original": text,
        "mode": mode,
        "intensity": intensity,
        "evaluator_answered": evaluator_answered,
        "evaluator_answer": evaluator_answer
    }

    # ── Output Validation ──
    is_valid, error = validate_output(result)
    if not is_valid:
        logger.error(f"VALIDATION|output rejected: {error}")
        # Return safe fallback
        result = {
            "domain": "general",
            "distilled": text,
            "original": text,
            "mode": "standard",
            "intensity": "STANDARD",
            "evaluator_answered": False,
            "evaluator_answer": None
        }

    # ── Record Latency ──
    total_time = (time.time() - start_time) * 1000
    record_metric("latency_ms", total_time)
    logger.info(f"RESULT|domain={domain}|mode={mode}|intensity={intensity}|"
                f"evaluator_answered={evaluator_answered}|latency={total_time:.0f}ms")

    return result


# ── Timeout Wrapper ──

class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutError("Pipeline script timed out")


def run_with_timeout(func, args, timeout=HARD_TIMEOUT):
    """Run a function with a hard timeout. Returns result or raises."""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)
    try:
        result = func(*args)
        signal.alarm(0)
        return result
    except TimeoutError:
        logger.error(f"TIMEOUT|Pipeline exceeded {timeout}s")
        signal.alarm(0)
        raise


# ── Entry Point ──

if __name__ == "__main__":
    input_text = sys.stdin.read()
    try:
        result = run_with_timeout(process, (input_text,), timeout=HARD_TIMEOUT)
    except TimeoutError:
        result = {
            "domain": "general",
            "distilled": input_text,
            "original": input_text,
            "mode": "standard",
            "intensity": "STANDARD",
            "evaluator_answered": False,
            "evaluator_answer": None,
            "error": "timeout"
        }
    except Exception as e:
        logger.error(f"UNHANDLED|{e}")
        result = {
            "domain": "general",
            "distilled": input_text,
            "original": input_text,
            "mode": "standard",
            "intensity": "STANDARD",
            "evaluator_answered": False,
            "evaluator_answer": None,
            "error": str(e)
        }
    print(json.dumps(result))
