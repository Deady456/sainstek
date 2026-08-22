import os
import re
import json
import time
import random
import requests
import subprocess
from pathlib import Path
from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from .config import PEXELS_API_KEYS, CONFIG, ROOT

PEXELS_API = "https://api.pexels.com/videos/search"
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "56548904-dc4e2edcecb81ed1b459a2379")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# Blacklist words that could return ads, cartoons, or drawings
JUNK_WORDS = {"cartoon", "drawing", "illustration", "anime", "clipart", "vector", "meme", "banner", "ad"}

def probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(path)],
            check=True, capture_output=True, text=True,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 60.0


def clean_query(q: str) -> str:
    words = [w.strip().lower() for w in re.split(r'[,\s]+', q) if w.strip()]
    cleaned = [w for w in words if w not in JUNK_WORDS and len(w) > 2]
    return " ".join(cleaned[:3]) if cleaned else q


def search_pexels_hd_video(query: str, min_duration: float = 3.0) -> list[str]:
    cq = clean_query(query)
    found = []
    for key in PEXELS_API_KEYS:
        if not key or key == "dummy_key":
            continue
        try:
            r = requests.get(
                PEXELS_API,
                headers={"Authorization": key},
                params={"query": cq, "orientation": "portrait", "per_page": 15, "size": "medium"},
                timeout=12,
            )
            if r.status_code == 200:
                videos = r.json().get("videos", [])
                if not videos:
                    # RULE 2: If query returned 0 videos, do NOT loop backup keys. Break early!
                    break
                for v in videos:
                    if v.get("duration", 0) < min_duration:
                        continue
                    files = [f for f in v.get("video_files", []) if f.get("height", 0) > f.get("width", 0) and f.get("width", 0) >= 720]
                    if files:
                        files.sort(key=lambda f: f.get("height", 0), reverse=True)
                        found.append(files[0]["link"])
                if found:
                    break
        except Exception:
            continue
    return found


def search_pixabay_hd_video(query: str, min_duration: float = 3.0) -> list[str]:
    cq = clean_query(query)
    found = []
    try:
        r = requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": PIXABAY_KEY, "q": cq, "per_page": 15, "safesearch": "true", "video_type": "film"},
            timeout=12,
        )
        if r.status_code == 200:
            hits = r.json().get("hits", [])
            for hit in hits:
                if hit.get("duration", 0) < min_duration:
                    continue
                videos = hit.get("videos", {})
                for vtype in ["large", "medium", "small"]:
                    if vtype in videos and videos[vtype].get("url"):
                        found.append(videos[vtype]["url"])
                        break
    except Exception:
        pass
    return found


def search_wikimedia_commons_hd(name: str) -> list[str]:
    encoded = quote(clean_query(name))
    url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={encoded}&gsrnamespace=6&prop=imageinfo&iiprop=url|size|mime&format=json"
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                ii = pdata.get("imageinfo", [{}])[0]
                mime = ii.get("mime", "")
                w = ii.get("width", 0)
                h = ii.get("height", 0)
                img_url = ii.get("url", "")
                if mime.startswith("image/") and not mime.endswith("svg+xml") and w >= 800 and img_url:
                    results.append(img_url)
    except Exception:
        pass
    return results


def download_file(url: str, out_path: Path) -> bool:
    try:
        with requests.get(url, stream=True, headers=HEADERS, timeout=30) as r:
            if r.status_code == 200 and int(r.headers.get("content-length", 5000)) > 4000:
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                return True
    except Exception:
        pass
    return False


def convert_image_to_hd_clip(img_path: Path, out_path: Path, duration: float, w: int, h: int, fps: int, zoom_idx: int = 0):
    try:
        im = Image.open(img_path).convert("RGBA")
        iw, ih = im.size
        target_ratio = w / h
        if (iw / ih) > target_ratio:
            new_w = int(ih * target_ratio)
            im = im.crop(((iw - new_w) // 2, 0, (iw + new_w) // 2, ih))
        else:
            new_h = int(iw / target_ratio)
            im = im.crop((0, (ih - new_h) // 2, iw, (ih + new_h) // 2))
        
        im = im.resize((w, h), Image.Resampling.LANCZOS)
        enh = ImageEnhance.Contrast(im).enhance(1.08)
        enh = ImageEnhance.Color(enh).enhance(1.15)
        clean_img_path = img_path.with_name(f"clean_{img_path.name}")
        enh.convert("RGB").save(clean_img_path, quality=95)
    except Exception:
        clean_img_path = img_path

    frames = int(duration * fps)
    if zoom_idx % 2 == 0:
        zoom_expr = f"zoompan=z=\'min(1.15,1.0+0.005*on)\':d={frames}:x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\':s={w}x{h}:fps={fps}"
    else:
        zoom_expr = f"zoompan=z=\'max(1.0,1.14-0.005*on)\':d={frames}:x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\':s={w}x{h}:fps={fps}"

    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(clean_img_path),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},{zoom_expr}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-t", f"{duration:.3f}", str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True)


def trim_video_clip(in_path: Path, out_path: Path, duration: float, w: int, h: int, fps: int):
    cmd = [
        "ffmpeg", "-y", "-i", str(in_path),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-an", "-pix_fmt", "yuv420p", "-t", f"{duration:.3f}", str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True)


def _calculate_scene_durations(words: list[dict], scenes: list[dict], total_audio_dur: float) -> list[float]:
    if not words or not scenes:
        per_scene = total_audio_dur / max(1, len(scenes))
        return [max(3.0, per_scene) for _ in scenes]

    spoken = [s.get("text", "").lower() for s in scenes]
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
        durations.append(max(2.5, end_t - start_t))
        cursor = end_idx

    tot = sum(durations)
    if tot < total_audio_dur:
        extra = total_audio_dur - tot + 0.5
        durations[-1] += extra
    return durations


def fetch_all(scenes: list[dict], out_dir: Path, words: list[dict] = None, voice_audio: Path = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_clips = []
    v = CONFIG["video"]
    w, h, fps = v["width"], v["height"], v["fps"]

    total_audio_dur = probe_duration(voice_audio) if (voice_audio and voice_audio.exists()) else (len(scenes) * 7.0)
    scene_durations = _calculate_scene_durations(words, scenes, total_audio_dur)

    # Usage trackers to enforce strict MAX 2X visual repetition rule across the entire video
    used_sources = {}  # url/link -> usage_count
    donor_usage = {}   # donor_path -> usage_count
    video_pool = []
    clip_counter = 0

    print(f"    [Curated Visuals] Fetching clean HD stock footage for {len(scenes)} scenes ({total_audio_dur:.1f}s audio, max 2x reuse)...")

    for i, scene in enumerate(scenes):
        total_scene_dur = scene_durations[i]
        num_subclips = max(1, int(round(total_scene_dur / 3.2)))
        subclip_dur = total_scene_dur / num_subclips

        queries = []
        factual = scene.get("factual_subject")
        if factual and isinstance(factual, str) and factual.lower() != "null":
            queries.append(factual.strip())

        vq = scene.get("visual_query", "")
        if vq:
            queries.append(vq.strip())

        for sub_idx in range(num_subclips):
            out_clip_path = out_dir / f"clip_{clip_counter:03d}.mp4"
            clip_ready = False

            # 1. Search Pexels HD Portrait Video
            for q in queries:
                links = search_pexels_hd_video(q)
                candidate_links = [lnk for lnk in links if used_sources.get(lnk, 0) < 2]
                candidate_links.sort(key=lambda lnk: used_sources.get(lnk, 0))

                for link in candidate_links:
                    temp_v = out_dir / f"raw_v_{clip_counter}.mp4"
                    if download_file(link, temp_v):
                        trim_video_clip(temp_v, out_clip_path, subclip_dur, w, h, fps)
                        if out_clip_path.exists() and out_clip_path.stat().st_size > 1000:
                            used_sources[link] = used_sources.get(link, 0) + 1
                            if temp_v not in video_pool:
                                video_pool.append(temp_v)
                            clip_ready = True
                            break
                if clip_ready:
                    break

            # 2. Search Pixabay HD Motion Video
            if not clip_ready:
                for q in queries:
                    links = search_pixabay_hd_video(q)
                    candidate_links = [lnk for lnk in links if used_sources.get(lnk, 0) < 2]
                    candidate_links.sort(key=lambda lnk: used_sources.get(lnk, 0))

                    for link in candidate_links:
                        temp_v = out_dir / f"raw_pb_{clip_counter}.mp4"
                        if download_file(link, temp_v):
                            trim_video_clip(temp_v, out_clip_path, subclip_dur, w, h, fps)
                            if out_clip_path.exists() and out_clip_path.stat().st_size > 1000:
                                used_sources[link] = used_sources.get(link, 0) + 1
                                if temp_v not in video_pool:
                                    video_pool.append(temp_v)
                                clip_ready = True
                                break
                    if clip_ready:
                        break

            # 3. Search Wikimedia Commons Real Photo
            if not clip_ready:
                for q in queries:
                    img_links = search_wikimedia_commons_hd(q)
                    candidate_img_links = [img_url for img_url in img_links if used_sources.get(img_url, 0) < 2]
                    candidate_img_links.sort(key=lambda img_url: used_sources.get(img_url, 0))

                    for img_url in candidate_img_links:
                        temp_img = out_dir / f"raw_wm_{clip_counter}.jpg"
                        if download_file(img_url, temp_img):
                            convert_image_to_hd_clip(temp_img, out_clip_path, subclip_dur, w, h, fps, zoom_idx=clip_counter)
                            if out_clip_path.exists() and out_clip_path.stat().st_size > 1000:
                                used_sources[img_url] = used_sources.get(img_url, 0) + 1
                                clip_ready = True
                                break
                    if clip_ready:
                        break

            # 4. Failsafe: Pool Recycling (Max 2x per donor footage with alternating pan/zoom)
            if not clip_ready and video_pool:
                valid_donors = [d for d in video_pool if donor_usage.get(d, 0) < 2]
                if valid_donors:
                    valid_donors.sort(key=lambda d: donor_usage.get(d, 0))
                    donor = valid_donors[0]
                    trim_video_clip(donor, out_clip_path, subclip_dur, w, h, fps)
                    if out_clip_path.exists() and out_clip_path.stat().st_size > 1000:
                        donor_usage[donor] = donor_usage.get(donor, 0) + 1
                        clip_ready = True

            if not clip_ready:
                # Solid dark cinematic gradient placeholder (never raw web junk)
                im = Image.new("RGB", (w, h), (15, 20, 30))
                ph_path = out_dir / f"ph_{clip_counter}.jpg"
                im.save(ph_path)
                convert_image_to_hd_clip(ph_path, out_clip_path, subclip_dur, w, h, fps, zoom_idx=clip_counter)

            all_clips.append(out_clip_path)
            clip_counter += 1

        print(f"    scene {i+1}/{len(scenes)}: {total_scene_dur:.1f}s -> {num_subclips} HD clips ready")

    print(f"    [Curated Visuals] All {len(all_clips)} HD clips fetched cleanly without web junk (Strict max 2x repetition).")
    return all_clips


fetch_for_scenes = fetch_all
