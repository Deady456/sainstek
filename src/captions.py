import os
import warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", category=UserWarning)
import time
from pathlib import Path
from faster_whisper import WhisperModel
from .config import CONFIG

_model = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        size = CONFIG["captions"].get("whisper_model", "base")
        _model = WhisperModel(size, device="cpu", compute_type="int8")
    return _model


def transcribe_words(audio_path: Path) -> list[dict]:
    model = _get_model()
    print(f"    model loaded, transcribing {audio_path.name}...")
    t0 = time.time()
    segments, info = model.transcribe(str(audio_path), word_timestamps=True)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({"word": w.word, "start": float(w.start), "end": float(w.end)})
    print(f"    done in {time.time()-t0:.1f}s")
    return words


def _fmt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h:01d}:{m:02d}:{s:05.2f}"


def write_ass(words: list[dict], out_path: Path, video_w: int, video_h: int, offset: float = 0.0) -> Path:
    c = CONFIG["captions"]
    chunk_size = c.get("words_per_caption", 3)
    font_size = c.get("font_size", 70)
    margin_v = int(video_h * (1 - c.get("position_y", 0.5)))
    
    channel = CONFIG.get("upload", {}).get("channel", "default")
    channel_pill_colors = {
        "animewebai": "&H00E22B8A&",   # Neon Purple
        "sainstek": "&H00FF8800&",     # Electric Blue
        "kisahnyata": "&H003C14DC&",   # Crimson Red
        "misteriasia": "&H000000B2&",  # Dark Red
        "kasusmisteri": "&H003C14DC&", # Crimson Red
        "whatif": "&H000066FF&",       # Amber Orange
        "lofisleep": "&H00808000&",    # Soft Teal
        "serenitymind": "&H0054082E&", # Deep Indigo
        "default": "&H000000CC&",      # Red Accent
    }
    accent_pill = channel_pill_colors.get(channel, "&H000000CC&")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{c['font']},{font_size},{c['primary_color']},&H00FFFFFF,{c['outline_color']},&H00000000,-1,0,0,0,100,100,0,0,1,{c['outline']},2,2,40,40,{margin_v},1
Style: HookPill,{c['font']},{font_size},&H00FFFFFF&,&H00FFFFFF&,{accent_pill},&H00000000,-1,0,0,0,100,100,0,0,3,14,0,2,40,40,{margin_v},1
Style: DarkPill,{c['font']},{font_size},&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H00000000,-1,0,0,0,100,100,0,0,3,14,0,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = []
    hook_end_time = 3.0

    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        start_sec = chunk[0]["start"] + offset
        end_sec = chunk[-1]["end"] + offset
        start = _fmt_ts(start_sec)
        end = _fmt_ts(end_sec)
        text = " ".join(w["word"].strip() for w in chunk).upper()

        if start_sec < hook_end_time:
            style_name = "HookPill" if i == 0 else "DarkPill"
            text_fmt = "{\\fscx125\\fscy125\\t(0,150,\\fscx100\\fscy100)}" + text
        else:
            style_name = "Default"
            if chunk_size <= 2:
                text_fmt = "{\\fscx120\\fscy120\\t(0,150,\\fscx100\\fscy100)}" + text
            else:
                text_fmt = text

        lines.append(f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,{text_fmt}")

    out_path.write_text(header + "\\n".join(lines), encoding="utf-8")
    return out_path
