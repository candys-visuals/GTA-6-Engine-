"""Videoschnitt mit ffmpeg: Hochformat 9:16, Facecam oben, Zusammenschnitt, Untertitel einbrennen."""
import json
import subprocess
from pathlib import Path

W, H = 1080, 1920
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
       "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg-Fehler:\n{p.stderr[-2000:]}")
    return p


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "json", str(path)]).stdout
    return float(json.loads(out)["format"]["duration"])


def _filter(facecam):
    # Quelle immer zuerst auf 1920x1080 bringen, damit die Facecam-Koordinaten passen.
    base = "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease," \
           "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,split=2[a][b];"
    if facecam:
        cam_h = 640
        x, y, w, h = facecam["x"], facecam["y"], facecam["w"], facecam["h"]
        return base + (
            f"[a]crop={w}:{h}:{x}:{y},scale={W}:{cam_h}:force_original_aspect_ratio=increase,"
            f"crop={W}:{cam_h}[cam];"
            f"[b]scale=-2:{H - cam_h},crop={W}:{H - cam_h}[game];"
            f"[cam][game]vstack=inputs=2[v]"
        )
    # Ohne Facecam: unscharfer Hintergrund + gezoomtes Gameplay in der Mitte
    return base + (
        f"[a]scale=-2:{H},crop={W}:{H},boxblur=20:2,eq=brightness=-0.15[bg];"
        f"[b]crop=1440:1080,scale={W}:810[fg];"
        f"[bg][fg]overlay=0:(H-h)/2-80[v]"
    )


def render_segment(src, dst, max_dauer, facecam=None):
    """Einen Clip ins Hochformat bringen und auf max_dauer Sekunden kürzen."""
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", f"{max_dauer:.2f}",
         "-filter_complex", _filter(facecam), "-map", "[v]", "-map", "0:a?",
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", *ENC, str(dst)])
    return dst


def concat(segmente, dst):
    liste = Path(dst).with_suffix(".txt")
    liste.write_text("".join(f"file '{Path(s).resolve().as_posix()}'\n" for s in segmente))
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(liste),
         "-c", "copy", str(dst)])
    liste.unlink()
    return dst


def burn_subs(src, ass, dst):
    """Untertitel einbrennen. Läuft im Ordner der .ass-Datei, damit Windows-Pfade kein Problem machen."""
    ass = Path(ass).resolve()
    run(["ffmpeg", "-y", "-v", "error", "-i", str(Path(src).resolve()),
         "-vf", f"ass={ass.name}", *ENC, "-movflags", "+faststart",
         str(Path(dst).resolve())], cwd=ass.parent)
    return dst
