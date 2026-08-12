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
    headers = {"User-Agent": "AntigravityBot/1.0 (admin@example.com)"}
    with requests.get(url, stream=True, headers=headers, timeout=120) as r:
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

def search_wikipedia_image(name: str) -> str | None:
    encoded_name = requests.utils.quote(name)
    # 1. Try exact match first
    endpoints = [
        f"https://id.wikipedia.org/w/api.php?action=query&prop=pageimages&titles={encoded_name}&format=json&pithumbsize=1000",
        f"https://en.wikipedia.org/w/api.php?action=query&prop=pageimages&titles={encoded_name}&format=json&pithumbsize=1000"
    ]
    for url in endpoints:
        try:
            r = requests.get(url, headers={"User-Agent": "AntigravityBot/1.0 (admin@example.com)"}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                pages = data.get("query", {}).get("pages", {})
                for page_id, page_data in pages.items():
                    if page_id != "-1" and "thumbnail" in page_data:
                        return page_data["thumbnail"]["source"]
        except Exception as e:
            print(f"      Wikipedia exact match error: {e}")
            
    # 2. Try fuzzy search if exact match fails
    search_endpoints = [
        f"https://id.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_name}&format=json",
        f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_name}&format=json"
    ]
    for url in search_endpoints:
        try:
            r = requests.get(url, headers={"User-Agent": "AntigravityBot/1.0 (admin@example.com)"}, timeout=15)
            if r.status_code == 200:
                search_data = r.json()
                results = search_data.get("query", {}).get("search", [])
                if results:
                    best_title = results[0]["title"]
                    # Fetch image for this title
                    img_url = f"https://{url.split('/')[2]}/w/api.php?action=query&prop=pageimages&titles={requests.utils.quote(best_title)}&format=json&pithumbsize=1000"
                    r_img = requests.get(img_url, headers={"User-Agent": "AntigravityBot/1.0 (admin@example.com)"}, timeout=15)
                    if r_img.status_code == 200:
                        img_data = r_img.json()
                        pages = img_data.get("query", {}).get("pages", {})
                        for page_id, page_data in pages.items():
                            if page_id != "-1" and "thumbnail" in page_data:
                                return page_data["thumbnail"]["source"]
        except Exception as e:
            print(f"      Wikipedia search error: {e}")
            
    return None

def search_pixabay_photo(query: str, result_index: int = 0) -> str | None:
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={"key": PIXABAY_KEY, "q": query, "image_type": "photo", "per_page": 10, "safesearch": "true"},
            timeout=15,
        )
        if r.status_code == 200:
            hits = r.json().get("hits", [])
            matches = []
            for hit in hits:
                # Get the highest resolution image available
                if "no_largeImageURL" in hit:
                    matches.append(hit["no_largeImageURL"])
                elif "webformatURL" in hit:
                    matches.append(hit["webformatURL"])
            
            if matches:
                idx = min(result_index, len(matches) - 1)
                return matches[idx]
    except Exception as e:
        print(f"      Pixabay Photo API error: {e}")
    return None

def _fetch_single_clip(i: int, j: int, scene: dict, varied_q: str, out_dir: Path) -> Path:
    t0 = time.time()
    q = scene.get("visual_query", "abstract background")
    clean_q = simplify_query(q)
    final_mp4 = out_dir / f"scene_{i:02d}_{j:02d}.mp4"
    
    # 0. Always try Wikipedia first if factual_subject is present
    factual_subject = scene.get("factual_subject")
    if factual_subject and str(factual_subject).lower() != "null":
        # Modify query slightly if it's the second clip for the same scene to avoid same image
        search_term = factual_subject if j == 0 else f"{factual_subject} detail"
        wiki_url = search_wikipedia_image(search_term)
        if wiki_url:
            print(f"      found Wikipedia photo for {search_term}: {wiki_url[:50]}...")
            img_path = out_dir / f"scene_{i:02d}_{j:02d}_wiki.jpg"
            
            try:
                download(wiki_url, img_path)
                import subprocess
                subprocess.run([
                    "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
                    "-lavfi", "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,boxblur=20:20[bg];[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2",
                    "-c:v", "libx264", "-t", "4", "-pix_fmt", "yuv420p",
                    str(final_mp4)
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return final_mp4
            except Exception as e:
                print(f"      fetch/ffmpeg failed for Wikipedia image {search_term}: {e}")

    # 1. Fallback to real photos from Pixabay (since user wants REAL sources)
    search_q = factual_subject if (factual_subject and str(factual_subject).lower() != "null") else clean_q
    photo_url = search_pixabay_photo(search_q, result_index=j)
    
    # 2. Try single word if full phrase fails
    if photo_url is None and search_q:
        single_word = search_q.split()[0]
        photo_url = search_pixabay_photo(single_word, result_index=j)
        
    if photo_url:
        print(f"      found Pixabay REAL PHOTO for {search_q}: {photo_url[:50]}...")
        img_path = out_dir / f"scene_{i:02d}_{j:02d}_pixabay.jpg"
        
        try:
            download(photo_url, img_path)
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
                "-lavfi", "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,boxblur=20:20[bg];[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2",
                "-c:v", "libx264", "-t", "4", "-pix_fmt", "yuv420p",
                str(final_mp4)
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return final_mp4
        except Exception as e:
            print(f"      fetch/ffmpeg failed for Pixabay photo {search_q}: {e}")

    # 3. Ultimate Fallback: Pexels stock video (real camera footage, NOT AI)
    print(f"      Wiki & Pixabay Photo failed, falling back to Pexels video for: {clean_q}")
    url = search_pexels_vertical(clean_q, result_index=j)
    if url is None:
        url = search_pixabay_vertical(clean_q, result_index=j)
    if url is None and clean_q:
        single_word = clean_q.split()[0]
        url = search_pexels_vertical(single_word, result_index=j) or search_pixabay_vertical(single_word, result_index=j)
        
    if url is not None:
        download(url, final_mp4)
        print(f"      downloaded video ({time.time()-t0:.0f}s) - scene {i+1} clip {j+1}")
        return final_mp4
        
    # 4. If everything fails, use a generic video so the pipeline doesn't crash
    # But absolutely DO NOT USE AI (Pollinations)
    print(f"      All real sources failed. Using generic nature fallback.")
    fallback_url = search_pexels_vertical("nature", result_index=random.randint(0, 5))
    if fallback_url:
         download(fallback_url, final_mp4)
         return final_mp4
         
    raise RuntimeError(f"Completely failed to find any real source visual for scene {i} clip {j}")

def fetch_all(scenes: list[dict], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = []

    for i, s in enumerate(scenes):
        q = s.get("visual_query", "abstract background")
        for j in range(2): # 2 clips per scene
            tasks.append((i, j, s, f"{q} {j}"))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_fetch_single_clip, i, j, s, vq, out_dir): (i, j)
            for i, j, s, vq in tasks
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


fetch_for_scenes = fetch_all
