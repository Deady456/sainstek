import random
from pathlib import Path
import time
import requests
from .config import PEXELS_API_KEYS

API = "https://api.pexels.com/videos/search"

_VARIATIONS = [
    "aerial view", "close up", "wide shot", "cinematic", "nature",
    "dark mood", "bright", "texture", "background", "abstract",
    "motion", "flowing", "detail", "macro", "slow motion",
    "dynamic", "realistic", "artistic", "depth", "pattern",
]


def search_vertical(query: str, min_duration: float = 3.0, result_index: int = 0) -> str | None:
    r = requests.get(
        API,
        headers={"Authorization": random.choice(PEXELS_API_KEYS)},
        params={"query": query, "orientation": "portrait", "per_page": 15, "size": "medium"},
        timeout=30,
    )
    r.raise_for_status()
    videos = r.json().get("videos", [])
    matches = []
    for v in videos:
        if v.get("duration", 0) < min_duration:
            continue
        files = [f for f in v["video_files"] if f.get("width", 0) >= 1080 and f.get("height", 0) > f.get("width", 0)]
        if not files:
            continue
        files.sort(key=lambda f: f.get("height", 0))
        matches.append(files[0]["link"])
    if not matches:
        return None
    idx = min(result_index, len(matches) - 1)
    return matches[idx]


def download(url: str, out_path: Path) -> Path:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        sz = int(r.headers.get("content-length", 0))
        with open(out_path, "wb") as f:
            downloaded = 0
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                downloaded += len(chunk)
                if sz:
                    pct = downloaded * 100 // sz
                    if pct % 25 == 0:
                        print(f"      downloading... {pct}%")
    return out_path


def fetch_for_scenes(scenes: list[dict], out_dir: Path, clips_per_scene: int = 2) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, scene in enumerate(scenes):
        q = scene["visual_query"]
        for j in range(clips_per_scene):
            variation = random.choice(_VARIATIONS)
            varied_q = f"{q} {variation}"
            print(f"    scene {i+1}/{len(scenes)} clip {j+1}: \"{varied_q}\"")
            t0 = time.time()
            url = search_vertical(varied_q, result_index=j)
            if url is None:
                url = search_vertical(q, result_index=j)
            if url is None:
                url = search_vertical("abstract background")
            final_mp4 = out_dir / f"scene_{i:02d}_{j:02d}.mp4"
            if url is not None:
                paths.append(download(url, final_mp4))
                print(f"      downloaded ({time.time()-t0:.0f}s)")
            else:
                print(f"      Pexels failed, falling back to Pollinations for {q}")
                import subprocess
                try:
                    from .visuals_ai import generate as ai_generate
                except ImportError:
                    ai_generate = None
                
                if ai_generate is None:
                    raise RuntimeError(f"No Pexels result for scene {i}: {q} and visuals_ai not found")
                
                img_path = out_dir / f"scene_{i:02d}_{j:02d}.jpg"
                rich_prompt = f"{q}, cinematic, detailed, 4K"
                ai_generate(rich_prompt, img_path)
                
                subprocess.run([
                    "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
                    "-c:v", "libx264", "-t", "10", "-pix_fmt", "yuv420p",
                    str(final_mp4)
                ], capture_output=True, check=True)
                
                paths.append(final_mp4)
                print(f"      fallback generated ({time.time()-t0:.0f}s)")
    return paths
