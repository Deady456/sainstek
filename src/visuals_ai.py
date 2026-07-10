import requests, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/"
COLORS = [
    ["#667eea", "#764ba2"], ["#f093fb", "#f5576c"],
    ["#4facfe", "#00f2fe"], ["#43e97b", "#38f9d7"],
    ["#fa709a", "#fee140"], ["#a18cd1", "#fbc2eb"],
    ["#fccb90", "#d57eeb"], ["#e0c3fc", "#8ec5fc"],
    ["#f5576c", "#ff6f91"], ["#30cfd0", "#330867"],
]

def _parse_hex(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)

def _gradient(w, h, colors):
    img = Image.new("RGB", (w, h))
    pix = img.load()
    n = len(colors) - 1
    colors_rgb = [_parse_hex(c) for c in colors]
    for y in range(h):
        ratio = y / h
        idx = min(int(ratio * n), n - 1)
        local_r = (ratio * n) - idx
        c1 = colors_rgb[idx]
        c2 = colors_rgb[min(idx + 1, n)]
        r = int(c1[0] + (c2[0] - c1[0]) * local_r)
        g = int(c1[1] + (c2[1] - c1[1]) * local_r)
        b = int(c1[2] + (c2[2] - c1[2]) * local_r)
        for x in range(w):
            pix[x, y] = (r, g, b)
    return img

def _add_decorations(draw, w, h):
    for _ in range(5):
        cx = random.randint(0, w)
        cy = random.randint(0, h)
        r = random.randint(80, 350)
        for i in range(r, 0, -20):
            alpha = max(0, min(255, int(30 * (1 - i / r))))
            draw.ellipse([cx - i, cy - i, cx + i, cy + i],
                        outline=(255, 255, 255, alpha))

def _generate_fallback(prompt: str, out_path: Path, width=1080, height=1920):
    colors = random.choice(COLORS)
    img = _gradient(width, height, colors)
    draw = ImageDraw.Draw(img)
    _add_decorations(draw, width, height)

    try:
        font = ImageFont.truetype("arialbd.ttf", 64)
        font2 = ImageFont.truetype("arial.ttf", 32)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
            font2 = ImageFont.truetype("DejaVuSans.ttf", 32)
        except (IOError, OSError):
            font = ImageFont.load_default()
            font2 = font

    words = prompt.split()
    lines = []
    current = ""
    for w in words:
        test = (current + " " + w).strip()
        lw = font.getlength(test) if hasattr(font, "getlength") else font.getsize(test)[0]
        if lw < width - 160:
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)

    total_h = len(lines) * 80
    start_y = (height - total_h) // 2 - 40

    for i, l in enumerate(lines):
        tw = font.getlength(l) if hasattr(font, "getlength") else font.getsize(l)[0]
        x = (width - tw) // 2
        y = start_y + i * 80
        draw.text((x + 2, y + 2), l, font=font, fill=(0, 0, 0, 80))
        draw.text((x, y), l, font=font, fill=(255, 255, 255))

    img.save(out_path, quality=92)

def generate(prompt: str, out_path: Path, width=1080, height=1920) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{POLLINATIONS_URL}{requests.utils.quote(prompt)}?width={width}&height={height}&nologo=true"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 1000:
                out_path.write_bytes(resp.content)
                return out_path
        except requests.RequestException:
            pass
    _generate_fallback(prompt, out_path, width, height)
    return out_path
