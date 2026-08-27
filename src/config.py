import os
import re
from pathlib import Path
import yaml
from dotenv import load_dotenv

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
STATE_FILE = ROOT / "state.json"

def _get_keys(prefix):
    keys = []
    for k, v in os.environ.items():
        if k.startswith(prefix) and v.strip():
            keys.extend([x.strip().strip('"').strip("'") for x in re.split(r',|\n|\\n', v) if x.strip()])
    return keys

_pexels_keys = _get_keys("PEXELS_API_KEY")
PEXELS_API_KEYS = _pexels_keys if _pexels_keys else ["dummy_key"]
import random
random.shuffle(PEXELS_API_KEYS)

# 9Router AWS Configuration (Primary Gateway)
NINEROUTER_API_KEYS = _get_keys("NINEROUTER_API_KEY") or _get_keys("NINEROUTER_KEY") or _get_keys("OMNIROUTE_API_KEY")
if not NINEROUTER_API_KEYS:
    NINEROUTER_API_KEYS = ["sk-1f7d1788ce9c1aa7-gixqcc-64a9e8fd"]

NINEROUTER_URL = os.environ.get("NINEROUTER_URL", "http://13.214.33.122:20128").rstrip("/")
NINEROUTER_BASE_URL = f"{NINEROUTER_URL}/v1" if not NINEROUTER_URL.endswith("/v1") else NINEROUTER_URL

GEMINI_API_KEYS = _get_keys("GEMINI_API_KEY")
GROQ_API_KEYS = _get_keys("GROQ_API_KEY")
OPENROUTER_API_KEYS = _get_keys("OPENROUTER_API_KEY")
NVIDIA_API_KEYS = _get_keys("NVIDIA_API_KEY")
OPENCODE_ZEN_API_KEYS = _get_keys("OPENCODE_ZEN_API_KEY")
STABILITY_API_KEYS = _get_keys("STABILITY_API_KEY")
OMNIROUTE_API_KEYS = _get_keys("OMNIROUTE_API_KEY")

_cfg_model = CONFIG.get("script", {}).get("model", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "9router")

if LLM_PROVIDER == "9router":
    LLM_API_KEYS = NINEROUTER_API_KEYS
    LLM_BASE_URL = NINEROUTER_BASE_URL
    LLM_MODEL = "gemini/gemini-3.6-flash"
elif LLM_PROVIDER == "gemini":
    LLM_API_KEYS = GEMINI_API_KEYS if GEMINI_API_KEYS else NINEROUTER_API_KEYS
    LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "models/gemini-3.5-flash")
elif LLM_PROVIDER == "groq":
    LLM_API_KEYS = GROQ_API_KEYS if GROQ_API_KEYS else NINEROUTER_API_KEYS
    LLM_BASE_URL = "https://api.groq.com/openai/v1"
    LLM_MODEL = "openai/gpt-oss-120b"
else:
    LLM_API_KEYS = NINEROUTER_API_KEYS
    LLM_BASE_URL = NINEROUTER_BASE_URL
    LLM_MODEL = "gemini/gemini-3.6-flash"

if not LLM_API_KEYS:
    LLM_API_KEYS = ["sk-1f7d1788ce9c1aa7-gixqcc-64a9e8fd"]
LLM_API_KEY = LLM_API_KEYS[0]

# ============================================================
# Comprehensive Fallback Providers Sequence:
# 1. 9Router Full Multi-Provider Pool (Gemini, OpenRouter, GPT, OpenCode Free, Kilo Free, ChatByte, Nvidia)
# 2. Direct Providers (Google Direct -> Groq Direct -> OpenRouter Direct -> Nvidia -> Opencode)
# ============================================================
FALLBACK_PROVIDERS = []

# --- 1. 9Router Providers (Gateway AWS) ---
if NINEROUTER_API_KEYS:
    # A. Tier 1: Fastest & Primary (<1.5s)
    FALLBACK_PROVIDERS.append({
        "name": "9router-gemini",
        "keys": NINEROUTER_API_KEYS,
        "base_url": NINEROUTER_BASE_URL,
        "model": "gemini/gemini-3.6-flash"
    })
    FALLBACK_PROVIDERS.append({
        "name": "9router-openrouter",
        "keys": NINEROUTER_API_KEYS,
        "base_url": NINEROUTER_BASE_URL,
        "model": "openrouter/meta-llama/llama-3.3-70b-instruct"
    })
    FALLBACK_PROVIDERS.append({
        "name": "9router-gpt4o",
        "keys": NINEROUTER_API_KEYS,
        "base_url": NINEROUTER_BASE_URL,
        "model": "gh/gpt-4o-mini"
    })
    FALLBACK_PROVIDERS.append({
        "name": "9router-gemini-lite",
        "keys": NINEROUTER_API_KEYS,
        "base_url": NINEROUTER_BASE_URL,
        "model": "gemini/gemini-3.5-flash-lite"
    })
    
    # B. Tier 2: Free Tier Models on 9Router (OpenCode Free, Kilo Free, ChatByte AI)
    FALLBACK_PROVIDERS.append({
        "name": "9router-opencode-free",
        "keys": NINEROUTER_API_KEYS,
        "base_url": NINEROUTER_BASE_URL,
        "model": "oc/mimo-v2.5-free"
    })
    FALLBACK_PROVIDERS.append({
        "name": "9router-kilo-free",
        "keys": NINEROUTER_API_KEYS,
        "base_url": NINEROUTER_BASE_URL,
        "model": "kc/minimax/minimax-m3:free"
    })
    FALLBACK_PROVIDERS.append({
        "name": "9router-chatbyte",
        "keys": NINEROUTER_API_KEYS,
        "base_url": NINEROUTER_BASE_URL,
        "model": "cbai/glm-5.2"
    })
    FALLBACK_PROVIDERS.append({
        "name": "9router-ag-gemini",
        "keys": NINEROUTER_API_KEYS,
        "base_url": NINEROUTER_BASE_URL,
        "model": "ag/gemini-3.7-flash-medium"
    })
    FALLBACK_PROVIDERS.append({
        "name": "9router-nvidia-minimax",
        "keys": NINEROUTER_API_KEYS,
        "base_url": NINEROUTER_BASE_URL,
        "model": "nvidia/minimaxai/minimax-m3"
    })

# --- 2. Direct Providers (Fallback jika server 9Router tidak terjangkau) ---
if GEMINI_API_KEYS:
    FALLBACK_PROVIDERS.append({
        "name": "gemini",
        "keys": GEMINI_API_KEYS,
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.6-flash"
    })
if GROQ_API_KEYS:
    FALLBACK_PROVIDERS.append({
        "name": "groq",
        "keys": GROQ_API_KEYS,
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b"
    })
if OPENROUTER_API_KEYS:
    FALLBACK_PROVIDERS.append({
        "name": "openrouter",
        "keys": OPENROUTER_API_KEYS,
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct"
    })
if NVIDIA_API_KEYS:
    FALLBACK_PROVIDERS.append({
        "name": "nvidia",
        "keys": NVIDIA_API_KEYS,
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "meta/llama-3.1-70b-instruct"
    })
if OPENCODE_ZEN_API_KEYS:
    FALLBACK_PROVIDERS.append({
        "name": "opencode-zen",
        "keys": OPENCODE_ZEN_API_KEYS,
        "base_url": "https://api.opencodezen.com/v1",
        "model": "gpt-4o-mini"
    })
