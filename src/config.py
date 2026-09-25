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

# Direct API Keys (from GitHub credentials)
OPENROUTER_API_KEYS = _get_keys("OPENROUTER_API_KEY")
GEMINI_API_KEYS = _get_keys("GEMINI_API_KEY")
GROQ_API_KEYS = _get_keys("GROQ_API_KEY")
NVIDIA_API_KEYS = _get_keys("NVIDIA_API_KEY")
OPENCODE_ZEN_API_KEYS = _get_keys("OPENCODE_ZEN_API_KEY")
STABILITY_API_KEYS = _get_keys("STABILITY_API_KEY")

_cfg_model = CONFIG.get("script", {}).get("model", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openrouter")

# Primary LLM Configuration - OpenRouter is the confirmed working provider
if LLM_PROVIDER == "openrouter":
    LLM_API_KEYS = OPENROUTER_API_KEYS if OPENROUTER_API_KEYS else ["no-key"]
    LLM_BASE_URL = "https://openrouter.ai/api/v1"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "meta-llama/llama-3.3-70b-instruct")
elif LLM_PROVIDER == "gemini":
    LLM_API_KEYS = GEMINI_API_KEYS if GEMINI_API_KEYS else OPENROUTER_API_KEYS
    LLM_BASE_URL = "https://openrouter.ai/api/v1"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "meta-llama/llama-3.3-70b-instruct")
elif LLM_PROVIDER == "groq":
    LLM_API_KEYS = GROQ_API_KEYS if GROQ_API_KEYS else OPENROUTER_API_KEYS
    LLM_BASE_URL = "https://openrouter.ai/api/v1"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "meta-llama/llama-3.3-70b-instruct")
else:
    LLM_API_KEYS = OPENROUTER_API_KEYS if OPENROUTER_API_KEYS else ["no-key"]
    LLM_BASE_URL = "https://openrouter.ai/api/v1"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "meta-llama/llama-3.3-70b-instruct")

if not LLM_API_KEYS:
    LLM_API_KEYS = ["no-key-configured"]
LLM_API_KEY = LLM_API_KEYS[0]

# Fallback Providers - only providers with confirmed working API keys
FALLBACK_PROVIDERS = []

# Primary: OpenRouter (confirmed working)
if OPENROUTER_API_KEYS:
    FALLBACK_PROVIDERS.append({
        "name": "openrouter",
        "keys": OPENROUTER_API_KEYS,
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct"
    })
    # Add working OpenRouter models
    FALLBACK_PROVIDERS.append({
        "name": "openrouter-gpt4o",
        "keys": OPENROUTER_API_KEYS,
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini"
    })

# Direct providers (only added if their API keys are confirmed working)
# NOTE: GEMINI_API_KEYS and GROQ_API_KEYS currently return 401/403 from direct API.
# They are kept here for reference but not added to FALLBACK_PROVIDERS.
# To enable, verify API key and add back the blocks below.

if NVIDIA_API_KEYS:
    FALLBACK_PROVIDERS.append({"name": "nvidia", "keys": NVIDIA_API_KEYS, "base_url": "https://integrate.api.nvidia.com/v1", "model": "meta/llama-3.1-70b-instruct"})
if OPENCODE_ZEN_API_KEYS:
    FALLBACK_PROVIDERS.append({"name": "opencode-zen", "keys": OPENCODE_ZEN_API_KEYS, "base_url": "https://api.opencodezen.com/v1", "model": "gpt-4o-mini"})
if STABILITY_API_KEYS:
    FALLBACK_PROVIDERS.append({"name": "stability", "keys": STABILITY_API_KEYS, "base_url": "https://api.stability.ai/v1", "model": "stable-diffusion-xl-base-1.0"})
