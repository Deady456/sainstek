import argparse
import json
from .state import load
from .upload import upload_video
from .config import STATE_FILE, CONFIG

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--index", type=int, default=None, help="Pilih index video dari daftar (0 = terbaru)")
    p.add_argument("--publish-at", default=None, help="ISO8601 UTC untuk jadwal upload")
    args = p.parse_args()

    state = load()
    unpublished = [e for e in state["published"] if e.get("video_id") is None]

    if not unpublished:
        print("Semua video sudah terupload. Tidak ada yang perlu diupload.")
        return

    if args.index is not None:
        entry = unpublished[args.index]
    else:
        entry = unpublished[-1]

    print(f"Uploading: {entry['title']}")
    print(f"  path: {entry['path']}")
    print(f"  topic: {entry['topic']}")
    print(f"  ts: {entry['ts']}")

    tags = CONFIG["upload"]["default_tags"]
    desc = f"{entry['title']}\n\n{CONFIG['niche']}\n\n#shorts #{entry['topic'].replace('-', ' ')}"

    video_id = upload_video(
        video_path=entry["path"],
        title=entry["title"],
        description=desc,
        tags=tags,
        publish_at=args.publish_at,
    )
    print(f"Uploaded OK. Video ID: {video_id}")
    print(f"https://youtube.com/shorts/{video_id}")

    for e in state["published"]:
        if e["ts"] == entry["ts"] and e["title"] == entry["title"]:
            e["video_id"] = video_id
            break
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print("state.json updated.")

if __name__ == "__main__":
    main()
