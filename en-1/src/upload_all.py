import shutil
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from .state import load
from .upload import upload_video
from .config import STATE_FILE, CONFIG

QUOTA_MAX = 6

def main():
    state = load()
    unpublished = [e for e in state["published"] if e.get("video_id") is None]

    if not unpublished:
        print("Semua video sudah terupload. Tidak ada yang perlu diupload.")
        return

    print(f"Ditemukan {len(unpublished)} video pending.")
    print(f"Kuota API: max {QUOTA_MAX} upload hari ini.\n")

    uploaded = 0
    for i, entry in enumerate(unpublished):
        if uploaded >= QUOTA_MAX:
            print(f"\nSudah mencapai batas {QUOTA_MAX} upload hari ini. Lanjutkan besok.")
            break

        path = Path(entry["path"])
        if not path.exists():
            print(f"[SKIP] File tidak ditemukan: {path}")
            continue

        safe_title = entry['title'].encode('ascii', errors='replace').decode('ascii')
        print(f"[{uploaded+1}/{min(len(unpublished), QUOTA_MAX)}] Uploading: {safe_title}")
        print(f"  path: {entry['path']}")

        try:
            tags = CONFIG["upload"]["default_tags"]
            desc = f"{entry['title']}\n\n{CONFIG['niche']}\n\n#shorts #{entry['topic'].replace('-', ' ')}"

            video_id = upload_video(
                video_path=path,
                title=entry["title"],
                description=desc,
                tags=tags,
                publish_at=None,
            )
            print(f"  OK! Video ID: {video_id}")
            print(f"  https://youtube.com/shorts/{video_id}")

            for e in state["published"]:
                if e["ts"] == entry["ts"] and e["title"] == entry["title"]:
                    e["video_id"] = video_id
                    break

            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

            video_dir = path.parent
            if video_dir.exists():
                shutil.rmtree(video_dir)
                print(f"  Cleanup: {video_dir} deleted.")

            uploaded += 1

        except Exception as e:
            print(f"  GAGAL: {e}")
            if "quota" in str(e).lower() or "dailyLimitExceeded" in str(e):
                print("  Kuota API habis. Hentikan upload.")
                break
            continue

        time.sleep(5)

    print(f"\nSelesai. {uploaded} video berhasil diupload hari ini.")
    remaining = len([e for e in state["published"] if e.get("video_id") is None])
    if remaining > 0:
        print(f"Sisa {remaining} video pending. Akan terupload sesuai jadwal.")

if __name__ == "__main__":
    main()
