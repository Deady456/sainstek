"""
Human review system for FreeFaceless.

Modes:
- auto: Direct upload, no review
- draft: Save draft for manual review
- hybrid: Draft every N videos, auto for the rest
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from .config import CONFIG, ROOT


def _get_review_config() -> dict:
    return CONFIG.get("review", {})


def _get_draft_dir() -> Path:
    cfg = _get_review_config()
    rel_dir = cfg.get("draft_dir", "drafts")
    d = ROOT / rel_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_state() -> dict:
    from . import state
    return state.load()


def should_review(video_count: int) -> bool:
    """Determine if this video should go through review."""
    cfg = _get_review_config()
    mode = cfg.get("mode", "auto")

    if mode == "auto":
        return False
    elif mode == "draft":
        return True
    elif mode == "hybrid":
        # Review every N videos
        min_switch = CONFIG.get("content_variation", {}).get("min_format_switch", 5)
        return video_count % min_switch == 0
    return False


def save_draft(data: dict, final_video_path: Path) -> Path:
    """Save video and metadata as draft for review."""
    draft_dir = _get_draft_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = data.get("topic", "unknown")[:30].replace(" ", "_")
    draft_name = f"{stamp}_{slug}"

    draft_path = draft_dir / draft_name
    draft_path.mkdir(parents=True, exist_ok=True)

    # Copy video
    video_dest = draft_path / "final.mp4"
    shutil.copy2(final_video_path, video_dest)

    # Save metadata
    meta = {
        "topic": data.get("topic"),
        "title": data.get("title"),
        "description": data.get("description"),
        "tags": data.get("tags"),
        "scenes": data.get("scenes"),
        "format": data.get("format"),
        "voice": data.get("voice_used"),
        "video_path": str(video_dest),
        "created_at": datetime.now().isoformat(),
        "status": "pending",
    }

    meta_path = draft_path / "draft.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save script separately for easy reading
    script_path = draft_path / "script.txt"
    lines = []
    for i, scene in enumerate(data.get("scenes", []), 1):
        lines.append(f"[Scene {i}] {scene.get('text', '')}")
    script_path.write_text("\n\n".join(lines), encoding="utf-8")

    print(f"    review: draft saved to {draft_path}")
    return draft_path


def approve_draft(draft_name: str) -> dict | None:
    """Approve a draft and return its data for upload."""
    draft_dir = _get_draft_dir()
    draft_path = draft_dir / draft_name
    meta_path = draft_path / "draft.json"

    if not meta_path.exists():
        print(f"    review: draft not found: {draft_name}")
        return None

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["status"] = "approved"
    meta["approved_at"] = datetime.now().isoformat()
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"    review: approved draft: {draft_name}")
    return meta


def reject_draft(draft_name: str, reason: str = "") -> bool:
    """Reject a draft."""
    draft_dir = _get_draft_dir()
    draft_path = draft_dir / draft_name
    meta_path = draft_path / "draft.json"

    if not meta_path.exists():
        return False

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["status"] = "rejected"
    meta["rejected_at"] = datetime.now().isoformat()
    meta["reject_reason"] = reason
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"    review: rejected draft: {draft_name}")
    return True


def list_drafts(status: str = "pending") -> list[dict]:
    """List all drafts with given status."""
    draft_dir = _get_draft_dir()
    drafts = []

    for d in sorted(draft_dir.iterdir()):
        meta_path = d / "draft.json"
        if not meta_path.exists():
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("status") == status:
            drafts.append({
                "name": d.name,
                "topic": meta.get("topic"),
                "title": meta.get("title"),
                "created_at": meta.get("created_at"),
            })

    return drafts


def get_review_score(data: dict) -> int:
    """
    Simple quality score (1-10) based on content metrics.
    Used for auto-approve in hybrid mode.
    """
    score = 5  # Base score

    title = data.get("title", "")
    description = data.get("description", "")
    scenes = data.get("scenes", [])

    # Title quality
    if len(title) >= 40:
        score += 1
    if "?" in title or "!" in title:
        score += 1

    # Description quality
    if len(description) > 100:
        score += 1
    if "#" in description:
        score += 1

    # Scene count
    if len(scenes) >= 4:
        score += 1

    return min(10, max(1, score))

