from pathlib import Path

import streamlit as st

from viral_editor.pipeline import Options, process

st.set_page_config(page_title="Viral Editor", page_icon="🎬", layout="wide")
st.title("🎬 Viral Editor para YouTube")

INPUT = Path("input")
INPUT.mkdir(exist_ok=True)

with st.sidebar:
    st.header("Ajustes")
    speed = st.slider("Velocidad", 1.0, 1.5, 1.08, 0.01)
    trim = st.checkbox("Recortar silencios", True)
    silence_db = st.slider("Umbral de silencio (dB)", -50, -15, -32, help="Más alto = corta más agresivo")
    min_silence = st.slider("Silencio mínimo a cortar (s)", 0.15, 1.0, 0.35, 0.05)
    zoom = st.slider("Zoom punch-in en cortes", 1.0, 1.3, 1.10, 0.01)
    fmt = st.selectbox("Formato", ["auto", "horizontal", "vertical", "both"])
    vmode = st.selectbox("Vertical desde horizontal", ["blur", "crop"])
    subs = st.checkbox("Subtítulos con palabra resaltada", True)
    wpl = st.slider("Palabras por línea", 1, 5, 3)
    model = st.selectbox("Modelo Whisper", ["tiny", "base", "small", "medium"], index=2)
    lang = st.text_input("Idioma (vacío = autodetectar)", "")
    hook = st.text_input("Hook en pantalla (vacío = lo propone Claude)", "")
    start = st.text_input("Empieza en (ej: 1:30, vacío = desde el inicio)", "")
    end = st.text_input("Termina en (ej: 12:45, vacío = hasta el final)", "")

up = st.file_uploader("Subí un video", type=["mp4", "mov", "mkv", "webm"])
existing = sorted(p.name for p in INPUT.glob("*") if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"})
choice = st.selectbox("…o elegí uno de la carpeta input/", ["—"] + existing)

if st.button("🚀 Editar", type="primary"):
    if up:
        target = INPUT / up.name
        target.write_bytes(up.getbuffer())
    elif choice != "—":
        target = INPUT / choice
    else:
        st.error("Subí o elegí un video.")
        st.stop()

    opts = Options(
        input_path=str(target), speed=speed, trim_silence=trim, silence_db=float(silence_db),
        min_silence=min_silence, zoom=zoom,
        formats=("horizontal", "vertical") if fmt == "both" else (fmt,),
        vertical_mode=vmode, subtitles=subs, words_per_line=wpl, whisper_model=model,
        language=lang or None, hook=hook or None,
        start=start or None, end=end or None,
    )
    with st.status("Procesando…", expanded=True) as status:
        res = process(opts, log=st.write)
        status.update(label="Listo ✅", state="complete")

    st.success(f"Guardado en `{res['out_dir']}` — {res['original_s']:.0f}s → {res['final_s']:.0f}s")
    cols = st.columns(max(len(res["videos"]), 1))
    for col, (name, path) in zip(cols, res["videos"].items()):
        col.subheader(name)
        col.video(path)
    meta = res["metadata"]
    st.subheader("Títulos")
    for t in meta.get("titles", []):
        st.write(f"- {t}")
    st.subheader("Prompt de miniatura")
    st.code(meta.get("thumbnail_prompt", ""), language=None)
    with st.expander("Descripción, tags e ideas"):
        st.text(meta.get("description", ""))
        st.write(", ".join(meta.get("tags", [])))
