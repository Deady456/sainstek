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
else:
    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
