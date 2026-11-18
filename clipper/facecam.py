"""Findet die Facecam eines Streamers automatisch.

Idee: Die Webcam ist ein fester Bereich im Bild. Das Gesicht darin steht (fast) immer an derselben
Stelle, und der Raumhintergrund bewegt sich kaum – im Gegensatz zum Gameplay.
1. Gesichter in ~16 Bildern über den ganzen Clip suchen (YuNet).
2. Ein Gesicht, das in den meisten Bildern an derselben Stelle ist = Streamer-Gesicht.
3. Um das Gesicht herum den ruhigen (unbewegten) Bereich suchen = Webcam-Rahmen.
Ergebnis in Pixeln bezogen auf 1920x1080, oder None (keine Facecam / Vollbild-Kamera).
"""
from pathlib import Path

import numpy as np

MODELL = Path(__file__).with_name("face_detection_yunet_2023mar.onnx")
BW, BH = 960, 540          # Analyse-Auflösung
CAM_ASPECT = 1080 / 640    # Seitenverhältnis des oberen Bereichs im fertigen Video


def _frames(path, n=16):
    import cv2
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    out = []
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((i + 0.5) * total / n))
        ok, f = cap.read()
        if ok:
            out.append(cv2.resize(f, (BW, BH), interpolation=cv2.INTER_AREA))
    cap.release()
    return out


def detect(path, debug=False):
    import cv2
    frames = _frames(path)
    if len(frames) < 6:
        return None
    det = cv2.FaceDetectorYN.create(str(MODELL), "", (BW, BH), 0.75, 0.3, 50)

    faces = []  # (frame_idx, cx, cy, w, h)
    for i, f in enumerate(frames):
        _, res = det.detect(f)
        for r in (res if res is not None else []):
            x, y, w, h = r[:4]
            if w >= 14:
                faces.append((i, x + w / 2, y + h / 2, w, h))
    if not faces:
        return None

    grau = np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) for f in frames])
    std = grau.std(axis=0)

    # Stabile Gesichtsposition finden (gleiche Stelle in vielen Bildern).
    # Ein echtes Webcam-Gesicht bewegt sich leicht (reden, Mimik) – ein Gesicht auf einem
    # Standbild/Poster nicht. Solche Treffer werden verworfen.
    kandidaten = []
    for _, cx, cy, w, _h in faces:
        nah = [f for f in faces if abs(f[1] - cx) < max(w, 20) * 0.6 and abs(f[2] - cy) < max(w, 20) * 0.6]
        kandidaten.append((len({f[0] for f in nah}), nah))
    kandidaten.sort(key=lambda k: k[0], reverse=True)
    best = None
    for anzahl, cluster in kandidaten:
        if anzahl < len(frames) * 0.4:
            break
        a = np.array(cluster)
        cx, cy, fw, fh = (float(np.median(a[:, k])) for k in (1, 2, 3, 4))
        x0, y0 = int(max(0, cx - fw / 2)), int(max(0, cy - fh / 2))
        bewegung = float(std[y0:int(cy + fh / 2), x0:int(cx + fw / 2)].mean())
        if bewegung >= 5:
            best = (anzahl, cx, cy, fw, fh)
            break
    if best is None:
        return None
    anzahl, cx, cy, fw, fh = best

    # Gesicht riesig = Vollbild-Kamera ("Just Chatting"), kein Gameplay → überspringen
    if fh > BH * 0.28:
        return None

    # Ruhige Bereiche: geringe Veränderung über die Zeit
    ruhig = (std < 18).astype(np.uint8)
    ruhig = cv2.morphologyEx(ruhig, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    # Suchfenster um das Gesicht: Webcam ist selten größer als ~6 Gesichtshöhen
    sx0, sx1 = int(max(0, cx - fh * 5)), int(min(BW, cx + fh * 5))
    sy0, sy1 = int(max(0, cy - fh * 3.5)), int(min(BH, cy + fh * 3.5))
    fenster = np.zeros_like(ruhig)
    fenster[sy0:sy1, sx0:sx1] = ruhig[sy0:sy1, sx0:sx1]
    # Gesicht selbst bewegt sich → als "Webcam" markieren, damit der Bereich zusammenhängt
    fx0, fy0 = int(cx - fw * 0.8), int(cy - fh * 0.9)
    fenster[max(0, fy0):int(cy + fh * 1.2), max(0, fx0):int(cx + fw * 0.8)] = 1

    n, labels, stats, _ = cv2.connectedComponentsWithStats(fenster, 8)
    lab = labels[int(cy), int(cx)]
    x, y, w, h = stats[lab][:4]

    # Plausibilität: mind. 2,2× Gesichtshöhe, sonst großzügig ums Gesicht schneiden
    if h < fh * 1.5 or w < fw * 2.0:
        h = fh * 2.4
        w = h * CAM_ASPECT
        x, y = cx - w / 2, cy - h * 0.45

    # Nicht zu groß werden lassen (z.B. wenn auch ruhiges Gameplay daneben liegt)
    max_h = fh * 2.6
    if h > max_h:
        y = max(y, min(cy - max_h * 0.45, y + h - max_h))
        h = max_h
    max_w = max_h * CAM_ASPECT * 1.15
    if w > max_w:
        x = max(x, min(cx - max_w / 2, x + w - max_w))
        w = max_w

    # Auf das Ziel-Seitenverhältnis bringen, Gesicht im Bild halten
    x, y, w, h = float(x), float(y), float(w), float(h)
    if w / h > CAM_ASPECT:
        nw = h * CAM_ASPECT
        x = min(max(x, cx - nw / 2), x + w - nw)
        w = nw
    else:
        nh = w / CAM_ASPECT
        y = min(max(y, cy - nh * 0.45), y + h - nh)
        h = nh
    x, y = max(0.0, min(x, BW - w)), max(0.0, min(y, BH - h))

    s = 1920 / BW
    box = {"x": int(x * s), "y": int(y * s), "w": int(w * s), "h": int(h * s)}
    if debug:
        box["_gesicht"] = (cx * s, cy * s, fh * s, anzahl, len(frames))
    return box
