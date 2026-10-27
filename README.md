# 🎬 Viral Editor para YouTube

Toma un video y lo deja listo para YouTube/Shorts:

- Recorta silencios y "ehh..." muertos
- Velocidad (1.08x por defecto) y zoom punch-in en cortes alternados
- Subtítulos grandes, 3 palabras por línea, con la palabra actual resaltada en amarillo
- Hook en pantalla los primeros 3 segundos
- Formato vertical 9:16, horizontal 16:9 o ambos (fondo desenfocado o recorte centrado)
- Color más vivo, nitidez y audio pulido (compresor + volumen -14 LUFS)
- Títulos, descripción, tags, ideas de Shorts y **prompt de miniatura** (con Claude)
- 4 frames del video para usar como referencia de la miniatura

## Salida

Todo se guarda particionado por fecha:

```
output/20261026/<nombre_del_video>/
├── <nombre>_vertical.mp4
├── <nombre>_horizontal.mp4
├── subtitulos.srt
├── metadata.md / metadata.json
├── thumbnail_prompt.txt
└── frames_miniatura/
```

## Usar en GitHub Codespaces

1. Subí esta carpeta a un repo nuevo de GitHub.
2. (Opcional, para títulos y prompt de miniatura con IA) Repo → Settings → Secrets and variables → **Codespaces** → agregá `ANTHROPIC_API_KEY`.
3. Botón verde **Code → Codespaces → Create codespace**. Se instala solo ffmpeg, fuentes y dependencias.
4. Arrastrá tu video a la carpeta `input/`.
5. En la terminal:

```bash
streamlit run app.py          # interfaz web (se abre en el puerto 8501)
# o por línea de comandos:
python -m viral_editor input/mi_video.mp4
python -m viral_editor input/mi_video.mp4 --format both --speed 1.12 --silence-db -28
```

Sin `ANTHROPIC_API_KEY` todo funciona igual, pero el prompt de miniatura y los títulos son una plantilla básica.

## Ajustes útiles

| Opción | Qué hace |
|---|---|
| `--speed 1.1` | velocidad |
| `--silence-db -28` | más alto = corta más agresivo (default -32) |
| `--min-silence 0.3` | silencio mínimo que se corta |
| `--zoom 1.15` / `--zoom 1.0` | punch-in / desactivarlo |
| `--format auto/horizontal/vertical/both` | auto = respeta la orientación del original |
| `--vertical-mode blur/crop` | fondo desenfocado o recorte del centro |
| `--model medium` | transcripción más precisa (más lenta) |
| `--hook "TEXTO"` | hook manual |
| `--start 1:30` / `--end 12:45` | usar solo ese tramo del video (acepta `90`, `1:30`, `0:01:30`) |

## Notas

- Un video de 7 min tarda unos minutos en una máquina de 4 cores; el modelo `small` de Whisper se descarga la primera vez.
- Para Shorts el video debe durar menos de 3 minutos.
- El video debe tener pista de audio.
