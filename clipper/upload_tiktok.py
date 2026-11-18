"""TikTok Content Posting API – lädt das Video als Entwurf in dein TikTok-Postfach.
Du bekommst eine Benachrichtigung in der App und tippst nur noch auf "Posten"."""
import json
import os
import secrets
import time
import urllib.parse

import requests

TOKEN_DATEI = os.environ.get("TIKTOK_TOKEN_DATEI", "tiktok_token.json")
OAUTH = "https://open.tiktokapis.com/v2/oauth/token/"


def auth_url(tcfg):
    return "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": tcfg["client_key"], "scope": "user.info.basic,video.upload",
        "response_type": "code", "redirect_uri": tcfg["redirect_uri"],
        "state": secrets.token_urlsafe(16),
    })


def exchange(tcfg, eingabe):
    """eingabe = komplette Adresse nach dem Login (oder nur der Code)."""
    eingabe = eingabe.strip()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(eingabe).query)
    code = q.get("code", [eingabe])[0]
    r = requests.post(OAUTH, timeout=20, headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"client_key": tcfg["client_key"], "client_secret": tcfg["client_secret"],
                            "code": code, "grant_type": "authorization_code",
                            "redirect_uri": tcfg["redirect_uri"]})
    _save(r)
    print("TikTok verbunden ✔")


def login(tcfg):
    print("\n1) Öffne diesen Link im Browser und melde dich mit deinem TikTok-Konto an:\n")
    print(auth_url(tcfg))
    print("\n2) Danach landest du auf deiner Redirect-Seite. Kopiere die KOMPLETTE Adresse aus der")
    exchange(tcfg, input("   Adresszeile und füge sie hier ein: "))


def _save(r):
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok-Login fehlgeschlagen: {data}")
    data["expires_at"] = time.time() + data.get("expires_in", 86400) - 300
    with open(TOKEN_DATEI, "w") as f:
        json.dump(data, f)
    return data


def _token(tcfg):
    if not os.path.exists(TOKEN_DATEI):
        raise RuntimeError("TikTok nicht verbunden – zuerst 'python run.py login-tiktok' ausführen.")
    with open(TOKEN_DATEI) as f:
        tok = json.load(f)
    if time.time() > tok["expires_at"]:
        r = requests.post(OAUTH, timeout=20, headers={"Content-Type": "application/x-www-form-urlencoded"},
                          data={"client_key": tcfg["client_key"], "client_secret": tcfg["client_secret"],
                                "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
        tok = _save(r)
    return tok["access_token"]


def upload(pfad, tcfg):
    token = _token(tcfg)
    groesse = os.path.getsize(pfad)
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/", timeout=30,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json={"source_info": {"source": "FILE_UPLOAD", "video_size": groesse,
                              "chunk_size": groesse, "total_chunk_count": 1}},
    )
    data = r.json()
    if data.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok init fehlgeschlagen: {data['error']}")
    with open(pfad, "rb") as f:
        put = requests.put(data["data"]["upload_url"], data=f, timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Length": str(groesse),
            "Content-Range": f"bytes 0-{groesse - 1}/{groesse}"})
    put.raise_for_status()
    return data["data"]["publish_id"]
