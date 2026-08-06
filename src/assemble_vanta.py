import json
import shutil
import subprocess
from pathlib import Path

def build(
    scene_videos: list[Path],
    voice_audio: Path,
    captions_ass: Path,
    words: list[dict],
    scenes: list[dict],
    out_path: Path,
    work_dir: Path,
    videos_per_scene: int = 2,
    hook_text: str = "",
    thumbnail_img: Path = None,
) -> Path:
    print("    [Vanta] Preparing assets for Vanta Remotion...")
    
    # Path is relative to this file: ../vanta
    vanta_dir = Path(__file__).resolve().parent.parent / "vanta"
    job_dir = vanta_dir / "public" / "job_temp"
    
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy voice
    vanta_voice = job_dir / "voice.mp3"
    shutil.copy2(voice_audio, vanta_voice)
    
    # Copy b-rolls
    broll_paths = []
    for i, vid in enumerate(scene_videos):
        dst = job_dir / f"vid_{i}.mp4"
        shutil.copy2(vid, dst)
        broll_paths.append(f"job_temp/{dst.name}")
        
    # Calculate duration (last word end time + 1 second)
    duration_s = 5.0
    if words:
        duration_s = words[-1]["end"] + 1.0
        
    frames = int(duration_s * 30)
    if frames < 30:
        frames = 30
        
    # Build props.json
    props = {
        "title": scenes[0]["text"] if scenes else hook_text,
        "voice_audio": f"job_temp/voice.mp3",
        "broll": broll_paths,
        "words": words,
        "durationInSeconds": duration_s
    }
    
    props_path = job_dir / "props.json"
    props_path.write_text(json.dumps(props, indent=2))
    
    print(f"    [Vanta] Running Remotion render ({frames} frames)...")
    
    # Ensure out_path's parent exists
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "npx", "remotion", "render",
        "src/index.ts",
        "FacelessVideo",
        str(out_path.absolute()),
        f"--props=public/job_temp/props.json"
    ]
    
    result = subprocess.run(cmd, cwd=vanta_dir, capture_output=True, text=True, shell=True)
    
    if result.returncode != 0:
        print("Vanta Render Failed!")
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("Vanta Render Failed")
        
    print(f"    [Vanta] Render complete: {out_path.name}")
    return out_path
