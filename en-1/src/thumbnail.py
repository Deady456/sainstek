from pathlib import Path
import random
from PIL import Image, ImageDraw, ImageFont

THUMB_W, THUMB_H = 1280, 720
_COLORS = [
    ["#667eea", "#764ba2"], ["#f093fb", "#f5576c"],
    ["#4facfe", "#00f2fe"], ["#43e97b", "#38f9d7"],
    ["#fa709a", "#fee140"], ["#a18cd1", "#fbc2eb"],
    ["#fccb90", "#d57eeb"], ["#e0c3fc", "#8ec5fc"],
    ["#30cfd0", "#330867"],
]

def _gradient(w, h, colors):
    img = Image.new("RGB", (w, h))
    pix = img.load()
    n = len(colors) - 1
    for y in range(h):
        ratio = y / h
        idx = min(int(ratio * n), n - 1)
        local_r = (ratio * n) - idx
        c1 = colors[idx]
        c2 = colors[min(idx + 1, n)]
        r = int(c1[0] + (c2[0] - c1[0]) * local_r)
        g = int(c1[1] + (c2[1] - c1[1]) * local_r)
        b = int(c1[2] + (c2[2] - c1[2]) * local_r)
        for x in range(w):
            pix[x, y] = (r, g, b)
    return img

def _load_font(size: int) -> ImageFont:
    for name in ["arialbd.ttf", "DejaVuSans-Bold.ttf", "NotoSans-Bold.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except (IOError, OSError):
            pass
    return ImageFont.load_default()

def generate(title: str, out_path: Path, bg_path: Path | None = None) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if bg_path and bg_path.exists():
        try:
            bg = Image.open(bg_path).convert("RGB")
            bg = bg.resize((THUMB_W, THUMB_H), Image.LANCZOS)
        except Exception:
            bg = _gradient(THUMB_W, THUMB_H, random.choice(_COLORS))
    else:
        bg = _gradient(THUMB_W, THUMB_H, random.choice(_COLORS))

    draw = ImageDraw.Draw(bg)
    overlay = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle([0, THUMB_H // 2, THUMB_W, THUMB_H], fill=(0, 0, 0, 140))
    bg.paste(overlay, (0, 0), overlay)

    font_size = 56
    font = _load_font(font_size)
    lines = []
    words = title.split()
    current = ""
    for w in words:
        test = (current + " " + w).strip()
        lw = font.getlength(test) if hasattr(font, "getlength") else font.getsize(test)[0]
        if lw < THUMB_W - 80 and len(current.split()) < 6:
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    if len(lines) > 3:
        lines = lines[:3]
        lines[-1] += "..."

    start_y = THUMB_H // 2 + 30
    for i, l in enumerate(lines):
        tw = font.getlength(l) if hasattr(font, "getlength") else font.getsize(l)[0]
        x = (THUMB_W - tw) // 2
        y = start_y + i * 68
        draw.text((x + 3, y + 3), l, font=font, fill=(0, 0, 0, 160))
        draw.text((x, y), l, font=font, fill=(255, 255, 255))

    img = bg.convert("RGB")
    img.save(out_path, quality=92)
    print(f"    thumbnail saved ({out_path.stat().st_size//1024} KB)")
    return out_path

def upload(yt_service, video_id: str, thumb_path: Path):
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(str(thumb_path), mimetype="image/jpeg")
    yt_service.thumbnails().set(videoId=video_id, media_body=media).execute()
    print(f"    thumbnail uploaded for video {video_id}")
