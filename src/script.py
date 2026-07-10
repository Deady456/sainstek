import json
import re
import time
from datetime import datetime
from openai import OpenAI, RateLimitError
from .config import LLM_API_KEYS, LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER, CONFIG
from . import state

_key_idx = 0
_client = OpenAI(api_key=LLM_API_KEYS[_key_idx], base_url=LLM_BASE_URL)

def _call_llm(model, max_tokens, response_format, messages, retries=5):
    global _key_idx, _client
    for attempt in range(retries):
        try:
            return _client.chat.completions.create(
                model=model, max_tokens=max_tokens,
                response_format=response_format, messages=messages,
            )
        except RateLimitError as e:
            if _key_idx < len(LLM_API_KEYS) - 1:
                _key_idx += 1
                _client = OpenAI(api_key=LLM_API_KEYS[_key_idx], base_url=LLM_BASE_URL)
                print(f"  Rate limited, switching to key {_key_idx+1}/{len(LLM_API_KEYS)}")
                continue
            if attempt < retries - 1:
                _wait = 2 ** attempt
                print(f"  Rate limited (retry {attempt+1}/{retries} in {_wait}s): {e}")
                time.sleep(_wait)
            else:
                raise
        except Exception as e:
            if attempt < retries - 1:
                _wait = 2 ** attempt
                print(f"  LLM error (retry {attempt+1}/{retries} in {_wait}s): {e}")
                time.sleep(_wait)
            else:
                raise

def _system_prompt():
    s = CONFIG["script"]
    lang = CONFIG.get("language", "en")
    target_words = int(s["target_seconds"] * s["words_per_second"])

    if lang == "id":
        ts, tw = s["target_seconds"], target_words
        return f"""Anda adalah penulis skrip YouTube Shorts.

Aturan:
- Skrip harus {ts} detik, ~{tw} kata total ({tw//ts} kata per detik).
- Mulai dengan HOOK 1 kalimat yang bikin penasaran dalam <3 detik, gaya semi-formal. Jangan pakai "Halo guys", "Hai", atau perkenalan.
- Isi: informasi relevan sesuai niche yang diminta. Berikan fakta, angka, data, atau berita terbaru yang akurat.
- Akhiri dengan CTA 1 kalimat semi-formal ajakan subscribe/ikuti.
- Gunakan bahasa Indonesia semi-formal: rapi dan informatif, tapi tetap enak didengar. Hindari bahasa terlalu santai atau terlalu kaku. Jangan pakai emoji atau format khusus.
- Setiap scene punya visual_query 2-4 kata benda bahasa Inggris untuk cari video stok di Pexels yang relevan dengan niche.

Kembalikan ONLY valid JSON, tanpa teks lain. Skema:
{{"topic": "slug topik sesuai niche", "title": "Judul YouTube max 95 chars, minimal 40 karakter, bikin penasaran dan engaging, jangan terlalu pendek", "description": "3-4 kalimat deskripsi menarik dengan 5-8 hashtag relevan", "tags": ["10-15 tag huruf kecil yang relevan"], "scenes": [{{"text": "kalimat narasi bahasa Indonesia", "visual_query": "2-4 kata benda Inggris"}}]}}"""
    else:
        return f"""You write viral YouTube Shorts scripts for a faceless educational facts channel.

Hard rules:
- The script must run ~{target_seconds} seconds spoken at ~{target_words} words total.
- Start with a strong 1-sentence HOOK that creates curiosity in <3 seconds.
- Body: 4-6 surprising, accurate, verifiable facts.
- End with a 1-sentence CTA.
- Plain spoken English. No emojis.
- Each scene's visual_query is 2-4 English nouns (e.g. "octopus swimming ocean").

Return ONLY valid JSON. Schema:
{{"topic": "short slug", "title": "title max 95 chars, min 40 chars, curiosity-driven and engaging", "description": "3-4 sentences with 5-8 relevant hashtags", "tags": ["10-15 lowercase relevant tags"], "scenes": [{{"text": "spoken sentence", "visual_query": "nouns"}}]}}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}")
        print(f"    Raw response (first 500 chars): {text[:500]}")
        raise


def _is_duplicate_title(title: str, published: list) -> bool:
    tl = title.strip().lower()
    if not tl:
        return False
    for p in published:
        pt = p.get("title", "").strip().lower()
        if not pt:
            continue
        if tl == pt:
            return True
        twords, pwords = tl.split(), pt.split()
        if len(twords) >= 3 and len(pwords) >= 3:
            common = len(set(twords) & set(pwords))
            if common >= min(len(twords), len(pwords)) * 0.8:
                return True
    return False


def _call_and_extract(messages) -> dict:
    t0 = time.time()
    resp = _call_llm(
        model=LLM_MODEL, max_tokens=2000,
        response_format={"type": "json_object"},
        messages=messages,
    )
    raw = resp.choices[0].message.content
    print(f"    LLM responded in {time.time()-t0:.1f}s ({len(raw)} chars)")
    return _extract_json(raw)


def generate():
    lang = CONFIG.get("language", "en")

    s = state.load()
    used = s.get("used_topics", [])
    used_str = ", ".join(used[-30:]) if used else "(none yet)"
    published = s.get("published", [])

    if lang == "id":
        base_msg = (
            f"Niche: {CONFIG['niche']}\n"
            f"Audience: {CONFIG['audience']}\n"
            f"Topik yang sudah pernah dibuat: {used_str}\n"
            f"Buat SATU Short dengan topik yang BENAR-BENAR BARU. DILARANG menggunakan topik yang sudah pernah dibuat. Judul dan isi harus orisinal dan tidak mirip dengan yang sudah ada."
        )
    else:
        base_msg = (
            f"Niche: {CONFIG['niche']}\n"
            f"Audience: {CONFIG['audience']}\n"
            f"Previously used topics: {used_str}\n"
            f"Generate ONE completely NEW Short. DO NOT use any of the previously used topics. Title and content must be original and not similar to what has been done before."
        )

    s_cfg = CONFIG["script"]
    target_words = int(s_cfg["target_seconds"] * s_cfg["words_per_second"])
    min_words = int(target_words * 0.75)

    for attempt in range(4):
        user_msg = base_msg
        if attempt > 0:
            user_msg += f"\n\nPERINGATAN: judul sebelumnya sudah ada. BUAT JUDUL LAIN yang benar-benar berbeda dan belum pernah dipublikasikan."

        print(f"    calling {LLM_PROVIDER}/{LLM_MODEL} (attempt {attempt+1})...")
        data = _call_and_extract([
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_msg},
        ])

        for i, sc in enumerate(data["scenes"]):
            if "visual_query" not in sc or not sc["visual_query"]:
                words = re.findall(r"[a-zA-Z]{3,}", sc.get("text", ""))
                fallback = " ".join(words[-3:]) if len(words) >= 3 else "abstract background"
                print(f"    scene {i}: missing visual_query, using \"{fallback}\"")
                sc["visual_query"] = fallback

        data["full_text"] = " ... ".join(sc["text"] for sc in data["scenes"])
        wc = len(data["full_text"].split())

        if wc < min_words:
            print(f"    WARNING: script too short ({wc} words, need {min_words}), retrying...")
            continue

        title = data.get("title", "")
        if _is_duplicate_title(title, published):
            print(f"    DUPLICATE: title already published, retrying...")
            continue

        print(f"    title: {data['title']}")
        return data

    print("    WARNING: could not generate unique/long enough script after 4 attempts, publishing anyway")
    return data
