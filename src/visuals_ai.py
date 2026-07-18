import requests, random, os
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

def draw_text_with_outline(draw, x, y, text, font, text_color, outline_color, shadow_color):
    shadow_offset = 15
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color)
    
    stroke_width = 8
    for adj_x in range(-stroke_width, stroke_width + 1, 2):
        for adj_y in range(-stroke_width, stroke_width + 1, 2):
            draw.text((x + adj_x, y + adj_y), text, font=font, fill=outline_color)
            
    draw.text((x, y), text, font=font, fill=text_color)

def _apply_hook_text(img_path: Path, hook_text: str, width: int, height: int):
    try:
        img = Image.open(img_path).convert("RGBA")
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        
        # Load Bevan font exclusively
        cwd = os.getcwd()
        font_paths = [
            os.path.join(cwd, "Bevan.ttf")
        ]
        
        # Try to find an existing font
        chosen_font = None
        random.shuffle(font_paths)
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    chosen_font = ImageFont.truetype(fp, 85)
                    break
                except:
                    pass
        if not chosen_font:
            try:
                chosen_font = ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", 85)
            except:
                chosen_font = ImageFont.load_default()
                
        colors = [
            (255, 255, 0, 255),   # Yellow
            (0, 255, 255, 255),   # Cyan
            (255, 100, 100, 255), # Light Red/Pink
            (100, 255, 100, 255), # Light Green
            (255, 255, 255, 255), # White
            (255, 150, 0, 255)    # Orange
        ]
        random_color = random.choice(colors)
        
        words = hook_text.split()
        lines = []
        current_line = []
        max_width = 800
        
        for word in words:
            test_line = " ".join(current_line + [word])
            tw = draw.textlength(test_line, font=chosen_font) if hasattr(draw, "textlength") else chosen_font.getsize(test_line)[0]
            if tw > max_width:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
            else:
                current_line.append(word)
                
        if current_line:
            lines.append(" ".join(current_line))
            
        line_spacing = 45

        # Measure each line height to vertically center the block
        line_heights = []
        for line in lines:
            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), line, font=chosen_font)
                lh = bbox[3] - bbox[1]
            else:
                lh = chosen_font.getsize(line)[1]
            line_heights.append(lh)

        total_h = sum(line_heights) + line_spacing * (len(lines) - 1)
        y = (height - total_h) // 2

        for i, line in enumerate(lines):
            tw = draw.textlength(line, font=chosen_font) if hasattr(draw, "textlength") else chosen_font.getsize(line)[0]
            x = (width - tw) // 2
            line_height = line_heights[i]

            draw_text_with_outline(
                draw, x, y, line, chosen_font,
                text_color=random_color,
                outline_color=(0, 0, 0, 255),
                shadow_color=(0, 0, 0, 150)
            )
            y += line_height + line_spacing
            
        img = img.convert("RGB")
        img.save(img_path, quality=95)
    except Exception as e:
        print(f"Failed to apply hook text: {e}")

def generate(prompt: str, out_path: Path, width=1080, height=1920, hook_text: str = None) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{POLLINATIONS_URL}{requests.utils.quote(prompt)}?width={width}&height={height}&nologo=true"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 1000:
                out_path.write_bytes(resp.content)
                if hook_text:
                    _apply_hook_text(out_path, hook_text, width, height)
                return out_path
        except requests.RequestException:
            pass
    _generate_fallback(prompt, out_path, width, height)
    if hook_text:
        _apply_hook_text(out_path, hook_text, width, height)
    return out_path
