"""Pipeline: recorta silencios -> velocidad + zoom punch-in -> transcribe -> subtítulos -> formato -> audio."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from . import metadata, subtitles


@dataclass
class Options:
    input_path: str
    output_root: str = "output"
    speed: float = 1.08              # 1.0 = sin cambio (0.5–2.0)
    trim_silence: bool = True
    silence_db: float = -32.0        # más alto (ej -25) = corta más agresivo
    min_silence: float = 0.35        # silencios más largos que esto se eliminan
    pad: float = 0.10                # aire que se deja alrededor de cada frase
    zoom: float = 1.10               # punch-in en cortes alternados (1.0 = desactivado)
    formats: tuple = ("auto",)       # "auto" | "horizontal" | "vertical"
    vertical_mode: str = "blur"      # "blur" (fondo desenfocado) | "crop" (recorta centro)
    subtitles: bool = True
    words_per_line: int = 3
    whisper_model: str = "small"     # tiny/base/small/medium
    language: Optional[str] = None   # None = autodetectar ("es", "en"...)
    hook: Optional[str] = None       # texto grande los primeros 3s (si None lo propone Claude)
    color_boost: bool = True
    audio_polish: bool = True        # highpass + compresor + loudnorm -14 LUFS
    start: Optional[float] = None    # segundos desde donde empieza el video final (None = desde el inicio)
    end: Optional[float] = None      # segundos donde termina (None = hasta el final)


def parse_time(v):
    """Acepta 90, '90', '1:30' o '0:01:30' y devuelve segundos (o None)."""
    if v is None or str(v).strip() == "":
        return None
    parts = [float(x) for x in str(v).strip().split(":")]
    secs = 0.0
    for x in parts:
        secs = secs * 60 + x
    return secs


def _run(cmd, cwd=None):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)
    if p.returncode != 0:
        raise RuntimeError(f"Falló: {' '.join(map(str, cmd))}\n{p.stderr[-2500:]}")
    return p


def probe(path):
    """(ancho, alto, duración) ya considerando rotación del celular."""
    p = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
              "stream=width,height:stream_tags=rotate:stream_side_data=rotation:format=duration",
              "-of", "json", path])
    d = json.loads(p.stdout)
    st = d["streams"][0]
    w, h, rot = st["width"], st["height"], 0
    for sd in st.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if "rotate" in (st.get("tags") or {}):
        rot = int(st["tags"]["rotate"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    return w // 2 * 2, h // 2 * 2, float(d["format"]["duration"])


def detect_speech(path, duration, noise_db, min_silence, pad):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                        f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    silences = []
    for i, s in enumerate(starts):
        silences.append((max(s, 0.0), ends[i] if i < len(ends) else duration))
    speech, cur = [], 0.0
    for s, e in silences:
        if s - cur > 0.05:
            speech.append((cur, s))
        cur = e
    if duration - cur > 0.05:
        speech.append((cur, duration))
    # agregar "aire" y unir solapados
    padded = []
    for s, e in speech:
        s, e = max(0.0, s - pad), min(duration, e + pad)
        if padded and s <= padded[-1][1]:
            padded[-1] = (padded[-1][0], max(padded[-1][1], e))
        else:
            padded.append((s, e))
    padded = [(s, e) for s, e in padded if e - s >= 0.3]
    return padded or [(0.0, duration)]


def _cut(src, segments, w, h, o: Options, work: Path, log):
    parts = []
    for i, (s, e) in enumerate(segments):
        z = o.zoom if (o.zoom > 1.0 and i % 2 == 1) else 1.0
        vf = []
        if z > 1.0:
            vf.append(f"crop=trunc(iw/{z}/2)*2:trunc(ih/{z}/2)*2")
        vf += [f"scale={w}:{h}", "setsar=1", f"setpts=PTS/{o.speed}", "fps=30", "format=yuv420p"]
        out_dur = (e - s) / o.speed
        af = [f"atempo={o.speed}", "aresample=48000", "afade=t=in:st=0:d=0.015",
              f"afade=t=out:st={max(out_dur - 0.015, 0):.3f}:d=0.015"]
        seg = work / f"seg_{i:04}.mp4"
        _run(["ffmpeg", "-y", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", src,
              "-vf", ",".join(vf), "-af", ",".join(af),
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
              "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", seg])
        parts.append(seg)
        if i % 10 == 0:
            log(f"   cortando segmento {i + 1}/{len(segments)}")
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    cut = work / "cut.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", cut])
    return cut


def format_chain(src_w, src_h, fmt, mode):
    W, H = (1920, 1080) if fmt == "horizontal" else (1080, 1920)
    src_ar, dst_ar = src_w / src_h, W / H
    if abs(src_ar - dst_ar) < 0.02:
        return f"[0:v]scale={W}:{H}:flags=lanczos,setsar=1[f]", W, H
    if mode == "crop" and fmt == "vertical" and src_ar > dst_ar:
        return f"[0:v]crop='trunc(ih*{W}/{H}/2)*2':ih,scale={W}:{H}:flags=lanczos,setsar=1[f]", W, H
    return (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:5[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[f]"), W, H


def _render(cut, fmt, words, hook, o: Options, work: Path, out_path: Path, src_w, src_h):
    chain, W, H = format_chain(src_w, src_h, fmt, o.vertical_mode)
    post = []
    if o.color_boost:
        post += ["eq=contrast=1.05:saturation=1.18:brightness=0.01", "unsharp=5:5:0.6:5:5:0.0"]
    if o.subtitles and words:
        ass = work / f"subs_{fmt}.ass"
        subtitles.write_ass(words, ass, W, H, o.words_per_line, hook)
        post.append(f"ass={ass.name}")
    fc = f"{chain};[f]{','.join(post) if post else 'null'}[v]"
    cmd = ["ffmpeg", "-y", "-i", cut, "-filter_complex", fc, "-map", "[v]", "-map", "0:a"]
    if o.audio_polish:
        cmd += ["-af", "highpass=f=70,acompressor=threshold=-18dB:ratio=3:attack=5:release=80,"
                       "loudnorm=I=-14:TP=-1.5:LRA=11"]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path]
    _run(cmd, cwd=work)


def process(o: Options, log: Callable[[str], None] = print) -> dict:
    src = Path(o.input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    day = datetime.now().strftime("%Y%m%d")
    stem = re.sub(r"[^\w\-]+", "_", src.stem)[:60]
    out_dir = Path(o.output_root) / day / stem
    if out_dir.exists():
        out_dir = out_dir.with_name(f"{stem}_{datetime.now():%H%M%S}")
    out_dir.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="viral_"))
    try:
        w, h, dur = probe(src)
        log(f"📹 {src.name}: {w}x{h}, {dur:.0f}s")

        t0 = max(0.0, parse_time(o.start) or 0.0)
        t1 = min(dur, parse_time(o.end) or dur)
        if t1 - t0 < 1.0:
            raise ValueError(f"Rango inválido: inicio={t0:.1f}s, fin={t1:.1f}s (el video dura {dur:.1f}s)")
        if t0 > 0 or t1 < dur:
            log(f"🎯 Usando solo de {t0:.1f}s a {t1:.1f}s")

        if o.trim_silence:
            log("✂️  Detectando silencios...")
            segments = detect_speech(src, dur, o.silence_db, o.min_silence, o.pad)
            segments = [(max(s, t0), min(e, t1)) for s, e in segments if min(e, t1) - max(s, t0) >= 0.3]
            segments = segments or [(t0, t1)]
        else:
            segments = [(t0, t1)]
        kept = sum(e - s for s, e in segments)
        log(f"   {len(segments)} segmentos, quedan {kept:.0f}s de {t1 - t0:.0f}s")

        log(f"🎞️  Aplicando velocidad x{o.speed} y zoom...")
        cut = _cut(src, segments, w, h, o, work, log)
        cut_dur = probe(cut)[2]

        log(f"🗣️  Transcribiendo (modelo {o.whisper_model})...")
        words, sentences, lang = subtitles.transcribe(cut, o.whisper_model, o.language)
        text = " ".join(s[2] for s in sentences)
        if sentences:
            subtitles.write_srt(sentences, out_dir / "subtitulos.srt")

        log("💡 Generando títulos, hook y prompt de miniatura...")
        meta = metadata.generate(text, lang, cut_dur, o.hook)
        (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "metadata.md").write_text(metadata.to_markdown(meta), encoding="utf-8")
        (out_dir / "thumbnail_prompt.txt").write_text(meta.get("thumbnail_prompt", ""), encoding="utf-8")

        formats = []
        for f in o.formats:
            f = ("vertical" if w < h else "horizontal") if f == "auto" else f
            if f not in formats:
                formats.append(f)
        videos = {}
        for f in formats:
            log(f"🎬 Renderizando versión {f}...")
            path = out_dir / f"{stem}_{f}.mp4"
            _render(cut, f, words, meta.get("hook"), o, work, path, w, h)
            videos[f] = str(path)

        thumbs = out_dir / "frames_miniatura"
        thumbs.mkdir()
        for k, frac in enumerate((0.1, 0.3, 0.5, 0.7), 1):
            _run(["ffmpeg", "-y", "-ss", f"{cut_dur * frac:.2f}", "-i", cut, "-frames:v", "1", "-q:v", "2",
                  thumbs / f"frame_{k}.jpg"])

        log(f"✅ Listo: {out_dir}")
        return {"out_dir": str(out_dir), "videos": videos, "metadata": meta,
                "original_s": dur, "final_s": cut_dur}
    finally:
        shutil.rmtree(work, ignore_errors=True)
