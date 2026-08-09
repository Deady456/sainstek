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

_pexels_keys = []
for k, v in os.environ.items():
    if k.startswith("PEXELS_API_KEY") and v.strip():
        import re
        _pexels_keys.extend([x.strip().strip('\"').strip('\'') for x in re.split(r',|\n|\\n', v) if x.strip()])
PEXELS_API_KEYS = _pexels_keys if _pexels_keys else ["dummy_key"]
import random
random.shuffle(PEXELS_API_KEYS)
_cfg_model = CONFIG.get("script", {}).get("model", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini" if "gemini" in _cfg_model.lower() else "groq")
_gkeys = []
for k, v in os.environ.items():
    if k.startswith("GEMINI_API_KEY") and v.strip():
        _gkeys.extend([x.strip().strip('\"').strip('\'') for x in re.split(r',|\n|\\n', v) if x.strip()])
GEMINI_API_KEYS = _gkeys if _gkeys else [""]
GEMINI_API_KEY = GEMINI_API_KEYS[0]

_grkeys = []
for k, v in os.environ.items():
    if k.startswith("GROQ_API_KEY") and v.strip():
        _grkeys.extend([x.strip().strip('\"').strip('\'') for x in re.split(r',|\n|\\n', v) if x.strip()])
GROQ_API_KEYS = _grkeys if _grkeys else ["dummy"]

_omnkeys = []
for k, v in os.environ.items():
    if k.startswith("OMNIROUTE_API_KEY") and v.strip():
        _omnkeys.extend([x.strip().strip('\"').strip('\'') for x in re.split(r',|\n|\\n', v) if x.strip()])
OMNIROUTE_API_KEYS = _omnkeys if _omnkeys else ["dummy"]

if LLM_PROVIDER == "gemini":
    LLM_API_KEY = GEMINI_API_KEY
    LLM_API_KEYS = GEMINI_API_KEYS
    LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "models/gemini-2.5-flash")
elif LLM_PROVIDER == "groq":
    LLM_API_KEYS = GROQ_API_KEYS
    LLM_API_KEY = LLM_API_KEYS[0]
    LLM_BASE_URL = "https://api.groq.com/openai/v1"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "llama-3.3-70b-versatile")
elif LLM_PROVIDER == "omniroute":
    _model = CONFIG.get("script", {}).get("model", "")
    LLM_API_KEYS = OMNIROUTE_API_KEYS
    LLM_API_KEY = LLM_API_KEYS[0] if LLM_API_KEYS else "dummy"
    LLM_BASE_URL = "https://openrouter.ai/api/v1"
    
    # Prefix model with 'meta-llama/' if it's a llama model so OpenRouter understands it
    if _model == "llama-3.3-70b-versatile":
        LLM_MODEL = "meta-llama/llama-3.3-70b-instruct"
    else:
        LLM_MODEL = _model if _model else "meta-llama/llama-3.3-70b-instruct"
else:
    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
