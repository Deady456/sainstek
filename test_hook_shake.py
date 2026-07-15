import sys
import time
from pathlib import Path
import subprocess
import random

# Pastikan script bisa mengimpor module dari src/
sys.path.append(str(Path(__file__).parent))

from src.config import CONFIG
from src import voice, captions
from src.assemble import _scene_durations

def run_test():
    work_dir = Path("output/test_shake")
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Teks dummy
    hook_text = "FAKTA GILA HEWAN LAUT"
    full_text = f"{hook_text} Tahukah kamu bahwa gurita memiliki tiga jantung? Dua untuk insang dan satu untuk tubuhnya. Ini adalah fakta yang luar biasa!"
    
    print("1/5 Synthesizing voice (Memanggil TTS)...")
    voice_mp3 = work_dir / "voice.mp3"
    voice.synth(full_text, voice_mp3)
    
    print("2/5 Transcribing (Mendapatkan timing kata)...")
    words = captions.transcribe_words(voice_mp3, original_text=full_text)
    
    # Memotong kata-kata hook agar tidak muncul di subtitle biasa
    hook_word_count = len(hook_text.split())
    captions_words = words[hook_word_count:]
    captions_ass = captions.write_ass(captions_words, work_dir / "captions.ass", 1080, 1920)
    
    print("3/5 Generating Shake Hook ASS...")
    # Hitung durasi hook berdasarkan kata yang ditranskrip
    scenes = [{"text": hook_text}, {"text": full_text.replace(hook_text, "").strip()}]
    durations = _scene_durations(words, scenes)
    ht_dur = 3.0
    print(f"    Durasi pembacaan hook: {ht_dur:.2f} detik")
    
    # Pilih 3 warna acak
    palettes = ["&H00FFFF&", "&HFFFFFF&", "&H00FF00&", "&HFFFF00&", "&HFF00FF&", "&H0080FF&"]
    c1, c2, c3 = random.sample(palettes, 3)
    hw = hook_text.split()
    third = len(hw) // 3
    l1 = " ".join(hw[:third])
    l2 = " ".join(hw[third:2*third]) if third < len(hw) else hw[1] if len(hw)>1 else ""
    l3 = " ".join(hw[2*third:]) if third*2 < len(hw) else ""
    
    if len(hw) == 4:
        l1 = " ".join(hw[:2])
        l2 = hw[2]
        l3 = hw[3]
    
    def fmt_time(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        cs = int((sec % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    shake_dur = min(0.5, ht_dur)
    frames = int(shake_dur * 30)
    events = []
    
    # Frame bergetar untuk 0.5 detik pertama
    if frames > 0:
        frame_len = shake_dur / frames
        for i in range(frames):
            st = i * frame_len
            en = (i + 1) * frame_len
            
            p = st / shake_dur
            ease_out = 1 - (1 - p) ** 3
            alpha_val = int(255 * (1 - ease_out))
            alpha_tag = f"\\alpha&H{alpha_val:02X}&"
            
            x_center = int(-300 + (840) * ease_out)
            
            dx = random.randint(-20, 20)
            dy = random.randint(-20, 20)
            pos = f"{{\\pos({x_center+dx},{600+dy}){alpha_tag}}}"
            styled = f"{pos}{{\\c{c1}}}{l1}"
            if l2: styled += f"\\N{{\\c{c2}}}{l2}"
            if l3: styled += f"\\N{{\\c{c3}}}{l3}"
            events.append(f"Dialogue: 0,{fmt_time(st)},{fmt_time(en)},HookText,,0,0,0,,{styled}")
    
    # Teks statis untuk sisa durasi hook
    if ht_dur > shake_dur:
        pos = f"{{\\pos(540,600)}}"
        styled = f"{pos}{{\\c{c1}}}{l1}"
        if l2: styled += f"\\N{{\\c{c2}}}{l2}"
        if l3: styled += f"\\N{{\\c{c3}}}{l3}"
        events.append(f"Dialogue: 0,{fmt_time(shake_dur)},{fmt_time(ht_dur)},HookText,,0,0,0,,{styled}")
        
    events_str = "\n".join(events)
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HookText,Impact,130,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,12,0,5,10,10,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{events_str}
"""
    hook_ass = work_dir / "hook.ass"
    hook_ass.write_text(ass_content, encoding="utf-8")
    
    print("4/5 Rendering video dengan latar solid biru gelap...")
    out_mp4 = work_dir / "test_shake.mp4"
    hook_ass_arg = str(hook_ass).replace("\\", "/").replace(":", "\\:")
    captions_ass_arg = str(captions_ass).replace("\\", "/").replace(":", "\\:")
    fonts_arg = str(Path("assets/fonts").absolute()).replace("\\", "/").replace(":", "\\:")
    
    vf = f"subtitles='{hook_ass_arg}':fontsdir='{fonts_arg}',subtitles='{captions_ass_arg}':fontsdir='{fonts_arg}'"
    
    cmd = [
        "ffmpeg", "-y", 
        "-f", "lavfi", "-i", "color=c=navy:s=1080x1920:r=30:d=10",
        "-i", str(voice_mp3),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-shortest", "-pix_fmt", "yuv420p", str(out_mp4)
    ]
    
    subprocess.run(cmd, check=True)
    print(f"\n5/5 Selesai! Video hasil tes tersimpan di: {out_mp4}")

if __name__ == "__main__":
    run_test()
