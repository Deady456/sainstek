import sys
import shutil
import subprocess
from pathlib import Path
from .voice import synth
from .config import ROOT, OUTPUT_DIR

CHUNK_SIZE = 5000
TEMP_DIR = OUTPUT_DIR / "_narasi_temp"

def chunk_text(text: str, size: int = CHUNK_SIZE):
    words = text.split()
    chunks, cur = [], []
    n = 0
    for w in words:
        if n + len(w) + 1 > size and cur:
            chunks.append(" ".join(cur))
            cur, n = [w], len(w)
        else:
            cur.append(w)
            n += len(w) + 1
    if cur:
        chunks.append(" ".join(cur))
    return chunks

def merge_audio(pieces: list[Path], out: Path):
    if len(pieces) == 1:
        shutil.copy2(pieces[0], out)
        return

    list_file = TEMP_DIR / "files.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in pieces), encoding="utf-8")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(list_file), "-c", "copy", str(out)],
        capture_output=True, check=True,
    )

def main():
    if len(sys.argv) < 2:
        print("Penggunaan:")
        print("  python -m src.narasi \"<teks>\" [output.mp3]")
        print("  python -m src.narasi @file.txt [output.mp3]")
        sys.exit(1)

    arg = sys.argv[1]
    if arg.startswith("@"):
        txt = Path(arg[1:]).read_text(encoding="utf-8")
    else:
        txt = arg

    out_name = sys.argv[2] if len(sys.argv) > 2 else "narasi.mp3"
    out_path = Path(out_name).resolve()

    chunks = chunk_text(txt)
    print(f"Teks: {len(txt)} chars -> {len(chunks)} chunk(s)")

    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
    TEMP_DIR.mkdir(parents=True)

    pieces = []
    for i, chunk in enumerate(chunks):
        print(f"  [{i+1}/{len(chunks)}] generating ({len(chunk)} chars)...")
        part = TEMP_DIR / f"part_{i:04d}.mp3"
        synth(chunk, part)
        pieces.append(part)

    print("Merging audio...")
    merge_audio(pieces, out_path)
    shutil.rmtree(TEMP_DIR)
    print(f"Done: {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")

if __name__ == "__main__":
    main()
