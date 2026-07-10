import asyncio
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


def synth(text: str, out_path: Path) -> Path:
    v = CONFIG["voice"]
    provider = v.get("provider", "elevenlabs")
    print(f"    voice: {v['voice']}, {len(text)} chars, provider: {provider}")

    t0 = time.time()

    if provider == "elevenlabs":
        keys_str = os.environ.get("ELEVENLABS_API_KEYS", "")
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]

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
    print(f"    done in {time.time()-t0:.1f}s (edge-tts)")
    return out_path
