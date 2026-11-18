"""Merkt sich, welche Clips schon verarbeitet wurden (damit nichts doppelt hochgeladen wird)."""
import sqlite3
import time


class State:
    def __init__(self, path="state.db"):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS clips (id TEXT PRIMARY KEY, status TEXT, ts REAL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS videos (datei TEXT PRIMARY KEY, clips TEXT, "
            "tiktok TEXT, youtube TEXT, ts REAL)"
        )
        self.db.commit()

    def is_used(self, clip_id):
        return self.db.execute("SELECT 1 FROM clips WHERE id=?", (clip_id,)).fetchone() is not None

    def mark_used(self, clip_id, status="verwendet"):
        self.db.execute("INSERT OR REPLACE INTO clips VALUES (?,?,?)", (clip_id, status, time.time()))
        self.db.commit()

    def add_video(self, datei, clip_ids):
        self.db.execute(
            "INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?)",
            (datei, ",".join(clip_ids), None, None, time.time()),
        )
        self.db.commit()

    def set_upload(self, datei, plattform, wert):
        self.db.execute(f"UPDATE videos SET {plattform}=? WHERE datei=?", (wert, datei))
        self.db.commit()
