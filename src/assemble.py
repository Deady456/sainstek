import json
import subprocess
from pathlib import Path
from .config import CONFIG, ROOT


def _run(cmd: list[str], desc: str = ""):
    if desc:
        print(f"    ffmpeg: {desc}")
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        tail = (p.stderr or "")[-4000:]
        raise RuntimeError(
            f"Command failed (exit {p.returncode}): {cmd[0]} ...\n--- ffmpeg stderr ---\n{tail}"
        )


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def _scene_durations(words: list[dict], scenes: list[dict]) -> list[float]:
    spoken = [s["text"].lower() for s in scenes]
    flat = [w["word"].strip().lower().strip(".,!?;:\"'") for w in words]
    durations = []
    cursor = 0
    for i, sentence in enumerate(spoken):
        scene_words = [w.strip(".,!?;:\"'") for w in sentence.split()]
        start_idx = cursor
        end_idx = min(cursor + len(scene_words), len(words))
        if i == len(spoken) - 1:
            end_idx = len(words)
        start_t = words[start_idx]["start"] if start_idx < len(words) else words[-1]["end"]
        end_t = words[end_idx - 1]["end"] if end_idx > 0 else start_t
        durations.append(max(0.5, end_t - start_t))
        cursor = end_idx
    return durations


def _prep_scene_clip(src: Path, target_dur: float, out_path: Path, w: int, h: int, fps: int):
    src_dur = probe_duration(src)
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},setsar=1,fps={fps}"
    )
    if src_dur >= target_dur:
        _run([
            "ffmpeg", "-y", "-ss", "0", "-t", f"{target_dur:.3f}", "-i", str(src),
            "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", str(out_path),
        ])
    else:
        loops = int(target_dur // src_dur) + 1
        _run([
            "ffmpeg", "-y", "-stream_loop", str(loops), "-i", str(src),
            "-t", f"{target_dur:.3f}", "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", str(out_path),
        ])


def _assemble_with_transitions(prepped: list[Path], durations: list[float],
                                out_path: Path, w: int, h: int, fps: int,
                                trans_dur: float = 0.3, fade_dur: float = 0.4):
    """Concatenate clips with xfade transitions + fade in/out."""
    n = len(prepped)
    if n == 1:
        out_start = max(0, durations[0] - fade_dur)
        vf = f"fade=t=in:st=0:d={fade_dur},fade=t=out:st={out_start:.3f}:d={fade_dur}"
        _run([
            "ffmpeg", "-y", "-i", str(prepped[0]),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(out_path),
        ], "fade in/out (single clip)")
        return

    # Build xfade filtergraph
    trans_type = "fade"
    cum = [sum(durations[:i+1]) for i in range(n)]
    total_out = cum[-1] - trans_dur * (n - 1)

    parts = []
    # setpts for each input
    for i in range(n):
        parts.append(f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[v{i}]")

    # chain xfade transitions
    prev = None
    for i in range(n - 1):
        offset = cum[i] - trans_dur * (i + 1)
        if prev is None:
            parts.append(f"[v{i}][v{i+1}]xfade=transition={trans_type}:duration={trans_dur:.3f}:offset={offset:.3f}[t{i}]")
            prev = f"t{i}"
        else:
            parts.append(f"[{prev}][v{i+1}]xfade=transition={trans_type}:duration={trans_dur:.3f}:offset={offset:.3f}[t{i}]")
            prev = f"t{i}"

    # fade in/out on the final composed stream
    out_start = max(0, total_out - fade_dur)
    parts.append(f"[{prev}]fade=t=in:st=0:d={fade_dur},fade=t=out:st={out_start:.3f}:d={fade_dur}[out]")

    filter_complex = ";".join(parts)

    cmd = ["ffmpeg", "-y"]
    for p in prepped:
        cmd.extend(["-i", str(p)])
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ])
    _run(cmd, f"xfade transitions ({trans_type}, {trans_dur}s) + fade in/out")


def build(
    scene_videos: list[Path],
    voice_audio: Path,
    captions_ass: Path,
    words: list[dict],
    scenes: list[dict],
    out_path: Path,
    work_dir: Path,
    videos_per_scene: int = 1,
) -> Path:
    v = CONFIG["video"]
    w, h, fps = v["width"], v["height"], v["fps"]
    work_dir.mkdir(parents=True, exist_ok=True)

    durations = _scene_durations(words, scenes)

    # Expand durations when multiple clips per scene
    if videos_per_scene > 1:
        expanded = []
        for d in durations:
            part = d / videos_per_scene
            expanded.extend([part] * videos_per_scene)
        durations = expanded

    # Ensure total video covers full audio (Whisper timestamps may undershoot)
    audio_dur = probe_duration(voice_audio)
    total_video = sum(durations)
    if total_video < audio_dur:
        extra = audio_dur - total_video + 1.0
        durations[-1] += extra
        print(f"    last scene extended +{extra:.1f}s to match audio")

    prepped = []
    for i, (src, dur) in enumerate(zip(scene_videos, durations)):
        out = work_dir / f"prep_{i:02d}.mp4"
        _prep_scene_clip(src, dur, out, w, h, fps)
        prepped.append(out)

    silent = work_dir / "silent.mp4"
    _assemble_with_transitions(prepped, durations, silent, w, h, fps)

    video_dur = probe_duration(silent)
    print(f"    video={video_dur:.1f}s audio={audio_dur:.1f}s")

    if video_dur < audio_dur + 0.5:
        pad = work_dir / "padded.mp4"
        extra = audio_dur - video_dur + 1.5
        print(f"    padding video +{extra:.1f}s (audio breather)")
        _run([
            "ffmpeg", "-y", "-i", str(silent),
            "-vf", f"tpad=stop_mode=clone:stop_duration={extra:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", str(pad),
        ], "pad last frame")
        silent = pad

    ass_arg = str(captions_ass).replace("\\", "/").replace(":", "\\:")
    fonts_arg = str(ROOT / "assets" / "fonts").replace("\\", "/").replace(":", "\\:")
    _run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(voice_audio),
        "-vf", f"subtitles='{ass_arg}':fontsdir='{fonts_arg}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_path),
    ], "final render (video+audio+captions)")
    return out_path
