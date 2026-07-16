import os
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

PEXELS_API_KEY = os.environ["PEXELS_API_KEY"]
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

if LLM_PROVIDER == "gemini":
    LLM_API_KEY = os.environ["GEMINI_API_KEY"]
    LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "models/gemini-2.5-flash")
elif LLM_PROVIDER == "groq":
    import re
    _keys = []
    for k, v in os.environ.items():
        if k.startswith("GROQ_API_KEY") and v.strip():
            _keys.extend([x.strip() for x in re.split(r'[,\n]+', v) if x.strip()])
    LLM_API_KEYS = _keys if _keys else ["dummy"]
    LLM_API_KEY = LLM_API_KEYS[0]
    LLM_BASE_URL = "https://api.groq.com/openai/v1"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "llama-3.3-70b-versatile")
else:
    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
