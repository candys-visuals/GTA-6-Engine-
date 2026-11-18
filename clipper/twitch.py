"""Twitch-API: findet die beliebtesten GTA-6-Clips der erlaubten Kanäle und lädt sie herunter."""
import datetime as dt
import subprocess
import sys
from pathlib import Path

import requests

API = "https://api.twitch.tv/helix"


class Twitch:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        r = requests.post(
            "https://id.twitch.tv/oauth2/token",
            data={"client_id": client_id, "client_secret": client_secret,
                  "grant_type": "client_credentials"},
            timeout=20,
        )
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def _get(self, path, params):
        r = requests.get(
            f"{API}/{path}", params=params, timeout=20,
            headers={"Client-ID": self.client_id, "Authorization": f"Bearer {self.token}"},
        )
        r.raise_for_status()
        return r.json()

    def game_id(self, name):
        data = self._get("games", {"name": name})["data"]
        if not data:
            raise SystemExit(f"Spiel '{name}' auf Twitch nicht gefunden – Kategorie-Name prüfen.")
        return data[0]["id"]

    def user_ids(self, logins):
        ids = {}
        for i in range(0, len(logins), 100):
            batch = logins[i:i + 100]
            for u in self._get("users", [("login", l) for l in batch])["data"]:
                ids[u["login"].lower()] = u["id"]
        missing = set(logins) - set(ids)
        if missing:
            print(f"  ! Kanäle nicht gefunden: {', '.join(sorted(missing))}")
        return ids

    def clips(self, broadcaster_id, game_id, hours):
        """Clips eines Kanals aus den letzten X Stunden, nur aus der GTA-6-Kategorie."""
        start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours))
        params = {
            "broadcaster_id": broadcaster_id,
            "started_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "first": 100,
        }
        return [c for c in self._get("clips", params)["data"] if c.get("game_id") == game_id]

    def game_clips(self, game_id, hours, max_clips=500):
        """Die meistgesehenen Clips der ganzen GTA-6-Kategorie (alle Streamer)."""
        start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours))
        params = {"game_id": game_id, "first": 100,
                  "started_at": start.strftime("%Y-%m-%dT%H:%M:%SZ")}
        out = []
        while len(out) < max_clips:
            data = self._get("clips", params)
            out += data["data"]
            cursor = data.get("pagination", {}).get("cursor")
            if not cursor or not data["data"]:
                break
            params["after"] = cursor
        return out


def find_clips(cfg, state):
    tc = cfg["twitch"]
    tw = Twitch(tc["client_id"], tc["client_secret"])
    gid = tw.game_id(tc["spiel"])
    kanaele = {k["name"].lower(): k for k in (cfg.get("kanaele") or [])}
    sprachen = set(tc.get("sprachen") or [])
    sperre = {s.lower() for s in (cfg.get("sperrliste") or [])}

    if cfg.get("alle_kanaele"):
        result = []
        for c in tw.game_clips(gid, tc.get("zeitraum_stunden", 6)):
            login = c["broadcaster_name"].lower()
            if login in sperre or state.is_used(c["id"]):
                continue
            if c["view_count"] < tc.get("min_views", 0):
                continue
            if sprachen and c.get("language") not in sprachen:
                continue
            c["login"] = login
            c["facecam"] = kanaele.get(login, {}).get("facecam")
            result.append(c)
        # Bevorzugte Sprache (z.B. Deutsch) zuerst, danach nach Aufrufen
        bevorzugt = tc.get("bevorzugte_sprache")
        reihenfolge = sorted(result, key=lambda c: (c.get("language") == bevorzugt, c["view_count"]),
                             reverse=True)
        # Abwechslung: höchstens X Clips pro Streamer pro Durchlauf
        max_pro = tc.get("max_clips_pro_streamer", 3)
        zaehler, gemischt = {}, []
        for c in reihenfolge:
            zaehler[c["login"]] = zaehler.get(c["login"], 0) + 1
            if zaehler[c["login"]] <= max_pro:
                gemischt.append(c)
        return gemischt

    ids = tw.user_ids(list(kanaele))
    result = []
    for login, bid in ids.items():
        try:
            for c in tw.clips(bid, gid, tc.get("zeitraum_stunden", 6)):
                if c["view_count"] < tc.get("min_views", 0) or state.is_used(c["id"]):
                    continue
                if sprachen and c.get("language") not in sprachen:
                    continue
                c["login"] = login
                c["facecam"] = kanaele[login].get("facecam")
                result.append(c)
        except requests.HTTPError as e:
            print(f"  ! Fehler bei {login}: {e}")
    result.sort(key=lambda c: c["view_count"], reverse=True)
    return result


def download(clip, ordner):
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / f"{clip['id']}.mp4"
    if ziel.exists():
        return ziel
    subprocess.run(
        [sys.executable, "-m", "yt_dlp", "-q", "--no-warnings", "-f", "best[ext=mp4]/best",
         "-o", str(ziel), clip["url"]],
        check=True,
    )
    return ziel
