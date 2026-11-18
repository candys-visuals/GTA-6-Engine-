"""GTA 6 Clip-Engine

  python run.py                 einmal: Clips suchen, schneiden, hochladen
  python run.py --loop          dauerhaft alle X Minuten (siehe config.yaml)
  python run.py --kein-upload   nur Videos bauen, nichts hochladen (zum Testen)
  python run.py --datei a.mp4 [b.mp4 ...]   eigene Videodateien verarbeiten (ohne Twitch)
  python run.py login-tiktok    TikTok-Konto verbinden (einmalig)
  python run.py login-youtube   YouTube-Konto verbinden (einmalig)
"""
import argparse
import os
import datetime as dt
import shutil
import time
import traceback
from pathlib import Path

import yaml

from clipper import subtitles, video
from clipper.state import State


def lade_config(pfad="config.yaml"):
    if not Path(pfad).exists():
        raise SystemExit("config.yaml fehlt – kopiere config.example.yaml zu config.yaml und fülle sie aus.")
    with open(pfad, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Zugangsdaten aus Umgebungsvariablen (GitHub Secrets) haben Vorrang
    env = os.environ.get
    if env("TWITCH_CLIENT_ID"):
        cfg["twitch"]["client_id"] = env("TWITCH_CLIENT_ID")
        cfg["twitch"]["client_secret"] = env("TWITCH_CLIENT_SECRET")
    if env("TIKTOK_CLIENT_KEY"):
        t = cfg.setdefault("upload", {}).setdefault("tiktok", {})
        t["client_key"] = env("TIKTOK_CLIENT_KEY")
        t["client_secret"] = env("TIKTOK_CLIENT_SECRET")
        t["aktiv"] = os.path.exists(os.environ.get("TIKTOK_TOKEN_DATEI", "tiktok_token.json"))
    return cfg


def plane_videos(clips, vcfg):
    """Teilt die gefundenen Clips in Videos auf (Zusammenschnitt bis max. 60 s oder einzeln)."""
    max_s = vcfg.get("max_sekunden", 60)
    max_videos = vcfg.get("max_videos_pro_durchlauf", 2)
    clips = [c for c in clips if c.get("duration", 0) >= 3]
    if vcfg.get("modus") == "einzeln":
        return [[c] for c in clips[:max_videos]]

    mindest = vcfg.get("min_clips_pro_zusammenschnitt", 2)

    def gueltig(gruppe, summe):
        # Ein langer Clip (≥ 40 s) darf allein ein Video sein, sonst mind. X Clips und ≥ 20 s
        return summe >= 40 or (len(gruppe) >= mindest and summe >= 20)

    videos, aktuell, summe = [], [], 0.0
    for c in clips:
        rest = max_s - summe
        # Würde der Clip zu einem kurzen Schnipsel abgeschnitten, lieber neues Video anfangen
        if aktuell and c["duration"] > rest and rest < 10:
            if gueltig(aktuell, summe):
                videos.append(aktuell)
            aktuell, summe, rest = [], 0.0, max_s
            if len(videos) >= max_videos:
                break
        aktuell.append(c)
        summe += min(c["duration"], rest)
        if summe >= max_s - 2:
            if gueltig(aktuell, summe):
                videos.append(aktuell)
            aktuell, summe = [], 0.0
            if len(videos) >= max_videos:
                break
    if aktuell and len(videos) < max_videos and gueltig(aktuell, summe):
        videos.append(aktuell)
    return videos


def baue_video(gruppe, cfg, arbeit, ausgabe):
    """gruppe: Liste von Dicts mit 'datei', 'name', optional 'facecam'. Gibt Pfad zum fertigen Video zurück."""
    vcfg, ucfg = cfg["video"], cfg.get("untertitel", {})
    max_s = vcfg.get("max_sekunden", 60)
    stempel = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp = Path(arbeit) / stempel
    tmp.mkdir(parents=True, exist_ok=True)

    segmente, credits, t = [], [], 0.0
    for i, c in enumerate(gruppe):
        rest = max_s - t
        if rest < 2:
            break
        seg = video.render_segment(c["datei"], tmp / f"seg{i}.mp4", rest, c.get("facecam"))
        d = video.duration(seg)
        segmente.append(seg)
        credits.append((t, t + d, f"twitch.tv/{c['name']}"))
        t += d
        print(f"    ✂ {c['name']}: {d:.1f}s")

    roh = video.concat(segmente, tmp / "roh.mp4")
    gesamt = video.duration(roh)

    words = []
    if ucfg.get("aktiv", True):
        print("    🎙 Untertitel werden erkannt …")
        words = subtitles.transcribe(roh, ucfg.get("whisper_modell", "small"), ucfg.get("geraet", "auto"))
    ass = subtitles.make_ass(tmp / "subs.ass", words, credits, gesamt, vcfg,
                             ucfg.get("woerter_pro_zeile", 3))
    Path(ausgabe).mkdir(parents=True, exist_ok=True)
    fertig = Path(ausgabe) / f"gta6_{stempel}.mp4"
    video.burn_subs(roh, ass, fertig)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"    ✅ {fertig} ({gesamt:.1f}s)")
    return fertig


def hochladen(datei, titel_daten, cfg, state):
    up = cfg.get("upload", {})
    titel = up.get("titel_vorlage", "{titel}").format(**titel_daten)
    beschreibung = up.get("beschreibung", "").format(**titel_daten)
    if up.get("tiktok", {}).get("aktiv"):
        from clipper import upload_tiktok
        try:
            pid = upload_tiktok.upload(datei, up["tiktok"])
            state.set_upload(str(datei), "tiktok", pid)
            print(f"    📤 TikTok: Entwurf in deinem Postfach (Titel zum Einfügen: {titel})")
        except Exception as e:
            print(f"    ! TikTok-Upload fehlgeschlagen: {e}")
    if up.get("youtube", {}).get("aktiv"):
        from clipper import upload_youtube
        try:
            vid = upload_youtube.upload(datei, titel, beschreibung, up["youtube"])
            state.set_upload(str(datei), "youtube", vid)
            print(f"    📤 YouTube: https://youtube.com/shorts/{vid}")
        except Exception as e:
            print(f"    ! YouTube-Upload fehlgeschlagen: {e}")


def durchlauf(cfg, state, upload=True):
    from clipper import twitch
    if not cfg.get("alle_kanaele") and not cfg.get("kanaele"):
        raise SystemExit("Keine Kanäle in config.yaml eingetragen (oder alle_kanaele: true setzen).")
    print(f"[{dt.datetime.now():%H:%M}] Suche neue GTA-6-Clips …")
    clips = twitch.find_clips(cfg, state)
    print(f"  {len(clips)} neue Clips gefunden")
    plan = plane_videos(clips, cfg["video"])
    if not plan:
        print("  Noch nicht genug Material – nächster Versuch beim nächsten Durchlauf.")
        return
    ausgabe = cfg.get("ausgabe_ordner", "ausgabe")
    for gruppe in plan:
        try:
            for c in gruppe:
                c["datei"] = twitch.download(c, Path(ausgabe) / "_downloads")
                c["name"] = c["login"]
            fertig = baue_video(gruppe, cfg, Path(ausgabe) / "_arbeit", ausgabe)
            for c in gruppe:
                state.mark_used(c["id"])
            state.add_video(str(fertig), [c["id"] for c in gruppe])
            if upload:
                namen = ", ".join(dict.fromkeys(c["broadcaster_name"] for c in gruppe))
                hochladen(fertig, {"titel": gruppe[0]["title"], "streamer": namen}, cfg, state)
        except Exception:
            print("  ! Fehler bei diesem Video:")
            traceback.print_exc()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("befehl", nargs="?", choices=["login-tiktok", "tiktok-link", "login-youtube"])
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--kein-upload", action="store_true")
    ap.add_argument("--datei", nargs="+", help="eigene Videodateien statt Twitch")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--code", help="bei login-tiktok: Adresse nach dem TikTok-Login")
    a = ap.parse_args()
    cfg = lade_config(a.config)

    if a.befehl == "login-tiktok":
        from clipper import upload_tiktok
        if a.code:
            return upload_tiktok.exchange(cfg["upload"]["tiktok"], a.code)
        return upload_tiktok.login(cfg["upload"]["tiktok"])
    if a.befehl == "tiktok-link":
        from clipper import upload_tiktok
        return print(upload_tiktok.auth_url(cfg["upload"]["tiktok"]))
    if a.befehl == "login-youtube":
        from clipper import upload_youtube
        return upload_youtube.login(cfg["upload"]["youtube"])

    state = State(os.environ.get("STATE_DB", "state.db"))
    if a.datei:
        gruppe = [{"datei": Path(d), "name": Path(d).stem} for d in a.datei]
        ausgabe = cfg.get("ausgabe_ordner", "ausgabe")
        fertig = baue_video(gruppe, cfg, Path(ausgabe) / "_arbeit", ausgabe)
        if not a.kein_upload:
            hochladen(fertig, {"titel": "GTA 6", "streamer": gruppe[0]["name"]}, cfg, state)
        return

    while True:
        try:
            durchlauf(cfg, state, upload=not a.kein_upload)
        except SystemExit:
            raise
        except Exception:
            traceback.print_exc()
        if not a.loop:
            break
        warte = cfg.get("intervall_minuten", 30)
        print(f"  Warte {warte} Minuten …\n")
        time.sleep(warte * 60)


if __name__ == "__main__":
    main()
