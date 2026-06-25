import json
import os
import sys
import re

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VOCAB_FILE = os.path.join(BASE_DIR, "vocabulario.json")

_DEFAULT = {
    "sustituciones": {},
    "initial_prompt": [
        "SpeakMe", "Whisper", "Ollama", "Python", "GitHub",
        "API", "JSON", "backend", "frontend", "dataset"
    ]
}

_cache = None


def cargar_vocabulario() -> dict:
    global _cache
    if not os.path.exists(VOCAB_FILE):
        _guardar(dict(_DEFAULT))
        _cache = dict(_DEFAULT)
        return _cache
    try:
        with open(VOCAB_FILE, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        _cache = dict(_DEFAULT)
    return _cache


def _guardar(data: dict) -> None:
    tmp = VOCAB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, VOCAB_FILE)


def aplicar_sustituciones(texto: str) -> str:
    vocab = _cache if _cache is not None else cargar_vocabulario()
    for origen, destino in vocab.get("sustituciones", {}).items():
        variantes = [v.strip() for v in origen.split(";")]
        for variante in variantes:
            if variante:
                texto = re.sub(re.escape(variante) + r'[\.\,\!\?]?', destino, texto, flags=re.IGNORECASE)
    return texto


def aplicar_sustituciones_ia(texto: str) -> str:
    import logging
    vocab = _cache if _cache is not None else cargar_vocabulario()
    sust = vocab.get("sustituciones_ia", {})
    logging.getLogger(__name__).info(f"aplicar_sustituciones_ia | entradas={len(sust)} | texto='{texto[:60]}'")
    for origen, destino in sust.items():
        variantes = [v.strip() for v in origen.split(";")]
        for variante in variantes:
            if variante:
                nuevo = re.sub(re.escape(variante) + r'[\.\,\!\?]?', destino, texto, flags=re.IGNORECASE)
                if nuevo != texto:
                    logging.getLogger(__name__).info(f"  MATCH: '{variante}' → '{destino}'")
                texto = nuevo
    return texto


