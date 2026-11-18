# GTA 6 Clip-Engine

Holt jede Stunde die meistgesehenen deutschen und englischen GTA-6-Clips von Twitch,
schneidet sie zu einem Hochformat-Video (max. 59 s) mit Untertiteln zusammen und schickt es
als Entwurf in die TikTok-App. Läuft komplett auf GitHub, kein PC nötig.

## Einrichtung (geht alles vom Handy im Browser)

### 1. Twitch-App
dev.twitch.tv/console → „Register Your Application“
- Name: beliebig · OAuth Redirect URL: `http://localhost` · Kategorie: Application Integration · Client-Typ: Vertraulich
- Client-ID und „New Secret“ kopieren. (Twitch verlangt dafür Zwei-Faktor-Login auf deinem Konto.)

### 2. TikTok-App
developers.tiktok.com → App erstellen
- Produkte hinzufügen: **Login Kit** und **Content Posting API** (Scopes `user.info.basic`, `video.upload`)
- Redirect URI: `https://github.com/candys-visuals/GTA-6-Engine-`
- Unter „Sandbox“ dein TikTok-Konto als Testnutzer eintragen
- Client Key und Client Secret kopieren

### 3. Secrets in GitHub eintragen
Repository → Settings → Secrets and variables → Actions → „New repository secret“:

| Name | Inhalt |
|---|---|
| `TWITCH_CLIENT_ID` | aus Schritt 1 |
| `TWITCH_CLIENT_SECRET` | aus Schritt 1 |
| `TIKTOK_CLIENT_KEY` | aus Schritt 2 |
| `TIKTOK_CLIENT_SECRET` | aus Schritt 2 |
| `CACHE_KEY` | ein langes Fantasie-Passwort (verschlüsselt den gespeicherten Stand) |

### 4. TikTok verbinden
Actions → **TikTok verbinden** → „Run workflow“ (Feld leer lassen) → im Ergebnis auf den Link tippen,
einloggen → komplette Adresse kopieren → „Run workflow“ nochmal, Adresse ins Feld einfügen.

### 5. Starten
Actions → **GTA 6 Clips** → „Run workflow“. Ab dann läuft es jede Stunde von allein.

## Bedienung
- **Pausieren:** Actions → GTA 6 Clips → ⋯ → Disable workflow
- **Videos ansehen:** Jeder Lauf hat unten „Artifacts → videos“ zum Download (3 Tage)
- **Einstellungen:** `config.yaml` (Mindest-Aufrufe, Sprachen, Hook-Text, Sperrliste …)
- **Intervall ändern:** `.github/workflows/clips.yml`, Zeile mit `cron`
- TikTok erlaubt nur wenige offene Entwürfe gleichzeitig – poste oder lösche sie regelmäßig in der App.
