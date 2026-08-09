import os
import re
import random
from pathlib import Path
import time
import concurrent.futures
import requests
from .config import PEXELS_API_KEYS

PEXELS_API = "https://api.pexels.com/videos/search"
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "56548904-dc4e2edcecb81ed1b459a2379")

# Stopwords to clean up queries for better stock video search
FILLER_WORDS = {"realistic", "cinematic", "artistic", "4k", "hd", "detailed", "high", "quality", "ultra", "dynamic", "depth", "macro", "background", "texture"}

def simplify_query(query: str) -> str:
    """Extract 1-3 core nouns/words by stripping prompt filler words."""
    words = [w.strip().lower() for w in re.split(r'[,\s]+', query) if w.strip()]
    cleaned = [w for w in words if w not in FILLER_WORDS]
    if not cleaned:
        cleaned = words
    # Take first 2-3 words for high-relevance search
    return " ".join(cleaned[:3])

def search_pexels_vertical(query: str, min_duration: float = 3.0, result_index: int = 0) -> str | None:
    for attempt_key in PEXELS_API_KEYS:
        try:
            r = requests.get(
                PEXELS_API,
                headers={"Authorization": attempt_key},
                params={"query": query, "orientation": "portrait", "per_page": 15, "size": "medium"},
                timeout=20,
            )
            if r.status_code == 200:
                videos = r.json().get("videos", [])
                if not videos:
                    # RULE 2: If query returned 0 videos, do NOT loop backup keys. Break early!
                    break
                matches = []
                for v in videos:
                    if v.get("duration", 0) < min_duration:
                        continue
                    files = [f for f in v.get("video_files", []) if f.get("width", 0) >= 1080 and f.get("height", 0) > f.get("width", 0)]
                    if not files:
                        continue
                    files.sort(key=lambda f: f.get("height", 0))
                    matches.append(files[0]["link"])
                
                if matches:
                    idx = min(result_index, len(matches) - 1)
                    return matches[idx]
                else:
                    break
        except Exception as e:
            print(f"      Pexels API error with key {attempt_key[:5]}... : {e}")
            continue
    return None

def search_pixabay_vertical(query: str, min_duration: float = 3.0, result_index: int = 0) -> str | None:
    try:
        r = requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": PIXABAY_KEY, "q": query, "per_page": 10, "safesearch": "true"},
            timeout=15,
        )
        if r.status_code == 200:
            hits = r.json().get("hits", [])
            matches = []
            for hit in hits:
                if hit.get("duration", 0) < min_duration:
                    continue
                videos = hit.get("videos", {})
                for vtype in ["medium", "small", "large"]:
                    if vtype in videos and videos[vtype].get("url"):
                        matches.append(videos[vtype]["url"])
                        break
            if matches:
                idx = min(result_index, len(matches) - 1)
                return matches[idx]
    except Exception as e:
        print(f"      Pixabay API error: {e}")
    return None

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

def _fetch_single_clip(i: int, j: int, q: str, varied_q: str, out_dir: Path) -> Path:
    t0 = time.time()
    clean_q = simplify_query(q)
    
    # 1. Try Pexels with clean query
    url = search_pexels_vertical(clean_q, result_index=j)
    
    # 2. Fallback to Pixabay if Pexels returned nothing
    if url is None:
        url = search_pixabay_vertical(clean_q, result_index=j)
        
    # 3. Try single core word on Pexels/Pixabay
    if url is None:
        single_word = clean_q.split()[0] if clean_q else "abstract"
        url = search_pexels_vertical(single_word, result_index=j) or search_pixabay_vertical(single_word, result_index=j)
        
    final_mp4 = out_dir / f"scene_{i:02d}_{j:02d}.mp4"
    if url is not None:
        download(url, final_mp4)
        print(f"      downloaded ({time.time()-t0:.0f}s) - scene {i+1} clip {j+1}")
        return final_mp4
    else:
        print(f"      Pexels & Pixabay failed, falling back to Pollinations AI for {q}")
        import subprocess
        try:
            from .visuals_ai import generate as ai_generate
        except ImportError:
            ai_generate = None
            
        img_path = out_dir / f"scene_{i:02d}_{j:02d}.jpg"
        rich_prompt = f"{q}, 4k resolution, cinematic, vertical"
        
        if ai_generate:
            ai_generate(rich_prompt, img_path)
        else:
            # Fallback direct Pollinations image download
            poll_url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(rich_prompt)}?width=1080&height=1920&nologo=true"
            r = requests.get(poll_url, timeout=30)
            with open(img_path, "wb") as f:
                f.write(r.content)
                
        # Convert image to 4-second MP4 via FFmpeg
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
            "-c:v", "libx264", "-t", "4", "-pix_fmt", "yuv420p",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            str(final_mp4)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return final_mp4

def fetch_all(scenes: list[dict], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = []

    for i, s in enumerate(scenes):
        q = s.get("visual_query", "abstract background")
        for j in range(2): # 2 clips per scene
            tasks.append((i, j, q, f"{q} {j}"))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_fetch_single_clip, i, j, q, vq, out_dir): (i, j)
            for i, j, q, vq in tasks
        }
        for future in concurrent.futures.as_completed(futures):
            ij = futures[future]
            try:
                path = future.result()
                results[ij] = path
            except Exception as e:
                print(f"      error fetching clip {ij}: {e}")

    # Return ordered list of paths
    paths = []
    for i in range(len(scenes)):
        for j in range(2):
            if (i, j) in results:
                paths.append(results[(i, j)])
    return paths
