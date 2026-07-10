import json, os
from pathlib import Path
from . import state, blogger

def main():
    blog_id = os.environ.get("BLOG_ID")
    if not blog_id:
        print("BLOG_ID not set, skipping")
        return

    published = state.load().get("published", [])
    if not published:
        print("No published entries in state.json")
        return

    for entry in published:
        vid = entry.get("video_id") or entry.get("path", "")
        if not vid:
            continue

        print(f"Posting: {entry.get('title', 'untitled')}")
        try:
            url = blogger.publish(entry)
            if url:
                print(f"  OK: {url}")
            else:
                print("  FAILED")
        except Exception as e:
            print(f"  ERROR: {e}")

if __name__ == "__main__":
    main()
