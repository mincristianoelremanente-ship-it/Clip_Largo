import argparse

from .pipeline import Options, process


def main():
    p = argparse.ArgumentParser(description="Edita videos para YouTube de forma automática y viral.")
    p.add_argument("video", help="ruta del video (ej: input/mi_video.mp4)")
    p.add_argument("--speed", type=float, default=1.08)
    p.add_argument("--no-trim", action="store_true", help="no recortar silencios")
    p.add_argument("--silence-db", type=float, default=-32.0)
    p.add_argument("--min-silence", type=float, default=0.35)
    p.add_argument("--pad", type=float, default=0.10)
    p.add_argument("--zoom", type=float, default=1.10)
    p.add_argument("--format", choices=["auto", "horizontal", "vertical", "both"], default="auto")
    p.add_argument("--vertical-mode", choices=["blur", "crop"], default="blur")
    p.add_argument("--no-subs", action="store_true")
    p.add_argument("--words-per-line", type=int, default=3)
    p.add_argument("--model", default="small", help="tiny/base/small/medium")
    p.add_argument("--lang", default=None, help="es, en... (por defecto autodetecta)")
    p.add_argument("--hook", default=None)
    p.add_argument("--start", default=None, help="desde dónde empieza (90, 1:30 o 0:01:30)")
    p.add_argument("--end", default=None, help="dónde termina (mismo formato)")
    p.add_argument("--output", default="output")
    a = p.parse_args()
    formats = ("horizontal", "vertical") if a.format == "both" else (a.format,)
    process(Options(
        input_path=a.video, output_root=a.output, speed=a.speed, trim_silence=not a.no_trim,
        silence_db=a.silence_db, min_silence=a.min_silence, pad=a.pad, zoom=a.zoom, formats=formats,
        vertical_mode=a.vertical_mode, subtitles=not a.no_subs, words_per_line=a.words_per_line,
        whisper_model=a.model, language=a.lang, hook=a.hook,
        start=a.start, end=a.end,
    ))
