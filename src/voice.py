
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


﻿import asyncio
import os
import time
from pathlib import Path
import edge_tts
from .config import CONFIG
from elevenlabs.client import ElevenLabs


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


def _synth_elevenlabs(text: str, out_path: Path, v: dict, api_key: str) -> None:
    client = ElevenLabs(api_key=api_key)
    audio = client.text_to_speech.convert(
        voice_id=v.get("elevenlabs_voice_id", "3mAVBNEqop5UbHtD8oxQ"),
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )
    with open(out_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)



def _speed_up(audio_path: Path, rate: float = 1.15):
    import subprocess
    tmp = audio_path.with_suffix(".tmp.mp3")
    subprocess.run(["ffmpeg", "-y", "-i", str(audio_path), "-filter:a", f"atempo={rate}", str(tmp)], capture_output=True)
    tmp.replace(audio_path)


def synth(text: str, out_path: Path) -> Path:
    text = replace_numbers_id(text)
    v = CONFIG["voice"]
    provider = v.get("provider", "elevenlabs")
    print(f"    voice: {v['voice']}, {len(text)} chars, provider: {provider}")

    t0 = time.time()

    if provider == "elevenlabs":
        keys_str = os.environ.get("ELEVENLABS_API_KEYS", "")
        import re
        keys = [k.strip() for k in re.split(r',|\n|\\n', keys_str) if k.strip()]

        if keys:
            for i, api_key in enumerate(keys):
                try:
                    _synth_elevenlabs(text, out_path, v, api_key)
                    print(f"    done in {time.time()-t0:.1f}s (elevenlabs key[{i}])")
                    return out_path
                except Exception as e:
                    print(f"    key[{i}] failed: {e}, trying next")
                    continue
            print(f"    all elevenlabs keys failed, falling back to edge-tts")
        else:
            print(f"    no elevenlabs keys set, falling back to edge-tts")

    _synth_edge(text, out_path, v)
    if not out_path.exists() or out_path.stat().st_size < 1024:
        raise RuntimeError(
            f"edge-tts produced invalid audio ({out_path.stat().st_size if out_path.exists() else 0} bytes). "
            "All voice providers failed."
        )
    print(f"    done in {time.time()-t0:.1f}s (edge-tts)")
    return out_path

