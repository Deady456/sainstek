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
    hook_text: str = "",
    thumbnail_img: Path = None,
) -> Path:
    v = CONFIG["video"]
    w, h, fps = v["width"], v["height"], v["fps"]
    work_dir.mkdir(parents=True, exist_ok=True)

    durations = _scene_durations(words, scenes)

    if thumbnail_img and thumbnail_img.exists() and len(durations) > 0:
        deficit = 2.0
        for i in range(len(durations)):
            if deficit <= 0: break
            can_borrow = durations[i] - 1.0 # leave at least 1s
            if can_borrow > 0:
                borrow = min(deficit, can_borrow)
                durations[i] -= borrow
                deficit -= borrow

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
    
    if thumbnail_img and thumbnail_img.exists():
        thumb_out = work_dir / "prep_thumb.mp4"
        _run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(thumbnail_img),
            "-vf", (
                f"scale={w}:{h}:flags=lanczos:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},"
                f"unsharp=5:5:0.6:3:3:0.3,"
                f"zoompan=z='if(eq(on,1),1.0,min(1.06,zoom+0.0005))':d={int(2.0*fps)}:s={w}x{h}:fps={fps}"
            ),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-t", "2.0",
            str(thumb_out)
        ], "thumbnail prep (2s)")
        prepped.append(thumb_out)
        durations.insert(0, 2.0)
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

    # Build video filter chain: optional hook_text ASS + subtitles
    vf_parts = []
    hook_cfg = CONFIG.get("hook_text", {})
    if hook_text and hook_cfg.get("enabled", False):
        import random
        palettes = ["&H00FFFF&", "&HFFFFFF&", "&H00FF00&", "&HFFFF00&", "&HFF00FF&", "&H0080FF&"]
        c1, c2, c3 = random.sample(palettes, 3)
        hw = hook_text.split()
        if len(hw) >= 3:
            third = len(hw) // 3
            l1 = " ".join(hw[:third])
            l2 = " ".join(hw[third:2*third])
            l3 = " ".join(hw[2*third:])
        elif len(hw) == 2:
            l1, l2, l3 = hw[0], hw[1], ""
        else:
            l1, l2, l3 = hook_text, "", ""
            
        ht_dur = float(hook_cfg.get("duration", 3.0))
        def fmt_time(sec):
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = int(sec % 60)
            cs = int((sec % 1) * 100)
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        # Generate shaking text for the first 0.5 seconds
        shake_dur = min(0.5, ht_dur)
        frames = int(shake_dur * 30)
        events = []
        if frames > 0:
            frame_len = shake_dur / frames
            for i in range(frames):
                st = i * frame_len
                en = (i + 1) * frame_len
                
                # Ease-out progress
                p = st / shake_dur
                ease_out = 1 - (1 - p) ** 3
                
                # Fade in (Alpha FF to 00)
                alpha_val = int(255 * (1 - ease_out))
                alpha_tag = f"\\alpha&H{alpha_val:02X}&"
                
                # Slide from left to center
                x_center = int(-300 + (840) * ease_out)
                
                dx = random.randint(-20, 20)
                dy = random.randint(-20, 20)
                pos = f"{{\\pos({x_center+dx},{600+dy}){alpha_tag}}}"
                styled = f"{pos}{{\\c{c1}}}{l1}"
                if l2: styled += f"\\N{{\\c{c2}}}{l2}"
                if l3: styled += f"\\N{{\\c{c3}}}{l3}"
                events.append(f"Dialogue: 0,{fmt_time(st)},{fmt_time(en)},HookText,,0,0,0,,{styled}")
        
        # Static text for the rest of the duration
        if ht_dur > shake_dur:
            pos = f"{{\\pos(540,600)}}"
            styled = f"{pos}{{\\c{c1}}}{l1}"
            if l2: styled += f"\\N{{\\c{c2}}}{l2}"
            if l3: styled += f"\\N{{\\c{c3}}}{l3}"
            events.append(f"Dialogue: 0,{fmt_time(shake_dur)},{fmt_time(ht_dur)},HookText,,0,0,0,,{styled}")

        events_str = "\n".join(events)

        hook_ass = work_dir / "hook.ass"
        ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HookText,Impact,130,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,12,0,5,10,10,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{events_str}
"""
        with open(hook_ass, "w", encoding="utf-8") as f:
            f.write(ass_content)

        hook_ass_arg = str(hook_ass).replace("\\", "/").replace(":", "\\:")
        vf_parts.append(f"subtitles='{hook_ass_arg}':fontsdir='{fonts_arg}'")
    vf_parts.append(f"subtitles='{ass_arg}':fontsdir='{fonts_arg}'")
    vf_chain = ",".join(vf_parts)

    _run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(voice_audio),
        "-vf", vf_chain,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_path),
    ], "final render (video+audio+captions)")
    return out_path


