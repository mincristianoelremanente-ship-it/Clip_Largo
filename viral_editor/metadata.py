"""Títulos, descripción, tags, hook y PROMPT DE MINIATURA. Usa Claude si hay ANTHROPIC_API_KEY."""
from __future__ import annotations

import json
import os

PROMPT = """Sos un experto en crecimiento de canales de YouTube. Te paso la transcripción de un video
(idioma: {lang}, duración: {dur:.0f}s). Respondé SOLO con un JSON válido (sin markdown) con estas claves:

- "titles": 5 títulos distintos, max 60 caracteres, con curiosidad/beneficio claro, sin clickbait falso.
- "hook": frase de máximo 6 palabras para mostrar en pantalla los primeros 3 segundos (en el idioma del video).
- "description": descripción de YouTube (primeras 2 líneas muy fuertes, resumen, llamado a suscribirse, 3 hashtags al final).
- "tags": lista de 15 tags.
- "thumbnail_text": máximo 3 palabras en MAYÚSCULAS para la miniatura.
- "thumbnail_prompt": prompt EN INGLÉS para un generador de imágenes, miniatura 16:9 (1280x720): sujeto principal con
  expresión exagerada, composición con regla de tercios (rostro a un lado, texto al otro), colores saturados de alto
  contraste, fondo simple y desenfocado, iluminación dramática con rim light, estilo foto hiperrealista de YouTuber,
  incluí el texto exacto de thumbnail_text en tipografía bold con contorno, y terminá con "no watermark, no logo, sharp".
- "shorts_ideas": 3 ideas de clips cortos [{{"momento": "...", "idea": "..."}}].
- "pinned_comment": comentario fijado que genere conversación.

TRANSCRIPCIÓN:
{text}
"""


def _fallback(text: str, lang: str, hook: str | None) -> dict:
    first = " ".join(text.split()[:12]) or "Tu tema acá"
    return {
        "titles": [first[:60]],
        "hook": hook or "MIRÁ ESTO",
        "description": "(Definí ANTHROPIC_API_KEY para generar descripción automática)\n\n" + text[:300],
        "tags": [],
        "thumbnail_text": "MIRÁ ESTO",
        "thumbnail_prompt": (
            "YouTube thumbnail, 16:9, 1280x720. Close-up of a person with an exaggerated surprised expression on the "
            "right third of the frame, looking at camera. Left side: huge bold white text with thick black outline "
            "reading 'MIRÁ ESTO'. Topic: " + first + ". Highly saturated colors, strong contrast, dramatic rim "
            "lighting, simple blurred background, hyper-realistic, sharp, no watermark, no logo."
        ),
        "shorts_ideas": [],
        "pinned_comment": "",
    }


def generate(text: str, lang: str, duration: float, hook: str | None = None) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not (key and text.strip()):
        return _fallback(text, lang, hook)
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=os.environ.get("VIRAL_LLM_MODEL", "claude-sonnet-5-5"),
            max_tokens=2500,
            messages=[{"role": "user", "content": PROMPT.format(lang=lang, dur=duration, text=text[:12000])}],
        )
        raw = resp.content[0].text
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        if hook:
            data["hook"] = hook
        return data
    except Exception as e:  # noqa: BLE001
        print(f"[metadata] Claude falló ({e}); uso plantilla básica.")
        return _fallback(text, lang, hook)


def to_markdown(d: dict) -> str:
    L = ["# Títulos", *[f"{i}. {t}" for i, t in enumerate(d.get("titles", []), 1)], "",
         f"# Hook (primeros 3s)\n{d.get('hook', '')}", "",
         f"# Descripción\n{d.get('description', '')}", "",
         "# Tags\n" + ", ".join(d.get("tags", [])), "",
         f"# Texto de miniatura\n{d.get('thumbnail_text', '')}", "",
         f"# Prompt de miniatura\n{d.get('thumbnail_prompt', '')}", ""]
    if d.get("shorts_ideas"):
        L += ["# Ideas para Shorts", *[f"- {s.get('momento', '')}: {s.get('idea', '')}" for s in d["shorts_ideas"]], ""]
    if d.get("pinned_comment"):
        L += ["# Comentario fijado", d["pinned_comment"], ""]
    return "\n".join(L)
