import argparse
import re
import time
from datetime import datetime
from . import script, voice, captions, visuals, assemble, upload, state
from .config import OUTPUT_DIR


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "short"


def _log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def run_once(publish_at: str | None = None, upload_to_youtube: bool = True) -> dict:
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
    words = captions.transcribe_words(voice_mp3)
    _log(f"    {len(words)} words in {time.time()-t0:.1f}s")

    _log("4/7 Fetching footage from Pexels")
    scene_videos = visuals.fetch_for_scenes(data["scenes"], work / "broll")
    _log(f"    {len(scene_videos)} clips ready")

    _log("5/7 Writing caption file")
    from .config import CONFIG as CFG
    ass_path = captions.write_ass(words, work / "captions.ass",
                                  CFG["video"]["width"], CFG["video"]["height"])

    _log("6/7 Assembling final video with ffmpeg")
    _log("    processing scenes (scale/crop/loop)...")
    t0 = time.time()
    final = assemble.build(
        scene_videos=scene_videos,
        voice_audio=voice_mp3,
        captions_ass=ass_path,
        words=words,
        scenes=data["scenes"],
        out_path=work / "final.mp4",
        work_dir=work / "ffmpeg",
        videos_per_scene=2,
    )
    dur = time.time() - t0
    sz = final.stat().st_size / (1024 * 1024)
    _log(f"    final: {final.name} ({sz:.0f} MB, {dur:.0f}s render)")

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
    p = argparse.ArgumentParser()
    p.add_argument("--no-upload", action="store_true", help="Build only, don't upload")
    p.add_argument("--publish-at", default=None,
                   help="ISO8601 UTC timestamp for scheduled publish, e.g. 2026-05-20T14:00:00Z")
    args = p.parse_args()
    run_once(publish_at=args.publish_at, upload_to_youtube=not args.no_upload)

    print("\n" + "-" * 60)
    print("Done!")
    print("-" * 60)


if __name__ == "__main__":
    main()
