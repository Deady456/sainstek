import os
from openai import OpenAI

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")

def _get_client():
    if LLM_PROVIDER == "groq" and GROQ_API_KEY:
        return OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    elif LLM_PROVIDER == "openrouter" and OPENROUTER_API_KEY:
        return OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
    elif LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
        return OpenAI(api_key=GEMINI_API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    elif OPENROUTER_API_KEY:
        return OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
    elif GROQ_API_KEY:
        return OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    elif GEMINI_API_KEY:
        return OpenAI(api_key=GEMINI_API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    raise ValueError("No valid API key configured")

def _get_default_model():
    if LLM_PROVIDER == "groq":
        return "openai/gpt-oss-120b"
    elif LLM_PROVIDER == "gemini":
        return "gemini-3.5-flash"
    elif LLM_PROVIDER == "openrouter":
        return "meta-llama/llama-3.3-70b-instruct"
    return "meta-llama/llama-3.3-70b-instruct"

def generate_chat(prompt, model=None, system_prompt=""):
    client = _get_client()
    model = model or _get_default_model()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(model=model, messages=messages, max_tokens=100)
    return resp.choices[0].message.content

def generate_image(prompt, output_path="output.png", model="ag/gemini-3.1-flash-image"):
    client = _get_client()
    resp = client.images.generate(model=model, prompt=prompt, size="1024x1024")
    item = resp.data[0]
    import base64, urllib.request
    if hasattr(item, 'b64_json') and item.b64_json:
        with open(output_path, "wb") as f: f.write(base64.b64decode(item.b64_json))
    elif hasattr(item, 'url') and item.url:
        urllib.request.urlretrieve(item.url, output_path)
    return output_path

def generate_tts(text, output_path="speech.mp3", model="gemini/gemini-3.1-flash-tts-preview"):
    client = _get_client()
    resp = client.audio.speech.create(model=model, input=text, voice="alloy")
    import wave
    with open(output_path, "wb") as f: f.write(resp.content)
    return output_path

if __name__ == "__main__":
    print("Testing Multi-Provider Client...")
    try:
        reply = generate_chat("Tes: sebutkan 1 kalimat motivasi singkat.")
        print("[CHAT SUCCESS]:", reply)
    except Exception as e:
        print("[CHAT ERROR]:", e)
