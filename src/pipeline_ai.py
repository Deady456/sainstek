import argparse, re, time
from datetime import datetime
from . import script, voice, captions, visuals_ai, assemble_ai, upload, state, branding
from .config import CONFIG, OUTPUT_DIR

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "ai-short"

def _log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def run_once(publish_at: str | None = None,
             upload_to_youtube: bool = True) -> dict:
    _log("1/7 Generating script with LLM")
    data = script.generate()
    _log(f"    topic: {data['topic']} ({len(data['scenes'])} scenes)")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = OUTPUT_DIR / f"{stamp}_{slug(data['topic'])}"
    work.mkdir(parents=True, exist_ok=True)

    _log("2/7 Synthesizing voiceover with Edge TTS")
    voice_mp3 = voice.synth(data["full_text"], work / "voice.mp3")
    _log(f"    voice saved ({voice_mp3.stat().st_size/1024:.0f} KB)")

    _log("3/7 Transcribing for word-level captions (Faster-Whisper)")
    _log("    loading model (first run downloads)...")
    t0 = time.time()
    words = captions.transcribe_words(voice_mp3, original_text=data["full_text"])
    _log(f"    {len(words)} words in {time.time()-t0:.1f}s")

    _log("4/7 Generating AI images via Pollinations")
    image_dir = work / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []
    
    # We get hook_text earlier so we can pass it to the first scene
    hook_text = data.get("thumbnail_text", "")
    hook_cfg = CONFIG.get("hook_text", {})
    if not hook_cfg.get("enabled", False):
        hook_text = ""
        
    for i, scene in enumerate(data["scenes"]):
        prompt = scene.get("visual_query", "abstract background")
        rich_prompt = f"{prompt}, cinematic, detailed, 4K"
        img_path = image_dir / f"scene_{i:02d}.jpg"
        _log(f"    scene {i+1}/{len(data['scenes'])}: \"{prompt}\"")
        t1 = time.time()
        
        scene_hook = hook_text if i == 0 else ""
        visuals_ai.generate(rich_prompt, img_path, hook_text=scene_hook)
        
        _log(f"      done in {time.time()-t1:.0f}s")
        image_paths.append(img_path)

    _log("5/7 Writing caption file")
    if hook_text:
        captions_words = words[len(hook_text.split()):]
    else:
        captions_words = words

    ass_path = captions.write_ass(captions_words, work / "captions.ass",
                                  CONFIG["video"]["width"], CONFIG["video"]["height"])

    _log("6/7 Assembling slideshow video with ffmpeg")
    t0 = time.time()
    final = assemble_ai.build(
        image_paths=image_paths,
        voice_audio=voice_mp3,
        captions_ass=ass_path,
        words=words,
        scenes=data["scenes"],
        out_path=work / "final.mp4",
        work_dir=work / "ffmpeg",
        hook_text="",  # Text is already burned into the image by Pillow
    )
    dur = time.time() - t0
    sz = final.stat().st_size / (1024 * 1024)
    _log(f"    final: {final.name} ({sz:.0f} MB, {dur:.0f}s render)")

    _log("Applying branding (watermark)")
    branded = branding.apply_all(final, work / "branding")
    if branded != final:
        final_branded = work / "final.mp4"
        branded.replace(final_branded)
        final = final_branded
    else:
        final_branded = work / "final.mp4"
        final.replace(final_branded)
        final = final_branded
    video_id = None
    if upload_to_youtube:
        _log("7/7 Uploading to YouTube")
        video_id = upload.upload_video(
            video_path=final,
            title=data["title"],
            description=data["description"],
            tags=data["tags"],
            publish_at=publish_at,
        )
        _log(f"    uploaded: https://youtube.com/shorts/{video_id}")

    state.add_topic(data["topic"])
    state.add_published({
        "ts": stamp,
        "topic": data["topic"],
        "title": data["title"],
        "path": str(final),
        "video_id": video_id,
        "publish_at": publish_at,
    })
    return {"video_id": video_id, "path": str(final), "topic": data["topic"]}

def main():
    p = argparse.ArgumentParser(description="AI podcast pipeline (Pollinations images)")
    p.add_argument("--no-upload", action="store_true")
    p.add_argument("--publish-at", default=None,
                   help="ISO8601 UTC timestamp for scheduled publish")
    args = p.parse_args()
    run_once(publish_at=args.publish_at, upload_to_youtube=not args.no_upload)
    print("\n" + "-" * 60)
    print("Done!")
    print("-" * 60)

if __name__ == "__main__":
    main()
