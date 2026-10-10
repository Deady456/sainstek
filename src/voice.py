#!/usr/bin/env python3
"""
voice.py - TTS Synthesis dengan hierarki provider:
  1. ShellShock AWS google-tts/id  (GRATIS, unlimited, priority utama)
  2. ElevenLabs                    (jika ELEVENLABS_API_KEYS tersedia)
  3. Edge-TTS                      (last resort fallback, offline-capable)
"""

import re


def num_to_words_id(n: int) -> str:
    if n == 0:
        return 'nol'
    satuan = ['', 'satu', 'dua', 'tiga', 'empat', 'lima', 'enam', 'tujuh', 'delapan', 'sembilan', 'sepuluh', 'sebelas']
    if n < 12:
        return satuan[n]
    if n < 20:
        return num_to_words_id(n - 10) + ' belas'
    if n < 100:
        return satuan[n // 10] + ' puluh' + ((' ' + num_to_words_id(n % 10)) if n % 10 != 0 else '')
    if n < 200:
        return 'seratus' + ((' ' + num_to_words_id(n - 100)) if n - 100 != 0 else '')
    if n < 1000:
        return satuan[n // 100] + ' ratus' + ((' ' + num_to_words_id(n % 100)) if n % 100 != 0 else '')
    if n < 2000:
        return 'seribu' + ((' ' + num_to_words_id(n - 1000)) if n - 1000 != 0 else '')
    if n < 1000000:
        return num_to_words_id(n // 1000) + ' ribu' + ((' ' + num_to_words_id(n % 1000)) if n % 1000 != 0 else '')
    if n < 1000000000:
        return num_to_words_id(n // 1000000) + ' juta' + ((' ' + num_to_words_id(n % 1000000)) if n % 1000000 != 0 else '')
    if n < 1000000000000:
        return num_to_words_id(n // 1000000000) + ' miliar' + ((' ' + num_to_words_id(n % 1000000000)) if n % 1000000000 != 0 else '')
    return str(n)


def replace_numbers_id(text: str) -> str:
    """Convert all numeric digits to spelled-out Indonesian words for TTS."""
    if not isinstance(text, str):
        return text
    # 1. Ordinals: ke-1, ke-2
    text = re.sub(r'\bke-(\d+)\b', lambda m: ('pertama' if m.group(1) == '1' else ('ke' + num_to_words_id(int(m.group(1))))), text, flags=re.IGNORECASE)
    # 2. Decimal percentages: 99.9% / 99,9%
    text = re.sub(r'(\d+)[.,](\d+)\s*%', lambda m: f"{num_to_words_id(int(m.group(1)))} koma {num_to_words_id(int(m.group(2)))} persen", text)
    # 3. Percentages: 50%
    text = re.sub(r'(\d+)\s*%', lambda m: f"{num_to_words_id(int(m.group(1)))} persen", text)
    # 4. Decimals: 3.5 / 3,5
    text = re.sub(r'(\d+)[.,](\d+)', lambda m: f"{num_to_words_id(int(m.group(1)))} koma {num_to_words_id(int(m.group(2)))}", text)
    # 5. Standalone integers
    text = re.sub(r'\b(\d+)\b', lambda m: num_to_words_id(int(m.group(1))), text)
    return text


import asyncio
import os
import time
import urllib.request
import json
from pathlib import Path
import edge_tts
from .config import CONFIG
try:
    from elevenlabs.client import ElevenLabs
    _ELEVENLABS_AVAILABLE = True
except ImportError:
    _ELEVENLABS_AVAILABLE = False


# ============================================================
# ShellShock AWS Constants
# ============================================================
SHELLSHOCK_AWS_BASE = "http://13.214.34.200:20128"
SHELLSHOCK_AWS_KEY  = "sk-1f7d1788ce9c1aa7-qgi726-f1cb1818"
SHELLSHOCK_TTS_MODEL = "google-tts/id"   # Gratis, unlimited, bahasa Indonesia


# ============================================================
# Voice Variety System
# ============================================================

def _get_voice_config() -> dict:
    """Get voice config with variety support."""
    cfg = CONFIG.get("voice", {})
    variety = cfg.get("variety", {})

    if variety.get("enabled", False):
        voices = variety.get("voices", [])
        strategy = variety.get("strategy", "round_robin")

        if voices:
            voice = _select_voice(voices, strategy)
            return {
                **cfg,
                "voice": voice.get("edge_id", cfg.get("voice")),
                "elevenlabs_voice_id": voice.get("elevenlabs_id"),
                "_voice_name": voice.get("name"),
                "_voice_gender": voice.get("gender"),
            }

    return cfg


def _select_voice(voices: list[dict], strategy: str) -> dict:
    """Select voice based on strategy."""
    from . import state

    s = state.load()
    voice_idx = s.get("_voice_idx", 0)

    if strategy == "round_robin":
        selected = voices[voice_idx % len(voices)]
        state.update({"_voice_idx": voice_idx + 1})
    elif strategy == "random":
        import random
        selected = random.choice(voices)
    else:
        selected = voices[voice_idx % len(voices)]
        state.update({"_voice_idx": voice_idx + 1})

    print(f"    voice: selected {selected.get('name', 'unknown')} ({selected.get('gender', '?')})")
    return selected


# ============================================================
# TTS Providers
# ============================================================

def _synth_shellshock_google_tts(text: str, out_path: Path) -> None:
    """PRIMARY: ShellShock AWS google-tts/id — gratis, unlimited, bahasa Indonesia."""
    payload = json.dumps({
        "model": SHELLSHOCK_TTS_MODEL,
        "input": text,
        "voice": "id",
    }).encode("utf-8")
    req = urllib.request.Request(
        SHELLSHOCK_AWS_BASE + "/v1/audio/speech",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {SHELLSHOCK_AWS_KEY}",
            "Content-Type": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        audio = r.read()
    if len(audio) < 512:
        raise RuntimeError(f"ShellShock google-tts returned too small audio: {len(audio)} bytes")
    out_path.write_bytes(audio)


def _synth_elevenlabs(text: str, out_path: Path, v: dict, api_key: str) -> None:
    client = ElevenLabs(api_key=api_key)
    model_id = v.get("elevenlabs_model", "eleven_multilingual_v2")
    audio = client.text_to_speech.convert(
        voice_id=v.get("elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM"),
        text=text,
        model_id=model_id,
        output_format="mp3_44100_128",
    )
    with open(out_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)


def _synth_edge(text: str, out_path: Path, v: dict) -> None:
    async def _go():
        com = edge_tts.Communicate(
            text,
            voice=v["voice"],
            rate=v.get("rate", "+0%"),
            pitch=v.get("pitch", "+0Hz"),
        )
        await com.save(str(out_path))
    asyncio.run(_go())


def _speed_up(audio_path: Path, rate: float = 1.15):
    import subprocess
    tmp = audio_path.with_suffix(".tmp.mp3")
    subprocess.run(["ffmpeg", "-y", "-i", str(audio_path), "-filter:a", f"atempo={rate}", str(tmp)], capture_output=True)
    tmp.replace(audio_path)


# ============================================================
# Main synth() — Provider waterfall
# ============================================================

def synth(text: str, out_path: Path) -> Path:
    text = replace_numbers_id(text)
    v = _get_voice_config()
    voice_name = v.get("_voice_name", v.get("voice", "google-tts"))
    print(f"    voice: {voice_name}, {len(text)} chars")

    t0 = time.time()

    # ---- 1. ShellShock AWS google-tts/id (UTAMA - GRATIS) ----
    try:
        _synth_shellshock_google_tts(text, out_path)
        print(f"    done in {time.time()-t0:.1f}s (shellshock aws google-tts/id)")
        return out_path
    except Exception as e:
        print(f"    shellshock google-tts failed: {e} — trying next provider")

    # ---- 2. ElevenLabs (jika ada key) ----
    if _ELEVENLABS_AVAILABLE:
        provider = CONFIG.get("voice", {}).get("provider", "elevenlabs")
        if provider == "elevenlabs":
            keys_str = os.environ.get("ELEVENLABS_API_KEYS", "")
            keys = [k.strip() for k in re.split(r',|\n|\\n', keys_str) if k.strip()]
            if keys:
                for i, api_key in enumerate(keys):
                    for attempt in range(2):
                        try:
                            _synth_elevenlabs(text, out_path, v, api_key)
                            print(f"    done in {time.time()-t0:.1f}s (elevenlabs key[{i}], attempt {attempt+1})")
                            return out_path
                        except Exception as e:
                            err_msg = str(e).lower()
                            if "rate" in err_msg or "limit" in err_msg or "429" in err_msg:
                                print(f"    key[{i}] rate limited (attempt {attempt+1}), trying next")
                                break
                            elif "paid_plan_required" in err_msg or "402" in err_msg:
                                print(f"    key[{i}] needs paid plan, trying next")
                                break
                            else:
                                print(f"    key[{i}] error (attempt {attempt+1}): {e}")
                                if attempt == 0:
                                    time.sleep(1)
                                continue
                print(f"    all {len(keys)} elevenlabs keys exhausted")

    # ---- 3. Edge-TTS (last resort) ----
    print(f"    falling back to edge-tts (last resort)")
    _synth_edge(text, out_path, v)
    if not out_path.exists() or out_path.stat().st_size < 1024:
        raise RuntimeError(
            f"edge-tts produced invalid audio ({out_path.stat().st_size if out_path.exists() else 0} bytes). "
            "All voice providers failed."
        )
    print(f"    done in {time.time()-t0:.1f}s (edge-tts fallback)")
    return out_path
