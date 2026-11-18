"""Spracherkennung mit Whisper + Untertitel im TikTok-Stil (Wort für Wort hervorgehoben)."""
_model = None


def transcribe(path, modell="small", geraet="auto"):
    """Gibt eine Liste von Wörtern zurück: [{'start', 'end', 'text'}, ...]."""
    global _model
    from faster_whisper import WhisperModel
    if _model is None:
        if geraet == "auto":
            try:
                import ctranslate2
                geraet = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                geraet = "cpu"
        _model = WhisperModel(modell, device=geraet,
                              compute_type="float16" if geraet == "cuda" else "int8")
    segments, _info = _model.transcribe(str(path), word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append({"start": w.start, "end": w.end, "text": t})
    return words


def _ts(sek):
    sek = max(0.0, sek)
    h, rest = divmod(sek, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _clean(t):
    return t.replace("{", "(").replace("}", ")").replace("\\", "").upper()


def make_ass(pfad, words, credits, gesamt, vcfg, woerter_pro_zeile=3):
    """credits: Liste von (start, ende, text) – z.B. Streamer-Name pro Clip-Abschnitt."""
    font = vcfg.get("schrift", "Arial Black")
    farbe = vcfg.get("untertitel_farbe", "&H00FFFFFF")
    hl = vcfg.get("highlight_farbe", "&H0000E5FF")
    hook = (vcfg.get("hook_text") or "").strip()

    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,{font},84,{farbe},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,520,1",
        f"Style: Credit,{font},42,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,8,40,40,70,1",
        f"Style: Hook,{font},110,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,9,4,5,60,60,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    # Wort-für-Wort-Untertitel
    n = max(1, int(woerter_pro_zeile))
    for i in range(0, len(words), n):
        chunk = words[i:i + n]
        for j, w in enumerate(chunk):
            start = w["start"]
            end = chunk[j + 1]["start"] if j + 1 < len(chunk) else w["end"] + 0.15
            if i + n < len(words):
                end = min(end, words[i + n]["start"])
            if end <= start:
                continue
            parts = [
                f"{{\\c{hl}}}{_clean(x['text'])}{{\\c{farbe}}}" if k == j else _clean(x["text"])
                for k, x in enumerate(chunk)
            ]
            lines.append(f"Dialogue: 1,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{' '.join(parts)}")

    for start, end, text in credits:
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Credit,,0,0,0,,{text}")

    if hook:
        ende = min(3.0, gesamt)
        lines.append(
            f"Dialogue: 2,{_ts(0)},{_ts(ende)},Hook,,0,0,0,,"
            f"{{\\fad(0,300)\\t(0,250,\\fscx115\\fscy115)\\t(250,450,\\fscx100\\fscy100)}}{_clean(hook)}"
        )

    with open(pfad, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines) + "\n")
    return pfad
