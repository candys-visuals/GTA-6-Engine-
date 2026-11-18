"""YouTube Shorts Upload über die YouTube Data API."""
import os

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_DATEI = "youtube_token.json"


def _creds(ycfg, interaktiv=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(TOKEN_DATEI):
        creds = Credentials.from_authorized_user_file(TOKEN_DATEI, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not interaktiv:
            raise RuntimeError("YouTube nicht verbunden – zuerst 'python run.py login-youtube' ausführen.")
        flow = InstalledAppFlow.from_client_secrets_file(ycfg["client_secrets_datei"], SCOPES)
        creds = flow.run_local_server(port=0)
    with open(TOKEN_DATEI, "w") as f:
        f.write(creds.to_json())
    return creds


def login(ycfg):
    _creds(ycfg, interaktiv=True)
    print("YouTube verbunden ✔")


def upload(pfad, titel, beschreibung, ycfg):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    yt = build("youtube", "v3", credentials=_creds(ycfg))
    req = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": titel[:100], "description": beschreibung,
                        "tags": ["gta6", "gtavi", "gta", "shorts"], "categoryId": "20"},
            "status": {"privacyStatus": ycfg.get("sichtbarkeit", "private"),
                       "selfDeclaredMadeForKids": False},
        },
        media_body=MediaFileUpload(str(pfad), mimetype="video/mp4", chunksize=-1, resumable=True),
    )
    resp = None
    while resp is None:
        _status, resp = req.next_chunk()
    return resp["id"]
