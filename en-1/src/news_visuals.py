import re
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from .config import CONFIG


def _fetch_og_image(url: str) -> str | None:
    """Extract og:image from a news article page."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for meta in soup.find_all("meta"):
            if meta.get("property") == "og:image" or meta.get("name") == "twitter:image":
                content = meta.get("content", "")
                if content:
                    return content
        # Fallback: first img in article
        img = soup.find("article").find("img") if soup.find("article") else soup.find("img")
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                from urllib.parse import urlparse
                base = urlparse(url).scheme + "://" + urlparse(url).netloc
                src = base + src
            return src
    except Exception:
        pass
    return None


def _search_news_images(query: str, max_results: int = 3) -> list[str]:
    """Search Google News for images matching query."""
    urls = []
    # Try Google News RSS
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(rss_url, headers=headers, timeout=15)
        r.raise_for_status()
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.content)
        for item in root.findall(".//item"):
            link = item.findtext("link", "")
            if link:
                # Google News links are wrapped
                match = re.search(r'url=([^&]+)', link)
                if match:
                    from urllib.parse import unquote
                    link = unquote(match.group(1))
                urls.append(link)
    except Exception:
        pass
    return urls[:max_results]


def fetch_for_scenes(scenes: list[dict], out_dir: Path) -> list[Path]:
    """Fetch news images and create video clips with Ken Burns effect."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    v = CONFIG["video"]
    w, h, fps = v["width"], v["height"], v["fps"]

    for i, scene in enumerate(scenes):
        q = scene["visual_query"]
        out_path = out_dir / f"scene_{i:02d}.mp4"
        print(f"    scene {i+1}/{len(scenes)}: \"{q}\"")

        img_url = None
        t0 = time.time()
        article_urls = _search_news_images(q)
        for article_url in article_urls:
            img_url = _fetch_og_image(article_url)
            if img_url:
                print(f"      found image: {img_url[:80]}...")
                break

        if not img_url:
            # Fallback: try inline image search
            print(f"      no news image found, trying fallback...")
            search_url = f"https://www.google.com/search?tbm=isch&q={q}&hl=id"
            img_url = _fallback_image(search_url)

        if img_url:
            img_path = out_dir / f"img_{i:02d}.jpg"
            _download_image(img_url, img_path)
            _image_to_video(img_path, out_path, scene.get("duration", 5.0), w, h, fps)
            print(f"      downloaded ({time.time()-t0:.0f}s)")
        else:
            # Ultimate fallback: colored background
            print(f"      no image found, using fallback color")
            _fallback_video(out_path, scene.get("duration", 5.0), w, h, fps)
            print(f"      fallback created ({time.time()-t0:.0f}s)")

        paths.append(out_path)
    return paths


def _fallback_image(search_url: str) -> str | None:
    """Fallback: try to get first image from Google Images search."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
        # Extract first image URL from raw HTML
        matches = re.findall(r'src="(https://[^"]+\.(?:jpg|jpeg|png|webp))"', r.text)
        for m in matches:
            if "gstatic" not in m and "google" not in m:
                return m
    except Exception:
        pass
    return None


def _download_image(url: str, out_path: Path):
    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.get(url, headers=headers, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def _image_to_video(img_path: Path, out_path: Path, duration: float, w: int, h: int, fps: int):
    """Create a video clip from a static image with Ken Burns slow zoom."""
    import subprocess
    frames = int(duration * fps)
    zoom_rate = 0.015  # slow zoom
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
        "-vf",
        f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}:exact=1,"
        f"zoompan=z='if(eq(on,1),1,min(1.3,zoom+{zoom_rate}))':"
        f"d={frames}:"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"s={w}x{h}:fps={fps}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-t", f"{duration:.3f}",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True)


def _fallback_video(out_path: Path, duration: float, w: int, h: int, fps: int):
    """Create a colored background as ultimate fallback."""
    import subprocess
    color = "#1a1a2e"  # dark blue
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:r={fps}:d={duration:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True)
