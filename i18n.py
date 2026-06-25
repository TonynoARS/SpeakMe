import json
import os
import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_strings = {}
_lang = "es"

def set_lang(lang: str):
    global _strings, _lang
    _lang = lang
    path = os.path.join(BASE_DIR, "locales", f"{lang}.json")
    with open(path, encoding="utf-8") as f:
        _strings = json.load(f)

def t(key: str, **kwargs) -> str:
    text = _strings.get(key, key)
    return text.format(**kwargs) if kwargs else text

# Cargar idioma por defecto al importar
set_lang("es")
