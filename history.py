import json
import os
import sys
from datetime import datetime

from ai_processor import corregir_texto

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HISTORY_FILE = os.path.join(BASE_DIR, "historial.json")
MAX_ENTRIES = 100


def _leer() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _escribir(entradas: list) -> None:
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entradas, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, HISTORY_FILE)


def guardar_entrada(original: str, corregido: str, modo: str, idioma_salida: str,
                    motor: str = "", modelo_stt: str = "",
                    tiempo_stt: float = 0.0, tiempo_llm: float = 0.0,
                    tokens_prompt: int = 0, tokens_output: int = 0,
                    palabras_entrada: int = 0, palabras_salida: int = 0,
                    duracion_audio: float = 0.0,
                    prompt_usado: str = "",
                    texto_languagetool: str = "",
                    resultado_completo: bool = True) -> None:
    import difflib
    entradas = _leer()

    matcher = difflib.SequenceMatcher(None, original.split(), corregido.split())
    cambios = sum(t[0] != 'equal' for t in matcher.get_opcodes())
    densidad = round(cambios / duracion_audio, 2) if duracion_audio > 0 else 0.0

    entradas.append({
        "timestamp":           datetime.now().isoformat(timespec="seconds"),
        "original":            original,
        "corregido":           corregido,
        "modo":                modo,
        "idioma_salida":       idioma_salida,
        "motor":               motor,
        "modelo_stt":          modelo_stt,
        "tiempo_stt":          round(tiempo_stt, 2),
        "tiempo_llm":          round(tiempo_llm, 2),
        "tokens_prompt":       tokens_prompt,
        "tokens_output":       tokens_output,
        "palabras_entrada":    palabras_entrada,
        "palabras_salida":     palabras_salida,
        "duracion_audio":      round(duracion_audio, 2),
        "densidad_correccion": densidad,
        "prompt_usado":        prompt_usado,
        "texto_languagetool":  texto_languagetool,
        "resultado_completo":  resultado_completo,
    })
    if len(entradas) > MAX_ENTRIES:
        entradas = entradas[-MAX_ENTRIES:]
    _escribir(entradas)


def actualizar_version_usuario(timestamp: str, version_usuario: str) -> None:
    entradas = _leer()
    for entrada in entradas:
        if entrada.get("timestamp") == timestamp:
            entrada["version_usuario"] = version_usuario
            break
    _escribir(entradas)


def cargar_historial() -> list:
    return sorted(_leer(), key=lambda e: e.get("timestamp", ""), reverse=True)


def reprocesar_entrada(original: str, modo: str) -> str:
    return corregir_texto(original, modo=modo)
