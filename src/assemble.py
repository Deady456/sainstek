import os
import json
import random
import subprocess
from pathlib import Path
from .config import CONFIG, ROOT

def _run(cmd: list[str], desc: str = ""):
    if desc:
        print(f"    ffmpeg: {desc}")
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        tail = (p.stderr or "")[-3000:]
        raise RuntimeError(f"FFmpeg command failed (exit {p.returncode}): {cmd[0]} ...\n--- stderr ---\n{tail}")

def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])

def build(
    scene_videos: list[Path],
    voice_audio: Path,
    captions_ass: Path,
    out_path: Path,
    work_dir: Path,
    words: list[dict] = None,
    scenes: list[dict] = None,
    videos_per_scene: int = 1,
    hook_text: str = "",
    thumbnail_img: Path = None,
) -> Path:
    """
    Assemble scene videos, voice narration, background music, and captions using FFmpeg.
    """
    v = CONFIG["video"]
    w, h, fps = v["width"], v["height"], v["fps"]
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write concat list for scene videos
    concat_list = work_dir / "concat_scenes.txt"
    concat_lines = [f"file '{p.absolute().as_posix()}'" for p in scene_videos]
    concat_list.write_text("\n".join(concat_lines), encoding="utf-8")

    combined_video = work_dir / "combined_video.mp4"
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(combined_video),
    ], "concatenating news scene videos")

    # 2. Pick background music (random from assets/music/ or assets/bg.mp3)
    music_candidates = []
    music_dir = ROOT / "assets" / "music"
    if music_dir.is_dir():
        for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg"):
            music_candidates.extend(list(music_dir.rglob(ext)))
    if not music_candidates:
        music_candidates = [p for p in (ROOT / "assets").glob("*.mp3") if p.is_file() and p.name != "bg.mp3"]

    bg_music = random.choice(music_candidates) if music_candidates else (ROOT / "assets" / "bg.mp3")

    audio_dur = probe_duration(voice_audio)
    video_dur = probe_duration(combined_video)
    final_dur = max(audio_dur, video_dur)

    # 3. Assemble with audio mixing and ASS subtitles burn-in
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ass_escaped = str(captions_ass.absolute()).replace("\\", "/").replace(":", "\\:")

    vf_filters = [
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
        f"subtitles=filename='{ass_escaped}'"
    ]
    vf_str = ",".join(vf_filters)

    if bg_music.exists():
        print(f"    [Assemble] Adding background music ({bg_music.name}) with volume=0.15...")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(combined_video),
            "-i", str(voice_audio),
            "-stream_loop", "-1", "-i", str(bg_music),
            "-filter_complex",
            f"[0:v]{vf_str}[v];"
            f"[2:a]volume=0.15[bg];"
            f"[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-t", f"{final_dur:.3f}",
            str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(combined_video),
            "-i", str(voice_audio),
            "-vf", vf_str,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-t", f"{final_dur:.3f}",
            str(out_path),
        ]

    _run(cmd, "rendering final video with captions and mixed audio")
    return out_path
