import json, subprocess
from pathlib import Path
from .config import CONFIG, ROOT

def _run(cmd: list[str], desc: str = ""):
    if desc:
        print(f"    ffmpeg: {desc}")
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        tail = (p.stderr or "")[-4000:]
        raise RuntimeError(f"Command failed (exit {p.returncode}): {cmd[0]} ...\n--- ffmpeg stderr ---\n{tail}")

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

def build(
    image_paths: list[Path],
    voice_audio: Path,
    captions_ass: Path,
    words: list[dict],
    scenes: list[dict],
    out_path: Path,
    work_dir: Path,
    hook_text: str = "",
    has_hook: bool = False,
) -> Path:
    v = CONFIG["video"]
    w, h, fps = v["width"], v["height"], v["fps"]
    work_dir.mkdir(parents=True, exist_ok=True)

    MAX_CLIP = 20

    def _zoom_expr(zs, ze, dur):
        n = int(dur * fps)
        inc = (ze - zs) / max(1, n - 1)
        return f"z='if(eq(on,1),{zs},min({ze},zoom+{inc:.6f}))':d={n}:s={w}x{h}:fps={fps}"

    durations = _scene_durations(words, scenes)
    
    # Ensure hook stays on screen for at least 3 seconds
    if has_hook and len(durations) > 1:
        target_hook_dur = 3.0
        if durations[0] < target_hook_dur:
            deficit = target_hook_dur - durations[0]
            durations[0] = target_hook_dur
            for i in range(1, len(durations)):
                if deficit <= 0:
                    break
                can_borrow = durations[i] - 1.0 # leave at least 1.0s for other scenes
                if can_borrow > 0:
                    borrow = min(deficit, can_borrow)
                    durations[i] -= borrow
                    deficit -= borrow
                    
    audio_dur = probe_duration(voice_audio)
    total_video = sum(durations)
    if total_video < audio_dur:
        extra = audio_dur - total_video + 1.0
        durations[-1] += extra
        print(f"    last scene extended +{extra:.1f}s to match audio")

    zoom_profiles = [
        (1.0, 1.06),    # slow zoom-in
        (1.04, 1.0),    # zoom-out
        (1.0, 1.0),     # static
    ]

    seg_files = []
    for i, (img, dur) in enumerate(zip(image_paths, durations)):
        n_clips = max(1, int(dur // MAX_CLIP))
        clip_dur = dur / n_clips
        for j in range(n_clips):
            z_in, z_out = zoom_profiles[j % len(zoom_profiles)]
            seg = work_dir / f"seg_{i:04d}_{j:02d}.mp4"
            n_frames = max(1, int(clip_dur * fps))
            _run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(img),
                "-vf", (
                    f"scale={w}:{h}:flags=lanczos:force_original_aspect_ratio=increase,"
                    f"crop={w}:{h},"
                    f"unsharp=5:5:0.6:3:3:0.3,"
                    f"zoompan=" + _zoom_expr(z_in, z_out, clip_dur)
                ),
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-t", f"{clip_dur:.3f}",
                str(seg),
            ], f"scene {i+1}/{len(image_paths)} clip {j+1}/{n_clips} ({z_in}->{z_out})")
            seg_files.append(seg)

    concat_list = work_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{seg.name}'" for seg in seg_files), encoding="utf-8")

    combined = work_dir / "combined.mp4"
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy",
        str(combined),
    ], "concat scenes")

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

    bg_music = ROOT / "assets" / "bg.mp3"
    cmd = ["ffmpeg", "-y", "-i", str(combined), "-i", str(voice_audio)]
    if bg_music.exists():
        cmd.extend(["-stream_loop", "-1", "-i", str(bg_music)])
        audio_filter = "[1:a]volume=1.0[v];[2:a]volume=0.15[bg];[v][bg]amix=inputs=2:duration=first:dropout_transition=2[a]"
        if vf_chain:
            cmd.extend(["-filter_complex", f"[0:v]{vf_chain}[vout];{audio_filter}", "-map", "[vout]", "-map", "[a]"])
        else:
            cmd.extend(["-filter_complex", audio_filter, "-map", "0:v", "-map", "[a]"])
    else:
        if vf_chain:
            cmd.extend(["-vf", vf_chain])
            
    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-shortest",
        str(out_path),
    ])
    _run(cmd, "final render (video+audio+captions)")
    return out_path
