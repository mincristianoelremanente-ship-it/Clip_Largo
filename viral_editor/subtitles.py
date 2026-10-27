"""Transcripción (faster-whisper, local) y subtítulos estilo viral (ASS con palabra resaltada)."""
from __future__ import annotations


def transcribe(path, model_size: str = "small", language: str | None = None):
    """Devuelve (words, sentences, language). words=[(ini, fin, palabra)], sentences=[(ini, fin, texto)]."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(path), language=language, word_timestamps=True, vad_filter=True, beam_size=5
    )
    words, sentences = [], []
    for s in segments:
        sentences.append((s.start, s.end, s.text.strip()))
        for w in s.words or []:
            t = w.word.strip()
            if t:
                words.append((w.start, w.end, t))
    return words, sentences, info.language


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(sentences, path) -> None:
    lines = []
    for i, (a, b, txt) in enumerate(sentences, 1):
        lines += [str(i), f"{_srt_time(a)} --> {_srt_time(b)}", txt, ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def _clean(t: str) -> str:
    return t.upper().replace("{", "(").replace("}", ")").replace("\\", "")


def chunk_words(words, max_words: int = 3, max_chars: int = 20):
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x[2] for x in cur)
        if len(cur) >= max_words or len(text) >= max_chars or w[2].endswith((".", "?", "!", ",", ";", ":")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def write_ass(words, path, width: int, height: int, words_per_line: int = 3,
              hook: str | None = None, hook_seconds: float = 2.8, font: str = "Montserrat") -> None:
    vertical = height > width
    fs = 96 if vertical else 78
    mv = 480 if vertical else 110            # en vertical se deja libre la zona de la UI de Shorts
    fs_hook = 84 if vertical else 64
    mv_hook = 260 if vertical else 80

    out = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,{font},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,{mv},1",
        f"Style: Hook,{font},{fs_hook},&H00000000,&H000000FF,&H0000D6FF,&H00000000,-1,0,0,0,100,100,0,0,3,16,0,8,70,70,{mv_hook},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if hook:
        out.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(hook_seconds)},Hook,,0,0,0,,{{\\fad(120,250)}}{_clean(hook)}")

    hi = "{\\1c&H0000FFFF&\\fscx88\\fscy88\\t(0,90,\\fscx118\\fscy118)}"
    for chunk in chunk_words(words, words_per_line):
        for i, (a, b, _) in enumerate(chunk):
            end = chunk[i + 1][0] if i + 1 < len(chunk) else b
            if end - a < 0.06:
                end = a + 0.06
            parts = [(hi + _clean(w[2]) + "{\\r}") if j == i else _clean(w[2]) for j, w in enumerate(chunk)]
            out.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(end)},Sub,,0,0,0,,{' '.join(parts)}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
