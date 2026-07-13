"""
Branding layer: intro, outro, and watermark.

Adds professional branding to videos for better channel identity.
"""
import random
import re
import subprocess
from pathlib import Path
from .config import CONFIG, ROOT


def _get_branding_config() -> dict:
    return CONFIG.get("branding", {})


def add_intro(video_path: Path, output_path: Path) -> Path:
    """Prepend intro video to the main video."""
    cfg = _get_branding_config().get("intro", {})
    if not cfg.get("enabled", False):
        return video_path

    intro_path = ROOT / cfg["path"]
    if not intro_path.exists():
        print(f"    branding: intro not found at {intro_path}, skipping")
        return video_path

    duration = cfg.get("duration", 2.5)
    print(f"    branding: adding intro ({duration}s)")

    # Concat intro + main video
    concat_list = output_path.parent / "concat_intro.txt"
    concat_list.write_text(
        f"file '{intro_path}'\nfile '{video_path}'\n",
        encoding="utf-8",
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    concat_list.unlink(missing_ok=True)

    if p.returncode != 0:
        print(f"    branding: intro concat failed, using original")
        return video_path

    return output_path


def add_outro(video_path: Path, output_path: Path, cta_text: str = "") -> Path:
    """Append outro video to the main video."""
    cfg = _get_branding_config().get("outro", {})
    if not cfg.get("enabled", False):
        return video_path

    outro_path = ROOT / cfg["path"]
    if not outro_path.exists():
        print(f"    branding: outro not found at {outro_path}, skipping")
        return video_path

    print(f"    branding: adding outro ({cfg.get('duration', 3.0)}s)")

    # Concat main video + outro
    concat_list = output_path.parent / "concat_outro.txt"
    concat_list.write_text(
        f"file '{video_path}'\nfile '{outro_path}'\n",
        encoding="utf-8",
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    concat_list.unlink(missing_ok=True)

    if p.returncode != 0:
        print(f"    branding: outro concat failed, using original")
        return video_path

    return output_path


def add_watermark(video_path: Path, output_path: Path) -> Path:
    """Overlay watermark image on video."""
    cfg = _get_branding_config().get("watermark", {})
    if not cfg.get("enabled", False):
        return video_path

    wm_path = ROOT / cfg["path"]
    if not wm_path.exists():
        print(f"    branding: watermark not found at {wm_path}, skipping")
        return video_path

    position = cfg.get("position", "top_right")
    opacity = cfg.get("opacity", 0.4)
    size = cfg.get("size", 80)

    import random
    x_offset = random.randint(-200, 200)

    # Position mapping
    pos_map = {
        "top_right": f"main_w-{size}-20:20",
        "top_left": f"20:20",
        "bottom_right": f"main_w-{size}-20:main_h-{size}-20",
        "bottom_left": f"20:main_h-{size}-20",
        "center": f"(main_w-{size})/2+{x_offset}:(main_h*0.20)",
    }
    overlay_pos = pos_map.get(position, pos_map["top_right"])

    print(f"    branding: adding watermark ({position}, {opacity*100:.0f}%)")

    vf = (
        f"[1:v]scale={size}:-1:force_original_aspect_ratio=decrease,"
        f"format=rgba,colorchannelmixer=aa={opacity}[wm];"
        f"[0:v][wm]overlay={overlay_pos}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(wm_path),
        "-filter_complex", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"    branding: watermark failed: {p.stderr[-300:]}")
        return video_path

    return output_path


def apply_all(video_path: Path, work_dir: Path) -> Path:
    """Apply all branding (intro, outro, watermark) to video."""
    cfg = _get_branding_config()
    if not cfg.get("enabled", False):
        return video_path

    brand_dir = work_dir / "branding"
    brand_dir.mkdir(parents=True, exist_ok=True)

    current = video_path

    # Intro
    if cfg.get("intro", {}).get("enabled", False):
        out = brand_dir / "with_intro.mp4"
        current = add_intro(current, out)

    # Watermark
    if cfg.get("watermark", {}).get("enabled", False):
        out = brand_dir / "with_watermark.mp4"
        current = add_watermark(current, out)

    # Outro
    if cfg.get("outro", {}).get("enabled", False):
        out = brand_dir / "with_outro.mp4"
        cta = cfg.get("outro", {}).get("cta_text", "")
        current = add_outro(current, out, cta)

    return current
