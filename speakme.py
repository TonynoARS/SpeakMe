import threading
import tempfile
import wave
import time
import os
import sys
from datetime import datetime
import subprocess
import ctypes
import win32gui
import pyautogui
import pyaudio
from faster_whisper import WhisperModel
from pynput import mouse, keyboard
import tkinter as tk
import sv_ttk
from tkinter import simpledialog, ttk
import json
import logging

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = BASE_DIR

logging.basicConfig(
    filename=os.path.join(BASE_DIR, "speakme.log"),
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)
log = logging.getLogger()

# Ocultar consola si estamos en modo congelado (ejecutable)
if getattr(sys, "frozen", False):
    kernel32 = ctypes.WinDLL("kernel32")
    user32 = ctypes.WinDLL("user32")
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE

import ai_processor
from ai_processor import corregir_texto, MODOS, cerrar_ollama
import pyperclip


def inyectar_texto(texto):
    pyperclip.copy(texto)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")


from config_window import ConfigWindow, _whisper_repo_id, _renderizar_markdown
from vocabulary import aplicar_sustituciones
from history import guardar_entrada

try:
    from onnx_asr import load_model as parakeet_load_model

    _PARAKEET_DISPONIBLE = True
except ImportError:
    _PARAKEET_DISPONIBLE = False

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

NOTAS_FILE = os.path.join(BASE_DIR, "notas.json")


def _leer_notas():
    if not os.path.exists(NOTAS_FILE):
        return []
    try:
        with open(NOTAS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _guardar_notas(notas):
    tmp = NOTAS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(notas, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, NOTAS_FILE)


CONFIG_DEFAULT = {
    "trigger_type": "teclado",
    "trigger_button": "middle",
    "trigger_tecla": "ctrl_r",
    "modo": "normal_stt",
    "modo_ia": "normal_stt",
    "idioma": "es",
    "idioma_salida": "es",
    "idioma_app": "es",
    "inicio_windows": False,
    "widget_visible": True,
    "widget_posicion": "centro",
    "widget_color_inactivo": "#ffffff",
    "widget_vram": False,
    "widget_motor": True,
    "widget_size": "normal",
    "widget_topmost": True,
    "widget_notas": False,
    "stt_beam_size": 3,
    "modo_grabacion": "auto",
    "umbral_auto_ms": 300,
    "mic_index": 0,
    "atajo_correccion": "",
    "atajo_config": "",
    "atajo_toggle": "",
    "atajo_modo_siguiente": "",
    "atajo_nota": "",
    "atajo_grabar": "ctrl_r",
    "stt_motor": "local_cpu",
    "stt_modelo": "base",
    "ia_motor": "gemini",
    "ia_modelo": "",
    "openai_key": "",
    "groq_key": "",
    "gemini_key": "",
    "modo_avanzado": False,
    "ia_activo": False,
    "iniciar_minimizado": False,
    "languagetool_activo": False,
    "fallback_activo": False,
    "fallback_ollama": False,
    "fallback_groq": False,
    "fallback_gemini": False,
    "fallback_openai": False,
    "debug_mode": False,
    "sonido_grabacion": True,
    "autoenter_global": False,
    "autoenter_global_delay": 1,
    "tema": "light",
    "gemini_rpm_limite": 14,
    "groq_rpm_limite": 28,
    "gemini_rpd_limite": 500,
    "groq_rpd_limite": 1200,
    "openai_rpm_limite": 15,
    "openai_rpd_limite": 10000,
    "ollama_keep_alive": False,
    "gemini_model": "gemini-2.0-flash-lite",
    "groq_model": "llama-3.3-70b-versatile",
    "openai_model": "gpt-4.1-mini",
    "gemini_tier": "gratuito",
    "groq_tier": "gratuito",
    "openai_tier": "pago",
    "gemini_tpm_limite": "1000",
    "gemini_tpd_limite": "1500",
    "groq_tpm_limite": "12000",
    "groq_tpd_limite": "100000",
    "openai_tpm_limite": "40000",
    "openai_tpd_limite": "0",
    "gemini_aviso_tpm_activo": True,
    "gemini_aviso_tpm_porcentaje": 80,
    "groq_aviso_tpm_activo": True,
    "groq_aviso_tpm_porcentaje": 80,
    "openai_aviso_tpm_activo": False,
    "openai_aviso_tpm_porcentaje": 80,
    "groq_max_words_chunk": "2",
    "gemini_max_words_chunk": "800",
    "openai_max_words_chunk": "99999",
    "ollama_disponible": False,
    "openai_coste_sesion": 0,
    "bienvenida_mostrada": False,
}


def cargar_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    guardar_config(CONFIG_DEFAULT.copy())
    return CONFIG_DEFAULT.copy()


def guardar_config(config):
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG_FILE)


def _aplicar_languagetool(texto, idioma="es"):
    try:
        import language_tool_python

        if not hasattr(_aplicar_languagetool, "_tool"):
            tool = language_tool_python.LanguageTool(idioma)
            tool.disable_spellchecking()
            _aplicar_languagetool._tool = tool
        return _aplicar_languagetool._tool.correct(texto)
    except Exception as e:
        logging.getLogger(__name__).warning(f"LanguageTool error: {e}")
        return texto


class SpeakMe:
    def __init__(self):
        self.config = cargar_config()
        self.grabando = False
        self.activo = True
        self.frames = []
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.modelo = None
        self.root = None
        self.ultimo_corregido = ""
        self.tray_icon = None
        self.stt_nombre = "Whisper GPU"
        self.estado_win = None
        self._listeners = []
        self.stt_backend = "whisper"
        self._audio_cache_dir = os.path.join(BASE_DIR, "audio_cache")
        os.makedirs(self._audio_cache_dir, exist_ok=True)
        self._ollama_disponible = False
        threading.Thread(target=self._detectar_ollama, daemon=True).start()

    def _detectar_ollama(self):
        try:
            import subprocess

            subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._ollama_disponible = True
        except Exception as e:
            self._ollama_disponible = False
            log.error(f"Ollama detección falló: {type(e).__name__}: {e}")
        self.config["ollama_disponible"] = self._ollama_disponible
        log.info(f"Ollama disponible: {self._ollama_disponible}")

    def _aplicar_tema(self, tema: str):
        sv_ttk.set_theme(tema)
        style = ttk.Style()
        style.configure("Accent.TButton", background="#7C5EF7", foreground="white")
        style.configure("Main.Accent.TButton", background="#7C5EF7", foreground="white")
        style.map(
            "Accent.TButton", background=[("active", "#6B4FE0"), ("pressed", "#5B40D0")]
        )
        style.map(
            "Main.Accent.TButton",
            background=[("active", "#6B4FE0"), ("pressed", "#5B40D0")],
        )

        if tema == "dark":
            style.configure(".", background="#0D0D0D", foreground="#F0F0F0")
            style.configure("TFrame", background="#0D0D0D")
            style.configure("TLabelframe", background="#0D0D0D", foreground="#F0F0F0")
            style.configure(
                "TLabelframe.Label", background="#0D0D0D", foreground="#7C5EF7"
            )
            style.configure("TLabel", background="#0D0D0D", foreground="#F0F0F0")
            style.configure("TNotebook", background="#0D0D0D")
            style.configure("TNotebook.Tab", background="#1A1A1A", foreground="#F0F0F0")
            style.map(
                "TNotebook.Tab",
                background=[("selected", "#7C5EF7")],
                foreground=[("selected", "#FFFFFF")],
            )
            style.configure("TCheckbutton", background="#0D0D0D", foreground="#F0F0F0")
            style.configure("TRadiobutton", background="#0D0D0D", foreground="#F0F0F0")
            style.configure("TSeparator", background="#7C5EF7")

        try:
            hwnd = self.root.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                35,
                ctypes.byref(ctypes.c_int(0x00F75E7C)),
                ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass

    def _mostrar_msg_carga(self, texto):
        try:
            self._actualizar_splash(texto, 30)
        except Exception:
            pass
        try:
            self._estado_label.configure(text=texto)
        except Exception:
            pass

    def cargar_modelo(self):
        stt_motor = self.config.get("stt_motor", "local_gpu")
        modelo_id = self.config.get("stt_modelo", "large-v3-turbo")

        if stt_motor in ("parakeet", "parakeet_gpu") and _PARAKEET_DISPONIBLE:
            gpu = stt_motor == "parakeet_gpu"
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if gpu
                else ["CPUExecutionProvider"]
            )
            label = "GPU" if gpu else "CPU"
            log.info(f"Cargando Parakeet TDT v3 {label}...")
            try:
                self.modelo = parakeet_load_model(
                    "nemo-parakeet-tdt-0.6b-v3",
                    providers=providers,
                )
                self.stt_backend = "parakeet"
                self.stt_nombre = f"Parakeet {label}"
                log.info(f"Parakeet TDT v3 {label} cargado correctamente")
            except Exception as e:
                log.error(
                    f"Error cargando Parakeet {label}: {e} — fallback a Whisper GPU"
                )
                self.stt_backend = "whisper"
                self.stt_nombre = "Whisper GPU"
                self._cargar_whisper(modelo_id, "local_gpu")
        elif stt_motor in ("parakeet", "parakeet_gpu") and not _PARAKEET_DISPONIBLE:
            log.warning(
                "stt_motor=parakeet pero onnx_asr no está instalado — fallback a Whisper GPU"
            )
            self.stt_backend = "whisper"
            self.stt_nombre = "Whisper GPU"
            self._cargar_whisper(modelo_id, "local_gpu")
        else:
            self.stt_backend = "whisper"
            self.stt_nombre = (
                "Whisper GPU" if stt_motor == "local_gpu" else "Whisper CPU"
            )
            self._cargar_whisper(modelo_id, stt_motor)

        self.root.after(0, self._cerrar_splash)

    def _cargar_whisper(self, modelo_id, stt_motor):
        device = "cuda" if stt_motor == "local_gpu" else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        log.info(
            f"Cargando modelo Whisper: {modelo_id} | device={device} | compute_type={compute_type}"
        )
        try:
            self.modelo = WhisperModel(
                modelo_id,
                device=device,
                compute_type=compute_type,
                local_files_only=True,
            )
            log.info(f"Modelo cargado desde caché local: {modelo_id}")
        except Exception:
            log.info(f"Modelo {modelo_id} no está en caché — descargando...")
            self._mostrar_msg_carga(f"Descargando modelo {modelo_id}...")
            self.modelo = WhisperModel(
                modelo_id, device=device, compute_type=compute_type
            )
            log.info(f"Modelo descargado y cargado: {modelo_id}")

    def iniciar_grabacion(self):
        if not self.activo or self.grabando or not self.modelo:
            return
        self.ventana_activa = win32gui.GetForegroundWindow()
        self.grabando = True
        self.frames = []
        mic_index = self.config.get("mic_index", 1)
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            input_device_index=mic_index,
            frames_per_buffer=1024,
        )
        log.info(f"Grabación iniciada | mic_index={mic_index} | 16000 Hz")
        self.actualizar_icono("grabando")
        threading.Thread(target=self._grabar, daemon=True).start()

    def _guardar_audio_cache(self, frames):
        try:
            from pathlib import Path

            archivos = sorted(Path(self._audio_cache_dir).glob("*.wav"))
            while len(archivos) >= 5:
                archivos[0].unlink()
                archivos = archivos[1:]
            nombre = os.path.join(
                self._audio_cache_dir, f"audio_{int(time.time())}.wav"
            )
            with wave.open(nombre, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"".join(frames))
        except Exception as e:
            log.warning(f"Error guardando audio cache: {e}")

    def _grabar(self):
        while self.grabando:
            data = self.stream.read(1024, exception_on_overflow=False)
            self.frames.append(data)

    def detener_y_procesar(self):
        if not self.grabando:
            return
        self.grabando = False
        time.sleep(0.1)
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.actualizar_icono("procesando")
        frames_snapshot = list(self.frames)
        threading.Thread(target=self._procesar, daemon=True).start()
        threading.Thread(
            target=self._guardar_audio_cache, args=(frames_snapshot,), daemon=True
        ).start()

    def _procesar(self):
        if self.modelo is None:
            log.error("_procesar: modelo es None, abortando")
            self.actualizar_icono("inactivo")
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(b"".join(self.frames))

        idioma_detectado = self.config.get("idioma", "auto")
        log.info(
            f"STT | backend={self.stt_backend} | modelo={self.config.get('stt_modelo', '?')} | device={'cuda' if self.config.get('stt_motor') == 'local_gpu' else 'cpu'} | compute={('float16' if self.config.get('stt_motor') == 'local_gpu' else 'int8') if self.stt_backend == 'whisper' else 'onnx'}"
        )
        if self.stt_backend == "parakeet":
            t_stt_ini = time.monotonic()
            texto_crudo = self.modelo.recognize(tmp_path)
            if isinstance(texto_crudo, list):
                texto_crudo = " ".join(texto_crudo)
            texto_crudo = texto_crudo.strip()
            t_stt_fin = time.monotonic()
        else:
            stt_motor = self.config.get("stt_motor", "local_gpu")
            beam_size = self.config.get("stt_beam_size", 1)
            if stt_motor == "local_cpu" and beam_size > 2:
                beam_size = 2
            cfg_idioma = self.config.get("idioma", "es")
            t_stt_ini = time.monotonic()
            segments, info = self.modelo.transcribe(
                tmp_path,
                language=None if cfg_idioma == "auto" else cfg_idioma,
                beam_size=beam_size,
                vad_filter=True,
            )
            texto_crudo = " ".join([s.text for s in segments]).strip()
            t_stt_fin = time.monotonic()
            idioma_detectado = info.language if cfg_idioma == "auto" else cfg_idioma
        texto_crudo = texto_crudo.rstrip(".").strip()
        texto_whisper_puro = texto_crudo
        texto_crudo = aplicar_sustituciones(texto_crudo)
        texto_pre_lt = texto_crudo
        texto_post_lt = texto_crudo
        if self.config.get("languagetool_activo", False):
            texto_post_lt = _aplicar_languagetool(texto_crudo, idioma_detectado)
            texto_crudo = texto_post_lt
        os.unlink(tmp_path)

        if not texto_crudo:
            self.actualizar_icono("inactivo")
            return

        modo_activo = self.config.get("modo_ia", "normal_stt")
        modo_cfg = dict(MODOS.get(modo_activo, {}))
        modo_cfg["gemini_model"] = self.config.get(
            "gemini_model", "gemini-2.5-flash-lite"
        )
        modo_cfg["groq_model"] = self.config.get("groq_model", "llama-3.1-8b-instant")
        if not self.config.get("ia_activo", True):
            ia_motor = "none"
        else:
            ia_motor = (
                modo_cfg.get("motor")
                or modo_cfg.get("modelo")
                or self.config.get("ia_motor", "ollama")
            )
        groq_key = self.config.get("groq_key", "")
        gemini_key = self.config.get("gemini_key", "")
        openai_key = self.config.get("openai_key", "")
        log.info(
            f"Dictado procesado | modo={modo_activo} | motor={ia_motor} | "
            f"stt={self.stt_nombre} | idioma={idioma_detectado} | palabras={len(texto_crudo.split())}"
        )
        log.info(
            f"_procesar | ia_motor={self.config.get('ia_motor')} | modo={self.config.get('modo_ia')} | motor_activo={self.config.get('motor_ia_activo')}"
        )
        log.info(
            f"texto_entrada | {len(texto_crudo)} chars | {repr(texto_crudo[:120])}"
        )
        t_llm_ini = time.monotonic()
        if not self.config.get("ia_activo", True) or ia_motor == "none":
            texto_corregido = texto_crudo
            ai_processor.ultimo_motor_usado = "none"
        else:
            motor_activo = self.config.get("ia_motor", "gemini")
            if self.config.get(f"{motor_activo}_aviso_tpm_activo", False):
                tpm_limite = int(self.config.get(f"{motor_activo}_tpm_limite", 99999))
                consumo = ai_processor._consumo_medio_tpm()
                if tpm_limite > 0 and consumo >= tpm_limite:
                    msg = " ⚠️ Límite TPM superado "
                    self.root.after(0, lambda m=msg: self._mostrar_notif_error(m))
            texto_corregido = corregir_texto(
                texto_crudo,
                modo=modo_activo,
                ia_motor=ia_motor,
                groq_key=groq_key,
                gemini_key=gemini_key,
                openai_key=openai_key,
                idioma=idioma_detectado,
                gemini_rpm_limite=self.config.get("gemini_rpm_limite", 13),
                groq_rpm_limite=self.config.get("groq_rpm_limite", 28),
                openai_rpm_limite=self.config.get("openai_rpm_limite", 500),
                config=self.config,
            )
        t_llm_fin = time.monotonic()

        if ai_processor.ultimo_fue_fallback:
            origen = ai_processor.ultimo_motor_principal
            destino = ai_processor.ultimo_motor_usado
            self.root.after(
                0, lambda o=origen, d=destino: self._mostrar_toast_fallback(o, d)
            )
        elif ai_processor.ultimo_error_api == "429":
            log.warning(
                "⚠ Límite de API alcanzado (429) — el texto no fue procesado por el LLM"
            )

            def _notificar_limite():
                try:
                    self._estado_label.configure(
                        text="⚠ Límite API alcanzado", fg="#ff8800"
                    )
                    self.estado_win.after(3000, self._actualizar_texto_estado)
                except Exception:
                    pass

            self.root.after(0, _notificar_limite)
            self._mostrar_notif_error("⚠ Límite alcanzado — fallback activado")
        elif ai_processor.ultimo_error_api == "error":
            ai_processor.ultimo_motor_usado = "none"
            self._mostrar_toast_error(ia_motor)

        log.info(f"post_llm_raw   | {repr(texto_corregido[:120])}")

        # texto_corregido = re.sub(
        #     r'([a-záéíóúüñ])(\s{2,})([A-ZÁÉÍÓÚÜÑ])',
        #     lambda m: m.group(1) + ". " + m.group(3),
        #     texto_corregido)
        # log.info(f"post_re_espacios | {repr(texto_corregido[:120])}")

        if texto_corregido and texto_corregido[-1] not in ".!?…":
            texto_corregido += "."
        log.info(f"post_punto_final | {repr(texto_corregido[:120])}")
        self.ultimo_corregido = texto_corregido

        motor_usado = ai_processor.ultimo_motor_usado or ia_motor
        if (
            motor_usado in ("groq", "gemini", "openai")
            and self.config.get(f"{motor_usado}_tier", "gratuito") == "pago"
        ):
            try:
                precio_in = float(self.config.get(f"{motor_usado}_precio_entrada", 0))
                precio_out = float(self.config.get(f"{motor_usado}_precio_salida", 0))
                coste = (
                    ai_processor.ultimo_tokens_prompt * precio_in
                    + ai_processor.ultimo_tokens_output * precio_out
                ) / 1_000_000
                clave = f"{motor_usado}_coste_sesion"
                self.config[clave] = self.config.get(clave, 0.0) + coste
                guardar_config(self.config)
                log.info(
                    f"coste_sesion | motor={motor_usado} | coste={coste:.8f} | total={self.config[clave]:.6f}"
                )
            except Exception as e:
                log.warning(f"Error calculando coste: {e}")

        guardar_entrada(
            original=texto_whisper_puro,
            corregido=texto_corregido,
            modo="Sin IA"
            if not self.config.get("ia_activo", True)
            else MODOS.get(modo_activo, {}).get("nombre", modo_activo),
            idioma_salida=idioma_detectado,
            motor=ai_processor.ultimo_motor_usado or ia_motor,
            modelo_stt=self.stt_nombre,
            tiempo_stt=round(t_stt_fin - t_stt_ini, 2),
            tiempo_llm=round(t_llm_fin - t_llm_ini, 2),
            tokens_prompt=ai_processor.ultimo_tokens_prompt,
            tokens_output=ai_processor.ultimo_tokens_output,
            palabras_entrada=len(texto_whisper_puro.split()),
            palabras_salida=len(texto_corregido.split()),
            duracion_audio=round(len(self.frames) * 1024 / 16000, 2),
            prompt_usado=ai_processor.ultimo_prompt_usado,
            resultado_completo=ai_processor.ultimo_resultado_completo,
            texto_languagetool=texto_post_lt
            if (
                self.config.get("languagetool_activo", False)
                and texto_post_lt != texto_pre_lt
            )
            else (
                "__lt_activo__" if self.config.get("languagetool_activo", False) else ""
            ),
        )
        log.info(
            f"prompt_usado guardado | len={len(ai_processor.ultimo_prompt_usado)} chars | preview={ai_processor.ultimo_prompt_usado[:80]!r}"
        )
        self.root.after(0, self._actualizar_texto_estado)

        try:
            win32gui.SetForegroundWindow(self.ventana_activa)
        except Exception:
            pass
        inyectar_texto(texto_corregido)
        _ae_activo, _ae_delay = self._autoenter_get(self.config.get("modo_ia", ""))
        if _ae_activo:
            delay = _ae_delay
            self._autoenter_activo = True
            self._autoenter_cancelado = False
            for i in range(delay, 0, -1):
                if self._autoenter_cancelado:
                    break
                _fg = self.config.get("widget_color_inactivo", "#888888")
                self.root.after(
                    0,
                    lambda n=i, c=_fg: self._btn_autoenter.configure(
                        text=f"⏎{n}s", fg=c
                    ),
                )
                time.sleep(1)
            self._autoenter_activo = False
            self.root.after(0, self._actualizar_color_autoenter)
            if not self._autoenter_cancelado:
                from pynput.keyboard import Key, Controller

                Controller().press(Key.enter)
                Controller().release(Key.enter)
        self.actualizar_icono("inactivo")

    def abrir_correccion_manual(self):
        if not self.ultimo_corregido:
            return

        def show():
            nuevo = simpledialog.askstring(
                "SpeakMe — Corrección",
                "Último texto procesado:",
                initialvalue=self.ultimo_corregido,
                parent=self.root,
            )

        self.root.after(0, show)

    def _obtener_vram_libre(self):
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            mib = int(result.stdout.strip())
            return round(mib / 1024, 1)
        except Exception:
            return None

    def _actualizar_texto_estado(self):
        ia_activo = self.config.get("ia_activo", True)
        modo_key = self.config.get("modo_ia", "normal_stt")
        modo_nombre = (
            "Sin IA"
            if not ia_activo
            else MODOS.get(modo_key, {}).get("nombre", modo_key)
        )
        motor_nombres = {
            "gemini": "Gemini",
            "groq": "Groq",
            "ollama": "Ollama",
            "openai": "OpenAI",
            "none": "Sin IA",
        }
        if self.config.get("widget_motor", True):
            if not self.config.get("ia_activo", True):
                motor_actual = "none"
            else:
                motor_actual = ai_processor.ultimo_motor_usado or self.config.get(
                    "ia_motor", ""
                )
                for clave in motor_nombres:
                    if clave in motor_actual.lower():
                        motor_actual = clave
                        break
            motor_str = (
                f" | {motor_nombres.get(motor_actual, motor_actual)}"
                if motor_actual
                else ""
            )
        else:
            motor_str = ""
        if self.config.get("widget_vram", True):
            vram = self._obtener_vram_libre()
            vram_str = f" | {vram}GB" if vram is not None else " | —"
        else:
            vram_str = ""
        texto = f"{modo_nombre}{motor_str}{vram_str}"
        try:
            self._estado_label.configure(text=texto)
            self.estado_win.after(100, self._posicionar_widgets)
            self.estado_win.after(5000, self._actualizar_texto_estado)
        except Exception:
            pass
        try:
            self._actualizar_color_autoenter()
        except Exception:
            pass

    def _autoenter_get(self, modo_key=None):
        """Devuelve (activo, delay) del auto-enter global, igual para cualquier modo."""
        return (
            self.config.get("autoenter_global", False),
            self.config.get("autoenter_global_delay", 2),
        )

    def _autoenter_set(self, modo_key=None, **valores):
        if "auto_enter" in valores:
            self.config["autoenter_global"] = valores["auto_enter"]
        if "auto_enter_delay" in valores:
            self.config["autoenter_global_delay"] = valores["auto_enter_delay"]
        guardar_config(self.config)

    def _toggle_autoenter(self):
        if getattr(self, "_autoenter_activo", False):
            self._autoenter_cancelado = True
            return
        activo, _ = self._autoenter_get()
        self._autoenter_set(auto_enter=not activo)
        self._actualizar_color_autoenter()

    def _actualizar_color_autoenter(self):
        modo_key = self.config.get("modo_ia", "")
        activo, _ = self._autoenter_get(modo_key)
        color_comun = self.config.get("widget_color_inactivo", "#888888")
        try:
            self._btn_autoenter.configure(fg=color_comun if activo else "#444444")
        except Exception:
            pass

    def _guardar_modo_auto_enter(self, modo_key):
        modos_file = os.path.join(BASE_DIR, "modos.json")
        try:
            with open(modos_file, encoding="utf-8") as f:
                modos = json.load(f)
            if modo_key in modos:
                modos[modo_key]["auto_enter"] = MODOS[modo_key].get("auto_enter", False)
                modos[modo_key]["auto_enter_delay"] = MODOS[modo_key].get(
                    "auto_enter_delay", 2
                )
            tmp = modos_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(modos, f, indent=2, ensure_ascii=False)
            os.replace(tmp, modos_file)
        except Exception as e:
            log.warning(f"Error guardando auto_enter: {e}")

    def _mostrar_menu_autoenter(self, event=None):
        BG = "#1e1e2e"
        FG = "#aaaaaa"
        FG_A = "#ffffff"
        HOV = "#3a3a5e"

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg=BG)

        try:
            hwnd = ctypes.windll.user32.GetParent(popup.winfo_id()) or popup.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass

        modo_key = self.config.get("modo_ia", "")
        activo, delay = self._autoenter_get(modo_key)

        def _make_item(text, active=False, command=None):
            bg_item = "#2a2a3e" if active else BG
            fg_item = FG_A if active else FG
            lbl = tk.Label(
                popup,
                text=text,
                bg=bg_item,
                fg=fg_item,
                font=("Segoe UI Variable", self._widget_font_size),
                anchor="w",
                padx=12,
                pady=6,
                cursor="hand2",
            )
            lbl.pack(fill=tk.X)
            lbl.bind("<Enter>", lambda e, l=lbl: l.configure(bg=HOV))
            lbl.bind("<Leave>", lambda e, l=lbl, b=bg_item: l.configure(bg=b))
            if command:
                lbl.bind("<Button-1>", lambda e: command())
            return lbl

        def _toggle():
            a, _ = self._autoenter_get(modo_key)
            self._autoenter_set(modo_key, auto_enter=not a)
            self._actualizar_color_autoenter()
            popup.destroy()

        prefijo = "✓" if activo else " "
        _make_item(f"{prefijo} Auto Enter activo", active=activo, command=_toggle)

        tk.Frame(popup, bg="#333355", height=1).pack(fill=tk.X, padx=8, pady=2)

        delay_row = tk.Frame(popup, bg=BG)
        delay_row.pack(fill=tk.X, padx=12, pady=(4, 8))
        tk.Label(
            delay_row,
            text="Delay:",
            bg=BG,
            fg=FG,
            font=("Segoe UI Variable", self._widget_font_size),
        ).pack(side=tk.LEFT)

        for n in range(6):
            active_n = n == delay
            btn = tk.Label(
                delay_row,
                text=str(n),
                bg="#2a2a3e" if active_n else BG,
                fg=FG_A if active_n else FG,
                font=("Segoe UI Variable", self._widget_font_size),
                padx=6,
                cursor="hand2",
            )
            btn.pack(side=tk.LEFT, padx=2)

            def _set_delay(v=n):
                self._autoenter_set(modo_key, auto_enter_delay=v)
                popup.destroy()

            btn.bind("<Button-1>", lambda e, f=_set_delay: f())
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=HOV))
            btn.bind(
                "<Leave>",
                lambda e, b=btn, a=active_n: b.configure(bg="#2a2a3e" if a else BG),
            )

        popup.update_idletasks()
        w = popup.winfo_reqwidth()
        x = self._btn_autoenter.winfo_rootx()
        y = self.estado_win.winfo_y()

        # Si se sale por la derecha, abrir hacia la izquierda
        sw = self.estado_win.winfo_screenwidth()
        if x + w > sw:
            x = sw - w - 4

        popup.geometry(f"+{x}+{y - popup.winfo_reqheight() - 4}")
        popup.bind("<FocusOut>", lambda e: popup.destroy())
        popup.focus_set()

    def _redondear_esquinas(self, popup, w, h, radius=10):
        try:
            hwnd = ctypes.windll.user32.GetParent(popup.winfo_id()) or popup.winfo_id()
            region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w, h, radius, radius)
            ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
        except Exception:
            pass

    def _mostrar_menu_modos(self, event=None):
        try:
            with open(os.path.join(BASE_DIR, "modos.json"), encoding="utf-8") as f:
                modos_fresh = json.load(f)
        except Exception:
            modos_fresh = ai_processor.MODOS

        modo_actual = self.config.get("modo_ia", "normal_stt")
        ia_activo = self.config.get("ia_activo", True)
        favoritos = {k: v for k, v in modos_fresh.items() if v.get("favorito", False)}
        fuente = (
            favoritos
            if favoritos
            else {
                k: v
                for k, v in modos_fresh.items()
                if v.get("sistema", False) and k != "normal_stt"
            }
        )

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.85)
        popup.configure(bg="#1e1e2e")

        try:
            hwnd = ctypes.windll.user32.GetParent(popup.winfo_id()) or popup.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass

        # Modo Normal fijo siempre visible
        es_normal = not ia_activo
        prefijo = "✓" if es_normal else " "
        lbl_normal = tk.Label(
            popup,
            text=f"{prefijo} Normal (Sin IA)",
            bg="#2a2a3e" if es_normal else "#1e1e2e",
            fg="#ffffff" if es_normal else "#aaaaaa",
            font=("Segoe UI Variable", self._widget_font_size),
            anchor="w",
            padx=12,
            pady=6,
            cursor="hand2",
        )
        lbl_normal.pack(fill=tk.X)

        def _seleccionar_normal():
            self.config["ia_activo"] = False
            self.config["modo_ia"] = "normal_stt"
            guardar_config(self.config)
            self._actualizar_texto_estado()
            popup.destroy()

        lbl_normal.bind("<Enter>", lambda e: lbl_normal.configure(bg="#3a3a5e"))
        lbl_normal.bind(
            "<Leave>",
            lambda e: lbl_normal.configure(bg="#2a2a3e" if es_normal else "#1e1e2e"),
        )
        lbl_normal.bind("<Button-1>", lambda _: _seleccionar_normal())

        # Separador si hay modos IA
        if fuente:
            tk.Frame(popup, bg="#333355", height=1).pack(fill=tk.X, padx=8, pady=2)

        for k, v in fuente.items():
            nombre = v.get("nombre", k)
            es_actual = self.config.get("ia_activo", True) and (k == modo_actual)
            bg_item = "#2a2a3e" if es_actual else "#1e1e2e"
            fg_item = "#ffffff" if es_actual else "#aaaaaa"

            def _on_enter(e, lbl=None):
                lbl.configure(bg="#3a3a5e")

            def _on_leave(e, lbl=None, bg=bg_item):
                lbl.configure(bg=bg)

            def _seleccionar(key=k):
                self.config["ia_activo"] = True
                self._set_modo_ia(key)
                popup.destroy()

            lbl = tk.Label(
                popup,
                text=f"{'✓' if es_actual else ' '} {nombre}",
                bg=bg_item,
                fg=fg_item,
                font=("Segoe UI Variable", self._widget_font_size),
                anchor="w",
                padx=12,
                pady=6,
                cursor="hand2",
            )
            lbl.pack(fill=tk.X)
            lbl.bind("<Enter>", lambda e, l=lbl: _on_enter(e, l))
            lbl.bind("<Leave>", lambda e, l=lbl, b=bg_item: _on_leave(e, l, b))
            lbl.bind("<Button-1>", lambda e, key=k: _seleccionar(key))

        popup.update_idletasks()
        w = popup.winfo_reqwidth()
        h = popup.winfo_reqheight()
        self._redondear_esquinas(popup, w, h)
        wx = self.estado_win.winfo_x()
        ww = self.estado_win.winfo_width()
        x = wx + (ww - w) // 2
        y = self.estado_win.winfo_y() - h - 4
        popup.geometry(f"+{x}+{y}")

        popup.bind("<FocusOut>", lambda e: popup.destroy())
        popup.focus_set()

    def _mostrar_menu_opciones(self, event=None):
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.85)
        popup.configure(bg="#1e1e2e")

        try:
            hwnd = ctypes.windll.user32.GetParent(popup.winfo_id()) or popup.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass

        def _abrir_y_cerrar():
            popup.destroy()
            self._abrir_configuracion()

        lbl = tk.Label(
            popup,
            text="⚙️  Configuración",
            bg="#1e1e2e",
            fg="white",
            font=("Segoe UI Variable", 10),
            padx=16,
            pady=8,
            cursor="hand2",
            anchor="w",
        )
        lbl.pack(fill=tk.X)
        lbl.bind("<Button-1>", lambda e: _abrir_y_cerrar())
        lbl.bind("<Enter>", lambda e: lbl.configure(bg="#3a3a5e"))
        lbl.bind("<Leave>", lambda e: lbl.configure(bg="#1e1e2e"))

        popup.update_idletasks()
        w = popup.winfo_reqwidth()
        h = popup.winfo_reqheight()
        self._redondear_esquinas(popup, w, h)
        wx = self.estado_win.winfo_x()
        ww = self.estado_win.winfo_width()
        x = wx + (ww - w) // 2
        y = self.estado_win.winfo_y() - h - 4
        popup.geometry(f"+{x}+{y}")

        popup.bind("<FocusOut>", lambda e: popup.destroy())
        popup.focus_set()

    def _mostrar_toast_fallback(self, origen, destino):
        try:
            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.attributes("-alpha", 0.0)

            x = self.estado_win.winfo_x()
            y = self.estado_win.winfo_y() - 65
            toast.geometry(f"240x55+{x}+{y}")

            frame = tk.Frame(toast, bg="#1C1C1C", padx=16, pady=10)
            frame.pack(fill=tk.BOTH, expand=True)
            if destino == "Sin IA":
                msg_txt = f"⚠ {origen} no respondió — sin corrección IA"
            else:
                msg_txt = f"⚡ Fallback: {origen.title()} → {destino.title()}"
            tk.Label(
                frame,
                text=msg_txt,
                font=("Segoe UI Variable Display", 10),
                bg="#1C1C1C",
                fg="white",
            ).pack()

            # Esquinas redondeadas Windows 11
            hwnd = ctypes.windll.user32.GetParent(toast.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4
            )

            def fade_in(alpha=0.0):
                alpha = min(alpha + 0.1, 0.92)
                toast.attributes("-alpha", alpha)
                if alpha < 0.92:
                    toast.after(30, lambda: fade_in(alpha))

            def fade_out(alpha=0.92):
                alpha = max(alpha - 0.1, 0.0)
                toast.attributes("-alpha", alpha)
                if alpha > 0:
                    toast.after(30, lambda: fade_out(alpha))
                else:
                    toast.destroy()

            fade_in()
            toast.after(3000, fade_out)
        except Exception as e:
            log.warning(f"Toast fallback error: {e}")

    def _mostrar_toast_error(self, motor):
        self.root.after(
            0, lambda: self._mostrar_toast_fallback(motor.title(), "Sin IA")
        )

    def _mostrar_notif_error(self, texto):
        def show():
            try:
                ancho, alto = 280, 22
                sw = self.estado_win.winfo_screenwidth()
                sh = self.estado_win.winfo_screenheight()
                if self.config.get("widget_posicion", "lateral") == "centro":
                    x = (sw - ancho) // 2
                else:
                    x = sw - ancho - 10
                y_widget = sh - 22 - 42
                y = y_widget - alto - 6
                notif = tk.Toplevel(self.root)
                notif.overrideredirect(True)
                notif.attributes("-topmost", True)
                notif.attributes("-alpha", 0.85)
                notif.configure(bg="#1e1e2e")
                notif.geometry(f"{ancho}x{alto}+{x}+{y}")
                tk.Label(
                    notif,
                    text=texto,
                    font=("Segoe UI Variable", 10),
                    bg="#1e1e2e",
                    fg="white",
                ).pack(expand=True, padx=4)
                notif.after(4000, notif.destroy)
            except Exception:
                pass

        self.root.after(0, show)

    def _crear_ventana_estado(self):
        _tamaños = {
            "pequeño": (9, 20),
            "normal": (11, 24),
            "grande": (13, 32),
        }
        self._widget_font_size, self._widget_alto = _tamaños.get(
            self.config.get("widget_size", "normal"), (11, 24)
        )

        # Widget principal — texto de estado
        topmost = self.config.get("widget_topmost", True)
        self.estado_win = tk.Toplevel(self.root)
        self.estado_win.overrideredirect(True)
        self.estado_win.attributes("-topmost", topmost)
        self.estado_win.attributes("-alpha", 0.85)
        self.estado_win.configure(bg="#1e1e2e")

        _ci = self.config.get("widget_color_inactivo", "#888888")
        self._canvas_pulso = tk.Canvas(
            self.estado_win, width=18, height=18, bg="#1e1e2e", highlightthickness=0
        )
        self._canvas_pulso.pack(side=tk.LEFT, padx=(6, 2))
        self._canvas_pulso.bind("<Button-1>", self._mostrar_menu_modos)
        self._canvas_pulso.bind("<Button-3>", self._mostrar_menu_opciones)
        self._canvas_pulso.config(cursor="hand2")

        self._pulso_oval = self._canvas_pulso.create_oval(
            5, 5, 13, 13, fill=_ci, outline=""
        )
        self._pulso_radio = 4
        self._pulso_activo = False
        self._pulso_color = _ci

        def _animar_pulso():
            if not self._pulso_activo:
                return
            self._pulso_radio = 6 if self._pulso_radio == 4 else 4
            cx, cy = 9, 9
            r = self._pulso_radio
            self._canvas_pulso.coords(self._pulso_oval, cx - r, cy - r, cx + r, cy + r)
            self._canvas_pulso.itemconfig(self._pulso_oval, fill=self._pulso_color)
            self.estado_win.after(300, _animar_pulso)

        self._animar_pulso = _animar_pulso

        self._lbl_icono = self._canvas_pulso

        self._estado_label = tk.Label(
            self.estado_win,
            text="",
            font=("Segoe UI Variable", self._widget_font_size),
            bg="#1e1e2e",
            fg=self.config.get("widget_color_inactivo", "#888888"),
            anchor="w",
            padx=2,
        )
        self._estado_label.pack(side=tk.LEFT)
        self._estado_label.bind("<Button-1>", self._mostrar_menu_modos)
        self._estado_label.config(cursor="hand2")
        self._estado_label.bind("<Button-3>", self._mostrar_menu_opciones)

        # Widget secundario — iconos fijos
        self._iconos_win = tk.Toplevel(self.root)
        self._iconos_win.overrideredirect(True)
        self._iconos_win.attributes("-topmost", topmost)
        self._iconos_win.attributes("-alpha", 0.85)
        self._iconos_win.configure(bg="#1e1e2e")

        _ci = self.config.get("widget_color_inactivo", "#888888")

        self._btn_autoenter = tk.Label(
            self._iconos_win,
            text="⏎",
            bg="#1e1e2e",
            fg=_ci,
            font=("Segoe UI Variable", self._widget_font_size),
            cursor="hand2",
        )
        self._btn_autoenter.pack(side=tk.LEFT, padx=(4, 2))
        self._btn_autoenter.bind("<Button-1>", lambda e: self._toggle_autoenter())
        self._btn_autoenter.bind("<Button-3>", self._mostrar_menu_autoenter)

        sep = tk.Label(
            self._iconos_win,
            text="|",
            bg="#1e1e2e",
            fg=_ci,
            font=("Segoe UI Variable", self._widget_font_size),
        )
        sep.pack(side=tk.LEFT, padx=(0, 2))

        btn_nota = tk.Label(
            self._iconos_win,
            text="♪",
            bg="#1e1e2e",
            fg=_ci,
            font=("Segoe UI Variable", self._widget_font_size),
            cursor="hand2",
        )
        btn_nota.pack(side=tk.LEFT, padx=(0, 2))
        btn_nota.bind("<Button-1>", lambda e: self._grabar_nota())

        sep2 = tk.Label(
            self._iconos_win,
            text="-",
            bg="#1e1e2e",
            fg=_ci,
            font=("Segoe UI Variable", self._widget_font_size),
        )
        sep2.pack(side=tk.LEFT, padx=(0, 2))

        btn_hist = tk.Label(
            self._iconos_win,
            text="≡",
            bg="#1e1e2e",
            fg=_ci,
            font=("Segoe UI Variable", self._widget_font_size),
            cursor="hand2",
        )
        btn_hist.pack(side=tk.LEFT, padx=(0, 6))
        btn_hist.bind("<Button-1>", lambda e: self._ver_notas())

        # Posicionar ambos widgets
        self._posicionar_widgets()
        self._actualizar_texto_estado()

        # Esquinas redondeadas Windows 11
        for win in (self.estado_win, self._iconos_win):
            try:
                win.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int)
                )
            except Exception:
                pass

    def _mostrar_toast_stt(self, nombre):
        try:
            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.attributes("-alpha", 0.0)
            toast.configure(bg="#1e1e2e")

            tk.Label(
                toast,
                text=f"✓ Motor activo: {nombre}",
                font=("Segoe UI Variable", 10),
                bg="#1e1e2e",
                fg="#7C5EF7",
            ).pack(padx=16, pady=10)

            x = self.estado_win.winfo_x()
            y = self.estado_win.winfo_y() - 50
            toast.geometry(f"+{x}+{y}")

            for alpha in range(0, 9):
                toast.attributes("-alpha", alpha / 10)
                toast.update()
                time.sleep(0.03)

            toast.after(2500, toast.destroy)
        except Exception:
            pass

    def _posicionar_widgets(self):
        try:
            self.estado_win.update_idletasks()
            self._iconos_win.update_idletasks()
            from tkinter.font import Font

            _font = Font(family="Segoe UI Variable", size=self._widget_font_size)
            _icono_w = (
                self._lbl_icono.winfo_reqwidth() if hasattr(self, "_lbl_icono") else 0
            )
            ancho_texto = max(
                _font.measure(self._estado_label.cget("text")) + _icono_w + 24, 240
            )
            ancho_iconos = self._iconos_win.winfo_reqwidth() + 4
            ancho_total = ancho_texto + ancho_iconos
            alto = self._widget_alto
            sw = self.estado_win.winfo_screenwidth()
            sh = self.estado_win.winfo_screenheight()
            if self.config.get("widget_posicion", "lateral") == "centro":
                x = (sw - ancho_total) // 2
            else:
                x = sw - ancho_total - 10
            y = sh - alto - 50
            self.estado_win.geometry(f"{ancho_texto}x{alto}+{x}+{y}")
            self._iconos_win.geometry(f"{ancho_iconos}x{alto}+{x + ancho_texto}+{y}")
        except Exception:
            pass

    def actualizar_icono(self, estado):
        color_inactivo = self.config.get("widget_color_inactivo", "#888888")
        colores = {
            "inactivo": color_inactivo,
            "grabando": "#ff4444",
            "procesando": "#ffaa00",
        }
        fg = colores.get(estado, "gray")
        try:
            self._estado_label.configure(fg=fg)
            self._lbl_icono.configure(fg=fg)
        except Exception:
            pass
        try:
            for w in (self._sep1, self._sep2, self._btn_nota, self._btn_hist):
                w.configure(fg=fg)
        except Exception:
            pass
        try:
            if estado == "inactivo":
                self._actualizar_color_autoenter()
            else:
                self._btn_autoenter.configure(fg=fg)
        except Exception:
            pass
        try:
            self._pulso_color = fg
            if estado in ("grabando", "procesando"):
                self._pulso_activo = True
                self._animar_pulso()
            else:
                self._pulso_activo = False
                cx, cy = 9, 9
                self._canvas_pulso.coords(
                    self._pulso_oval, cx - 4, cy - 4, cx + 4, cy + 4
                )
                self._canvas_pulso.itemconfig(self._pulso_oval, fill=fg)
        except Exception:
            pass

    def _set_modo_ia(self, modo_key):
        self.config["modo_ia"] = modo_key
        guardar_config(self.config)
        log.info(f"Modo IA cambiado a: {modo_key}")
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.update_menu()
        try:
            self.root.after(0, self._actualizar_texto_estado)
        except Exception as e:
            log.error(f"Error actualizando label de estado: {e}")

    def _refresh_tray_menu(self):
        if not hasattr(self, "tray_icon") or not self.tray_icon:
            return
        try:
            self.root.after(0, self._reconstruir_tray_menu)
        except Exception:
            pass

    def _reconstruir_tray_menu(self):
        if not hasattr(self, "tray_icon") or not self.tray_icon:
            return
        try:
            self.tray_icon.update_menu()
        except Exception:
            pass
        self.root.after(0, self._actualizar_color_autoenter)

    def _recargar_modelo_con_splash(self):
        try:
            self._estado_label.configure(text="Recargando modelo...")
        except Exception:
            pass
        try:
            self.cargar_modelo()
            log.info(
                f"STT recargado OK | backend={self.stt_backend} | nombre={self.stt_nombre}"
            )
            self.root.after(0, lambda: self._mostrar_toast_stt(self.stt_nombre))
        except Exception as e:
            log.error(f"STT recarga FALLIDA: {e}")
            self.root.after(0, lambda: self._mostrar_toast_stt(f"ERROR: {e}"))
        self.root.after(0, self._actualizar_texto_estado)

    def _abrir_configuracion(self, tab=None):
        if getattr(self, "_config_abriendo", False):
            return
        self._config_abriendo = True

        def show():
            try:
                if hasattr(self, "_config_win") and self._config_win:
                    try:
                        if self._config_win.win.winfo_exists():
                            self._config_win.win.lift()
                            self._config_win.win.focus_force()
                            self._config_win.win.attributes("-topmost", True)
                            self._config_win.win.after(
                                100,
                                lambda: self._config_win.win.attributes(
                                    "-topmost", False
                                ),
                            )
                            return
                    except Exception:
                        pass
            finally:
                self._config_abriendo = False
            config_anterior = dict(self.config)

            def on_save(nueva_config):
                # ... (resto del código de on_save)
                self.config.update(nueva_config)
                if not self.config.get("ia_activo", True):
                    self.config["modo_ia"] = "normal_stt"
                import traceback

                log.info(
                    f"ia_activo cambiado a {self.config.get('ia_activo')} | {traceback.format_stack()[-2].strip()}"
                )

                try:
                    if nueva_config.get("tema") != config_anterior.get("tema"):
                        self._aplicar_tema(nueva_config.get("tema", "light"))
                        if hasattr(self, "_config_win") and self._config_win:
                            try:
                                if self._config_win.win.winfo_exists():
                                    self._config_win._aplicar_tema_widgets()
                            except Exception:
                                pass
                    else:
                        self._aplicar_tema(nueva_config.get("tema", "light"))
                except Exception as _e:
                    log.error(f"on_save _aplicar_tema error: {_e}")

                motor_anterior = config_anterior.get("ia_motor", "")
                motor_nuevo = nueva_config.get("ia_motor", "")

                if motor_nuevo != "ollama":
                    threading.Thread(target=cerrar_ollama, daemon=True).start()
                    log.info("Ollama cerrado — motor activo: %s", motor_nuevo)
                elif motor_nuevo == "ollama" and self.config.get("ia_activo", True):

                    def _arrancar_ollama():
                        from ai_processor import asegurar_ollama

                        asegurar_ollama()

                    threading.Thread(target=_arrancar_ollama, daemon=True).start()
                    log.info("Ollama: precalentando en background")

                guardar_config(self.config)

                if nueva_config.get("inicio_windows") != config_anterior.get(
                    "inicio_windows"
                ):
                    self._set_inicio_windows(nueva_config.get("inicio_windows", False))

                # Reaplicar listeners con nuevos atajos y trigger
                self._configurar_listeners()

                # Verificar que el motor STT seleccionado está realmente instalado
                # antes de plantearse recargarlo
                _motor_sel = self.config.get("stt_motor", "local_gpu")
                _modelo_sel = self.config.get("stt_modelo", "base")
                _saltar_reload_stt = False
                if _motor_sel in (
                    "parakeet",
                    "parakeet_gpu",
                ) and not self._stt_modelo_instalado(_motor_sel, _modelo_sel):
                    log.warning(
                        "Parakeet seleccionado pero no instalado — cambiando a Whisper base"
                    )
                    self.config["stt_motor"] = "local_cpu"
                    self.config["stt_modelo"] = "base"
                    guardar_config(self.config)
                elif _motor_sel in (
                    "local_gpu",
                    "local_cpu",
                ) and not self._stt_modelo_instalado(_motor_sel, _modelo_sel):
                    log.warning(
                        f"Modelo Whisper '{_modelo_sel}' no instalado — se mantiene el STT actual"
                    )
                    _saltar_reload_stt = True

                # Recargar STT si cambió el motor o el modelo,
                # o si el backend activo no coincide con lo configurado
                stt_motor_cfg = self.config.get("stt_motor", "local_gpu")
                backend_esperado = (
                    "parakeet"
                    if stt_motor_cfg in ("parakeet", "parakeet_gpu")
                    else "whisper"
                )
                stt_cambio = nueva_config.get("stt_motor") != config_anterior.get(
                    "stt_motor"
                ) or nueva_config.get("stt_modelo") != config_anterior.get("stt_modelo")
                backend_desajuste = self.stt_backend != backend_esperado
                log.info(
                    f"on_save | stt_motor anterior={config_anterior.get('stt_motor')} | nuevo={nueva_config.get('stt_motor')} | backend={self.stt_backend} | activo={self.activo}"
                )
                if (stt_cambio or backend_desajuste) and not _saltar_reload_stt:
                    _motor = self.config.get("stt_motor", "local_gpu")
                    _modelo = self.config.get("stt_modelo", "base")
                    if not self._manejar_stt_no_instalado(_motor, _modelo):
                        return
                    log.info(
                        f"Recargando STT | cambio={stt_cambio} | desajuste={backend_desajuste} | cfg={stt_motor_cfg} | activo={self.stt_backend}"
                    )
                    self.modelo = None
                    threading.Thread(
                        target=self._recargar_modelo_con_splash, daemon=True
                    ).start()

                topmost = nueva_config.get("widget_topmost", True)
                try:
                    self.estado_win.attributes("-topmost", topmost)
                    self._iconos_win.attributes("-topmost", topmost)
                except Exception:
                    pass

                # Recrear widget para aplicar cambios de layout
                try:
                    self.estado_win.destroy()
                    self._iconos_win.destroy()
                except Exception:
                    pass
                self._crear_ventana_estado()
                if not self.config.get("widget_visible", True):
                    self.estado_win.withdraw()
                    self._iconos_win.withdraw()

                self.root.after(0, self._actualizar_texto_estado)
                if hasattr(self, "tray_icon") and self.tray_icon:
                    self.tray_icon.update_menu()

            self._config_win = ConfigWindow(
                self.root,
                self.config,
                on_save,
                start_tab=tab,
                on_modos_change=self._refresh_tray_menu,
            )

        self.root.after(0, show)

    def _abrir_configuracion_tab(self, tab):
        def show():
            if hasattr(self, "_config_win") and self._config_win:
                try:
                    if self._config_win.win.winfo_exists():
                        self._config_win.win.lift()
                        self._config_win.win.focus_force()
                        return
                except Exception:
                    pass
            config_anterior = dict(self.config)

            def on_save(nueva_config):
                self.config.update(nueva_config)
                if not self.config.get("ia_activo", True):
                    self.config["modo_ia"] = "normal_stt"
                import traceback

                log.info(
                    f"ia_activo cambiado a {self.config.get('ia_activo')} | {traceback.format_stack()[-2].strip()}"
                )
                guardar_config(self.config)
                self.root.after(0, self._actualizar_texto_estado)
                if hasattr(self, "tray_icon") and self.tray_icon:
                    self.tray_icon.update_menu()
                # Verificar que el motor STT seleccionado está realmente instalado
                # antes de plantearse recargarlo
                _motor_sel = self.config.get("stt_motor", "local_gpu")
                _modelo_sel = self.config.get("stt_modelo", "base")
                _saltar_reload_stt = False
                if _motor_sel in (
                    "parakeet",
                    "parakeet_gpu",
                ) and not self._stt_modelo_instalado(_motor_sel, _modelo_sel):
                    log.warning(
                        "Parakeet seleccionado pero no instalado — cambiando a Whisper base"
                    )
                    self.config["stt_motor"] = "local_cpu"
                    self.config["stt_modelo"] = "base"
                    guardar_config(self.config)
                elif _motor_sel in (
                    "local_gpu",
                    "local_cpu",
                ) and not self._stt_modelo_instalado(_motor_sel, _modelo_sel):
                    log.warning(
                        f"Modelo Whisper '{_modelo_sel}' no instalado — se mantiene el STT actual"
                    )
                    _saltar_reload_stt = True

                stt_motor_cfg = self.config.get("stt_motor", "local_gpu")
                backend_esperado = (
                    "parakeet"
                    if stt_motor_cfg in ("parakeet", "parakeet_gpu")
                    else "whisper"
                )
                stt_cambio = nueva_config.get("stt_motor") != config_anterior.get(
                    "stt_motor"
                ) or nueva_config.get("stt_modelo") != config_anterior.get("stt_modelo")
                backend_desajuste = self.stt_backend != backend_esperado
                if (stt_cambio or backend_desajuste) and not _saltar_reload_stt:
                    _motor = self.config.get("stt_motor", "local_gpu")
                    _modelo = self.config.get("stt_modelo", "base")
                    if not self._manejar_stt_no_instalado(_motor, _modelo):
                        return
                    log.info(
                        f"Recargando STT | cambio={stt_cambio} | desajuste={backend_desajuste} | cfg={stt_motor_cfg} | activo={self.stt_backend}"
                    )
                    self.modelo = None
                    threading.Thread(
                        target=self._recargar_modelo_con_splash, daemon=True
                    ).start()

            self._config_win = ConfigWindow(
                self.root,
                self.config,
                on_save,
                start_tab=tab,
                on_modos_change=self._refresh_tray_menu,
            )

        self.root.after(0, show)

    def _abrir_historial(self):
        self._abrir_configuracion_tab("Historial")

    def _abrir_historial(self):
        def show():
            def on_save(nueva_config):
                self.config.update(nueva_config)
                import traceback

                log.info(
                    f"ia_activo cambiado a {self.config.get('ia_activo')} | {traceback.format_stack()[-2].strip()}"
                )
                guardar_config(self.config)
                self.root.after(0, self._actualizar_texto_estado)

            ConfigWindow(self.root, self.config, on_save, start_tab="Historial")

        self.root.after(0, show)

    def iniciar(self):
        self.root = tk.Tk()
        self._aplicar_tema(self.config.get("tema", "light"))
        self.root.withdraw()
        self._mostrar_splash()

        def cargar():
            self.cargar_modelo()
            self._configurar_listeners()

            # Precalentar Ollama si es el motor activo
            if self.config.get("ia_motor") == "ollama" and self.config.get(
                "ia_activo", True
            ):

                def _precalentar():
                    from ai_processor import asegurar_ollama

                    asegurar_ollama()

                threading.Thread(target=_precalentar, daemon=True).start()
                log.info("Ollama: precalentando en el arranque")

            self.root.after(0, self._iniciar_main)

        threading.Thread(target=cargar, daemon=True).start()
        self.root.mainloop()

    def _mostrar_splash(self):
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.update_idletasks()
        splash.update()
        splash.attributes("-topmost", True)
        splash.configure(bg="#1e1e2e")

        try:
            import ctypes

            hwnd = (
                ctypes.windll.user32.GetParent(splash.winfo_id()) or splash.winfo_id()
            )
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass

        sw = splash.winfo_screenwidth()
        sh = splash.winfo_screenheight()
        w, h = 380, 310
        splash.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        from PIL import Image, ImageTk

        img = Image.open(os.path.join(RESOURCE_DIR, "assets", "Splash_SpeakMe.png"))
        img = img.resize((200, 200), Image.LANCZOS)
        self._splash_img = ImageTk.PhotoImage(img)
        tk.Label(splash, image=self._splash_img, bg="#1e1e2e").pack(pady=(20, 10))

        stt_motor = self.config.get("stt_motor", "local_gpu")
        modelo_id = self.config.get("stt_modelo", "large-v3-turbo")
        if stt_motor == "parakeet":
            txt = "Cargando Parakeet TDT v3..."
        else:
            device = "GPU" if stt_motor == "local_gpu" else "CPU"
            txt = f"Cargando {modelo_id} ({device})..."
        tk.Label(
            splash, text=txt, bg="#1e1e2e", fg="#7C5EF7", font=("Segoe UI Variable", 10)
        ).pack()

        from tkinter import ttk

        pb = ttk.Progressbar(splash, mode="indeterminate", length=300)
        pb.pack(pady=(10, 0))
        pb.start(12)

        self._splash = splash
        return splash

    def _cerrar_splash(self):
        try:
            self._splash.destroy()
        except Exception:
            pass

    def _actualizar_splash(self, mensaje, progreso):
        try:
            self._splash_label.configure(text=mensaje)
            ancho_total = 280
            self._barra.configure(width=int(ancho_total * progreso / 100))
            self._splash_label.update()
        except:
            pass

    def _detener_listeners(self):
        for lst in self._listeners:
            try:
                lst.stop()
            except Exception:
                pass
        self._listeners = []

    def _configurar_listeners(self):
        self._detener_listeners()
        config = self.config

        trigger_type = config.get("trigger_type", "mouse")
        modo_grab = config.get("modo_grabacion", "ptt")
        PTT_UMBRAL = config.get("umbral_auto_ms", 300) / 1000.0
        boton_map = {
            "x1": mouse.Button.x1,
            "x2": mouse.Button.x2,
            "middle": mouse.Button.middle,
        }
        boton = boton_map.get(config.get("trigger_button", "x2"), mouse.Button.x2)

        log.info(
            f"Listeners | trigger={trigger_type} | modo={modo_grab} | umbral={PTT_UMBRAL}s"
        )

        # ── Helpers de grabación según modo ────────────────────────────────────────────
        _toggle_activo = [False]

        def _on_trigger_press():
            if modo_grab == "ptt":
                self.iniciar_grabacion()
            elif modo_grab == "toggle":
                if _toggle_activo[0]:
                    _toggle_activo[0] = False
                    self.detener_y_procesar()
                else:
                    _toggle_activo[0] = True
                    self.iniciar_grabacion()
            # auto: se gestiona en on_release con la duración

        def _on_trigger_release(duracion=None):
            if modo_grab == "ptt":
                self.detener_y_procesar()
            elif modo_grab == "auto" and duracion is not None:
                if duracion < PTT_UMBRAL:
                    if _toggle_activo[0]:
                        _toggle_activo[0] = False
                        log.info(f"Auto Toggle OFF ({duracion:.2f}s)")
                        self.detener_y_procesar()
                    else:
                        _toggle_activo[0] = True
                        log.info(f"Auto Toggle ON ({duracion:.2f}s)")
                else:
                    _toggle_activo[0] = False
                    log.info(f"Auto PTT ({duracion:.2f}s)")
                    self.detener_y_procesar()
            # toggle: release no hace nada

        # ── Mouse listener ──────────────────────────────────────────────────────────────────
        if trigger_type in ("mouse", "both"):
            _mouse_press_time = [None]

            def on_click(x, y, button, pressed):
                if button != boton:
                    return
                if pressed:
                    _mouse_press_time[0] = time.monotonic()
                    _on_trigger_press()
                elif modo_grab != "toggle":
                    duracion = (
                        (time.monotonic() - _mouse_press_time[0])
                        if _mouse_press_time[0] is not None
                        else None
                    )
                    _mouse_press_time[0] = None
                    _on_trigger_release(duracion)

            ml = mouse.Listener(on_click=on_click)
            ml.daemon = True
            ml.start()
            self._listeners.append(ml)

        # ── Keyboard listener ───────────────────────────────────────────────────────────────
        if trigger_type in ("teclado", "both"):
            tecla_cfg = config.get("trigger_tecla", "ctrl_r")
            try:
                tecla_trigger = getattr(keyboard.Key, tecla_cfg)
            except AttributeError:
                tecla_trigger = keyboard.KeyCode.from_char(tecla_cfg)
            log.info(f"Trigger tecla: {tecla_cfg} → {tecla_trigger}")

            _press_time = [None]

            def on_press(key):
                if key != tecla_trigger or _press_time[0] is not None:
                    return
                _press_time[0] = time.monotonic()
                if modo_grab != "auto":
                    _on_trigger_press()
                else:
                    if not _toggle_activo[0]:
                        self.iniciar_grabacion()

            def on_release(key):
                if key != tecla_trigger or _press_time[0] is None:
                    return
                duracion = time.monotonic() - _press_time[0]
                _press_time[0] = None
                _on_trigger_release(duracion)

            kl = keyboard.Listener(on_press=on_press, on_release=on_release)
            kl.daemon = True
            kl.start()
            self._listeners.append(kl)

        atajo_correccion = config.get("atajo_correccion", "<ctrl>+<alt>+c")
        atajo_nota = config.get("atajo_nota", "")

        hotkeys = {}
        if atajo_correccion:
            hotkeys[atajo_correccion] = self.abrir_correccion_manual
        if atajo_nota:
            hotkeys[atajo_nota] = lambda: self.root.after(0, self._grabar_nota)

        if hotkeys:
            try:
                gk = keyboard.GlobalHotKeys(hotkeys)
                gk.daemon = True
                gk.start()
                self._listeners.append(gk)
            except Exception as e:
                log.warning(f"GlobalHotKeys error: {e}")

    def _grabar_nota(self):
        if not self.modelo:
            log.info("NOTA | modelo no cargado, ignorando")
            return

        def show():
            # Cerrar historial de notas si está abierto
            if hasattr(self, "_notas_win") and self._notas_win:
                try:
                    if self._notas_win.winfo_exists():
                        self._notas_win.destroy()
                        self._notas_win = None
                except Exception:
                    pass

            if hasattr(self, "_nota_win") and self._nota_win:
                try:
                    if self._nota_win.winfo_exists():
                        self._nota_win.destroy()
                        self._nota_win = None
                        return
                except Exception:
                    pass

            BG_NOTE = "#2a2a3a"
            BG_BTN = "#3a3a5a"
            FG_BTN = "#F0F0F0"

            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=BG_NOTE)
            win.attributes("-alpha", 0.85)

            ancho, alto = 280, 200
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            _sizes = {"pequeño": (9, 18), "normal": (11, 22), "grande": (13, 28)}
            _, alto_widget = _sizes.get(
                self.config.get("widget_size", "normal"), (11, 22)
            )
            if self.config.get("widget_posicion", "lateral") == "centro":
                x = (sw - ancho) // 2
            else:
                x = sw - ancho - 10
            y_widget = sh - alto_widget - 42
            y = y_widget - alto - 20
            win.geometry(f"{ancho}x{alto}+{x}+{y}")

            win.after(50, lambda: self._redondear_esquinas(win, 280, 200))

            # X cerrar
            tk.Button(
                win,
                text="✕",
                command=lambda: _cerrar(),
                bg=BG_NOTE,
                fg="#777777",
                relief="flat",
                font=("Segoe UI Variable", 9),
                cursor="hand2",
                bd=0,
            ).place(x=ancho - 22, y=4)

            # Área de texto / estado
            lbl_estado = tk.Label(
                win,
                text="Mantén pulsado para grabar",
                fg="#aaaaaa",
                bg=BG_NOTE,
                font=("Segoe UI Variable", 9),
            )
            lbl_estado.pack(pady=(24, 6))

            lbl_texto = tk.Label(
                win,
                text="",
                fg="#F0F0F0",
                bg=BG_NOTE,
                font=("Segoe UI Variable", 9),
                wraplength=255,
                justify="left",
            )
            lbl_texto.pack(fill=tk.BOTH, expand=True, padx=14)

            # Botón GRABAR
            btn_grabar = tk.Button(
                win,
                text="👆  GRABAR",
                bg=BG_BTN,
                fg=FG_BTN,
                font=("Segoe UI Variable", 10, "bold"),
                relief="flat",
                cursor="hand2",
                padx=20,
                pady=8,
                bd=0,
            )
            btn_grabar.pack(pady=(6, 16))

            frames_audio = []
            grabando = [False]
            stream_ref = [None]
            _t_inicio = [0.0]

            def _iniciar():
                if grabando[0]:
                    return
                _t_inicio[0] = time.monotonic()
                grabando[0] = True
                win.after(
                    0,
                    lambda: lbl_estado.config(
                        text="🎤 Grabando...",
                        fg="#cc0000",
                        font=("Segoe UI Variable", 11, "bold"),
                    ),
                )
                stream_ref[0] = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    input_device_index=self.config.get("mic_index", 1),
                    frames_per_buffer=1024,
                )

                def _grabar():
                    while grabando[0]:
                        try:
                            frames_audio.append(
                                stream_ref[0].read(1024, exception_on_overflow=False)
                            )
                        except Exception:
                            break

                threading.Thread(target=_grabar, daemon=True).start()

            def _detener():
                if not grabando[0]:
                    return
                if time.monotonic() - _t_inicio[0] < 0.5:
                    return
                grabando[0] = False
                time.sleep(0.05)
                if stream_ref[0]:
                    try:
                        stream_ref[0].stop_stream()
                        stream_ref[0].close()
                    except Exception as e:
                        log.warning(f"NOTA | error cerrando stream: {e}")
                    stream_ref[0] = None
                if len(frames_audio) < 10:
                    win.after(0, lambda: _cerrar())
                    return
                win.after(
                    0,
                    lambda: lbl_estado.config(
                        text="⏳ Procesando...",
                        fg="#886600",
                        font=("Segoe UI Variable", 10),
                    ),
                )
                threading.Thread(target=_procesar, daemon=True).start()

            def _procesar():
                try:
                    if not frames_audio or len(frames_audio) < 10:
                        win.after(0, lambda: _cerrar())
                        return
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        tmp_path = f.name
                    with wave.open(tmp_path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
                        wf.setframerate(16000)
                        wf.writeframes(b"".join(frames_audio))
                    if self.stt_backend == "parakeet":
                        resultado = self.modelo.recognize(tmp_path)
                        texto_crudo = (
                            (
                                " ".join(resultado)
                                if isinstance(resultado, list)
                                else resultado
                            )
                            .strip()
                            .rstrip(".")
                        )
                    else:
                        cfg_idioma = self.config.get("idioma", "es")
                        segs, _ = self.modelo.transcribe(
                            tmp_path,
                            language=None if cfg_idioma == "auto" else cfg_idioma,
                            beam_size=1,
                            vad_filter=True,
                        )
                        texto_crudo = " ".join(s.text for s in segs).strip().rstrip(".")
                    texto_crudo = aplicar_sustituciones(texto_crudo)
                    os.unlink(tmp_path)
                    if not texto_crudo:
                        win.after(0, lambda: _cerrar())
                        return
                    texto_procesado = corregir_texto(
                        texto_crudo,
                        modo="normal_stt",
                        ia_motor=self.config.get("ia_motor", "ollama"),
                        groq_key=self.config.get("groq_key", ""),
                        gemini_key=self.config.get("gemini_key", ""),
                    )
                    notas = _leer_notas()
                    notas.append(
                        {
                            "timestamp": datetime.now().isoformat(timespec="seconds"),
                            "original": texto_crudo,
                            "procesado": texto_procesado,
                        }
                    )
                    _guardar_notas(notas)

                    def _mostrar_final():
                        lbl_estado.config(
                            text="✓ Guardado",
                            fg="#007700",
                            font=("Segoe UI Variable", 10, "bold"),
                        )
                        lbl_texto.config(text=texto_procesado[:200])
                        win.after(3000, lambda: _cerrar())

                    win.after(0, _mostrar_final)
                except Exception as e:
                    log.error(f"NOTA | error en _procesar: {e}")
                    win.after(0, lambda: _cerrar())

            def _cerrar():
                grabando[0] = False
                if stream_ref[0]:
                    try:
                        stream_ref[0].stop_stream()
                        stream_ref[0].close()
                    except Exception:
                        pass
                    stream_ref[0] = None
                try:
                    win.destroy()
                except Exception:
                    pass

            btn_grabar.bind("<ButtonPress-1>", lambda e: _iniciar())
            btn_grabar.bind("<ButtonRelease-1>", lambda e: _detener())
            win.after(300000, _cerrar)
            self._nota_win = win

        self.root.after(0, show)

    def _ver_notas(self):
        def show():
            # Cerrar ventana de grabación si está abierta
            if hasattr(self, "_nota_win") and self._nota_win:
                try:
                    if self._nota_win.winfo_exists():
                        self._nota_win.destroy()
                        self._nota_win = None
                except Exception:
                    pass

            if hasattr(self, "_notas_win") and self._notas_win:
                try:
                    if self._notas_win.winfo_exists():
                        self._notas_win.destroy()
                        self._notas_win = None
                        return
                except Exception:
                    pass

            BG = "#1e1e2e"
            ROW_BG = "#2a2a3a"
            ROW_HOV = "#3a3a5a"

            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=BG)
            win.attributes("-alpha", 0.85)
            self._notas_win = win

            ancho, alto = 300, 340
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            _sizes = {"pequeño": (9, 18), "normal": (11, 22), "grande": (13, 28)}
            _, alto_widget = _sizes.get(
                self.config.get("widget_size", "normal"), (11, 22)
            )
            if self.config.get("widget_posicion", "lateral") == "centro":
                x = (sw - ancho) // 2
            else:
                x = sw - ancho - 10
            y_widget = sh - alto_widget - 42
            y = y_widget - alto - 20
            win.geometry(f"{ancho}x{alto}+{x}+{y}")

            win.after(50, lambda: self._redondear_esquinas(win, 300, 340))

            # Cabecera
            f_header = tk.Frame(win, bg=BG)
            f_header.pack(fill=tk.X, padx=12, pady=(12, 4))

            tk.Label(
                f_header,
                text="HISTORIAL DE NOTAS",
                bg=BG,
                fg="#aaaaaa",
                font=("Segoe UI Variable", 9, "bold"),
            ).pack(side=tk.LEFT)

            tk.Button(
                f_header,
                text="✕",
                bg=BG,
                fg="#777777",
                relief="flat",
                bd=0,
                font=("Segoe UI Variable", 9),
                cursor="hand2",
                command=win.destroy,
            ).pack(side=tk.RIGHT)

            # Separador
            tk.Frame(win, bg="#3a3a5a", height=1).pack(fill=tk.X, padx=12)

            # Lista con scroll
            container = tk.Frame(win, bg=BG)
            container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

            canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
            sb = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=sb.set)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            inner = tk.Frame(canvas, bg=BG)
            inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

            def _resize_inner(e):
                canvas.itemconfig(inner_id, width=e.width)

            canvas.bind("<Configure>", _resize_inner)

            def _ver_completa(texto, ts):
                popup = tk.Toplevel(win)
                if hasattr(self, "_nota_detalle_win") and self._nota_detalle_win:
                    try:
                        if self._nota_detalle_win.winfo_exists():
                            self._nota_detalle_win.destroy()
                    except Exception:
                        pass
                self._nota_detalle_win = popup
                popup.overrideredirect(True)
                popup.attributes("-topmost", True)
                BG_POSIT = "#F5F5F0"
                FG_POSIT = "#222222"
                popup.configure(bg=BG_POSIT)

                pw, ph = 280, 200
                win_x, win_y = win.winfo_x(), win.winfo_y()
                win_w, win_h = win.winfo_width(), win.winfo_height()
                px = win_x + (win_w - pw) // 2
                py = win_y + (win_h - ph) // 2
                popup.geometry(f"{pw}x{ph}+{px}+{py}")

                def _start_move(e):
                    popup._drag_x = e.x
                    popup._drag_y = e.y

                def _do_move(e):
                    nx = popup.winfo_x() + e.x - popup._drag_x
                    ny = popup.winfo_y() + e.y - popup._drag_y
                    popup.geometry(f"+{nx}+{ny}")

                popup.bind("<Button-1>", _start_move)
                popup.bind("<B1-Motion>", _do_move)

                popup.after(50, lambda: self._redondear_esquinas(popup, 280, 200))

                tk.Button(
                    popup,
                    text="✕",
                    bg=BG_POSIT,
                    fg="#999999",
                    relief="flat",
                    bd=0,
                    font=("Segoe UI Variable", 9),
                    cursor="hand2",
                    command=popup.destroy,
                ).place(x=pw - 22, y=4)

                tk.Label(
                    popup,
                    text=ts[:16].replace("T", " "),
                    bg=BG_POSIT,
                    fg="#666666",
                    font=("Segoe UI Variable", 8),
                ).pack(pady=(16, 4))

                txt = tk.Text(
                    popup,
                    wrap=tk.WORD,
                    font=("Segoe UI Variable", 9),
                    bg=BG_POSIT,
                    fg=FG_POSIT,
                    relief="flat",
                    bd=0,
                    padx=14,
                    pady=4,
                )
                txt.insert("1.0", texto)
                txt.config(state="disabled")
                txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

            def refresh():
                for w in inner.winfo_children():
                    w.destroy()
                notas = sorted(
                    _leer_notas(), key=lambda n: n.get("timestamp", ""), reverse=True
                )
                if not notas:
                    tk.Label(
                        inner,
                        text="No hay notas guardadas",
                        fg="#999999",
                        bg=BG,
                        font=("Segoe UI Variable", 9),
                    ).pack(pady=20)
                for nota in notas:
                    ts = nota.get("timestamp", "")
                    texto = nota.get("procesado", nota.get("original", ""))

                    row = tk.Frame(inner, bg=ROW_BG, pady=6, padx=10, cursor="hand2")
                    row.pack(fill=tk.X, padx=4, pady=2)

                    def eliminar(ts_del=nota.get("timestamp")):
                        nueva = [
                            n for n in _leer_notas() if n.get("timestamp") != ts_del
                        ]
                        _guardar_notas(nueva)
                        refresh()
                        inner.update_idletasks()
                        canvas.configure(scrollregion=canvas.bbox("all"))

                    btn_del = tk.Label(
                        row,
                        text="✕",
                        bg=ROW_BG,
                        fg="#bbbbbb",
                        font=("Segoe UI Variable", 9),
                        cursor="hand2",
                        padx=4,
                    )
                    btn_del.pack(side=tk.RIGHT)
                    btn_del.bind("<Button-1>", lambda e, f=eliminar: f())

                    tk.Label(
                        row,
                        text=ts[5:16].replace("T", " "),
                        font=("Segoe UI Variable", 8),
                        fg="#999999",
                        bg=ROW_BG,
                        width=12,
                        anchor="w",
                    ).pack(side=tk.LEFT)
                    tk.Label(
                        row,
                        text=texto[:55] + ("…" if len(texto) > 55 else ""),
                        font=("Segoe UI Variable", 9),
                        fg="#333333",
                        bg=ROW_BG,
                        anchor="w",
                    ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

                    def _hover_on(e, r=row):
                        r.configure(bg=ROW_HOV)
                        [c.configure(bg=ROW_HOV) for c in r.winfo_children()]

                    def _hover_off(e, r=row):
                        r.configure(bg=ROW_BG)
                        [c.configure(bg=ROW_BG) for c in r.winfo_children()]

                    row.bind("<Enter>", _hover_on)
                    row.bind("<Leave>", _hover_off)
                    row.bind("<Button-1>", lambda e, t=texto, s=ts: _ver_completa(t, s))
                    for child in row.winfo_children():
                        if child is not btn_del:
                            child.bind(
                                "<Button-1>",
                                lambda e, t=texto, s=ts: _ver_completa(t, s),
                            )

                inner.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))

            refresh()

        self.root.after(0, show)

    def _iniciar_main(self):
        from pystray import Icon, Menu, MenuItem
        from PIL import Image

        self._icono_img = Image.open(os.path.join(RESOURCE_DIR, "assets", "SpeakMe.ico"))

        def _accion_modo(k):
            def accion(icon, item):
                if k == "normal_stt":
                    self.config["ia_activo"] = False
                else:
                    self.config["ia_activo"] = True
                self._set_modo_ia(k)
                guardar_config(self.config)
                self.root.after(0, self._actualizar_texto_estado)
                if hasattr(self, "tray_icon"):
                    self.tray_icon.update_menu()

            return accion

        def _build_submenu_modos():
            ia_on = self.config.get("ia_activo", True)

            try:
                with open(os.path.join(BASE_DIR, "modos.json"), encoding="utf-8") as f:
                    modos_fresh = json.load(f)
            except Exception:
                modos_fresh = ai_processor.MODOS

            favoritos = [
                (k, v) for k, v in modos_fresh.items() if v.get("favorito", False)
            ]

            personales = [
                (k, v)
                for k, v in modos_fresh.items()
                if not v.get("sistema", False) and not v.get("favorito", False)
            ]

            items = []

            for k, v in favoritos:
                items.append(
                    MenuItem(
                        f"★ {v['nombre']}",
                        _accion_modo(k),
                        checked=lambda item, k=k: self.config.get("modo_ia") == k,
                        radio=True,
                        enabled=ia_on,
                    )
                )

            if favoritos and personales:
                items.append(MenuItem("──────────────────", None, enabled=False))

            for k, v in personales:
                items.append(
                    MenuItem(
                        v["nombre"],
                        _accion_modo(k),
                        checked=lambda item, k=k: self.config.get("modo_ia") == k,
                        radio=True,
                        enabled=ia_on,
                    )
                )

            items.append(MenuItem("──────────────────", None, enabled=False))
            items.append(
                MenuItem(
                    "⚙ Modos", lambda icon, item: self._abrir_configuracion_tab("Modos")
                )
            )

            return tuple(items)

        submenu_modos = Menu(_build_submenu_modos)

        def _accion_modo_stt(icon, item):
            self.config["ia_activo"] = False
            self.config["modo_ia"] = "normal_stt"
            guardar_config(self.config)
            self.root.after(0, self._actualizar_texto_estado)
            if hasattr(self, "tray_icon"):
                self.tray_icon.update_menu()

        def _items_favoritos():
            try:
                with open(os.path.join(BASE_DIR, "modos.json"), encoding="utf-8") as f:
                    modos_fresh = json.load(f)
            except Exception:
                modos_fresh = {}
            favoritos = [
                (k, v) for k, v in modos_fresh.items() if v.get("favorito", False)
            ][:3]
            items = []
            for k, v in favoritos:
                items.append(
                    MenuItem(
                        v.get("nombre", k),
                        _accion_modo(k),
                        checked=lambda item, k=k: (
                            self.config.get("modo_ia") == k
                            and self.config.get("ia_activo", True)
                        ),
                        radio=True,
                    )
                )
            return items

        menu = Menu(
            MenuItem("         SpeakMe!", None, enabled=False),
            MenuItem("──────────────────", None, enabled=False),
            MenuItem(
                "Normal (no IA)",
                _accion_modo_stt,
                checked=lambda item: not self.config.get("ia_activo", True),
                radio=True,
            ),
            MenuItem("Modos", submenu_modos),
            MenuItem("──────────────────", None, enabled=False),
            MenuItem("🗒 Nota rápida", lambda icon, item: self._grabar_nota()),
            MenuItem("📋 Ver notas", lambda icon, item: self._ver_notas()),
            MenuItem("──────────────────", None, enabled=False),
            MenuItem(
                "📚 + Vocabulario",
                lambda icon, item: self._abrir_configuracion_tab("Vocabulario"),
            ),
            MenuItem("📂 Historial", lambda icon, item: self._abrir_historial()),
            MenuItem("──────────────────", None, enabled=False),
            MenuItem("⚙️ Configuración", lambda icon, item: self._abrir_configuracion()),
            MenuItem("──────────────────", None, enabled=False),
            MenuItem("Guía rápida", lambda icon, item: self._mostrar_wizard()),
            MenuItem("──────────────────", None, enabled=False),
            MenuItem("Salir", lambda icon, item: self._salir()),
        )

        self.tray_icon = Icon("SpeakMe", self._icono_img, "SpeakMe!", menu)
        self._crear_ventana_estado()
        if self.config.get("iniciar_minimizado", False):
            self.estado_win.withdraw()
            self._iconos_win.withdraw()
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        if not self.config.get("bienvenida_mostrada", False):
            self.root.after(1000, self._mostrar_wizard)

    _WHISPER_SIZES = {
        "tiny": "~75 MB",
        "base": "~140 MB",
        "small": "~460 MB",
        "medium": "~1.5 GB",
        "large-v2": "~3.1 GB",
        "large-v3": "~3.1 GB",
        "large-v3-turbo": "~1.6 GB",
    }

    def _stt_modelo_instalado(self, motor: str, modelo: str) -> bool:
        HF_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
        if motor in ("parakeet", "parakeet_gpu"):
            return os.path.exists(
                os.path.join(HF_CACHE, "models--istupakov--parakeet-tdt-0.6b-v3-onnx")
            )
        repo = _whisper_repo_id(modelo)
        snaps = os.path.join(
            HF_CACHE, "models--" + repo.replace("/", "--"), "snapshots"
        )
        try:
            return any(True for _ in os.scandir(snaps))
        except OSError:
            return False

    def _manejar_stt_no_instalado(self, motor: str, modelo: str) -> bool:
        """Devuelve True si se puede continuar con la recarga STT. False si se aborta o
        se abre el gestor para descargar primero (la recarga ocurrirá al cerrar el gestor)."""
        if self._stt_modelo_instalado(motor, modelo):
            return True
        from tkinter import messagebox

        if motor in ("parakeet", "parakeet_gpu"):
            msg = "Parakeet TDT v3 (~600 MB) no está instalado.\n¿Deseas descargarlo ahora?"
            autoinstalar = "parakeet"
        else:
            tam = self._WHISPER_SIZES.get(modelo, "?")
            msg = f"El modelo '{modelo}' ({tam}) no está instalado.\n¿Deseas descargarlo ahora?"
            autoinstalar = modelo
        if not messagebox.askyesno("Modelo no instalado", msg, parent=self.root):
            return False
        if hasattr(self, "_config_win") and self._config_win:
            try:
                self._config_win._mostrar_gestor_modelos(autoinstalar=autoinstalar)
            except Exception:
                pass
        return False  # recarga diferida: ocurrirá al pulsar "Aplicar y cerrar" en el gestor

    def _mostrar_wizard(self):
        from PIL import Image, ImageTk, ImageDraw

        wizard = tk.Toplevel(self.root)
        wizard.overrideredirect(True)
        wizard.configure(bg="#f0f0f5")

        sw = wizard.winfo_screenwidth()
        sh = wizard.winfo_screenheight()
        w, h = 500, 420
        wizard.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        self._wizard_paso_actual = 1
        self._wizard_ref = wizard

        # Logo circular
        try:
            logo_path = os.path.join(RESOURCE_DIR, "assets", "SpeakMe_logo.png")
            logo_img = (
                Image.open(logo_path).convert("RGBA").resize((72, 72), Image.LANCZOS)
            )
            mask = Image.new("L", (72, 72), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 72, 72), fill=255)
            logo_img.putalpha(mask)
            self._wizard_logo = ImageTk.PhotoImage(logo_img)
            logo_label = tk.Label(wizard, image=self._wizard_logo, bg="#f0f0f5", bd=0)
        except Exception:
            logo_label = tk.Label(
                wizard, text="🎙", font=("Segoe UI Variable", 32), bg="#f0f0f5"
            )

        # Cabecera
        f_header = tk.Frame(wizard, bg="#f0f0f5")
        f_header.pack(fill=tk.X, padx=24, pady=(20, 0))

        logo_label.configure(bg="#f0f0f5")
        logo_label.pack(in_=f_header, side=tk.LEFT)

        f_header_texto = tk.Frame(f_header, bg="#f0f0f5")
        f_header_texto.pack(side=tk.LEFT, padx=(12, 0))

        tk.Label(
            f_header_texto,
            text="Guía rápida de uso",
            bg="#f0f0f5",
            fg="#1a1a2e",
            font=("Segoe UI Variable", 13, "bold"),
        ).pack(anchor=tk.W)

        self._wizard_label_paso = tk.Label(
            f_header_texto,
            text="Paso 1 de 4",
            bg="#f0f0f5",
            fg="#7C5EF7",
            font=("Segoe UI Variable", 9),
        )
        self._wizard_label_paso.pack(anchor=tk.W)

        # Separador
        tk.Frame(wizard, bg="#e0e0e8", height=1).pack(fill=tk.X, padx=24, pady=(12, 0))

        # Frame contenido
        self._wizard_frame_contenido = tk.Frame(
            wizard, bg="#f0f0f5", width=452, height=260
        )
        self._wizard_frame_contenido.pack(padx=24, pady=(0, 0))
        self._wizard_frame_contenido.pack_propagate(False)

        # Separador inferior
        tk.Frame(wizard, bg="#e0e0e8", height=1).pack(fill=tk.X, padx=24)

        # Botones
        f_botones = tk.Frame(wizard, bg="#f0f0f5")
        f_botones.pack(fill=tk.X, padx=24, pady=(10, 16))

        self._wizard_btn_omitir = tk.Button(
            f_botones,
            text="Omitir guía",
            bg="#f0f0f5",
            fg="#888888",
            relief=tk.SOLID,
            bd=1,
            font=("Segoe UI Variable", 9),
            padx=12,
            pady=6,
            cursor="hand2",
            command=lambda: self._wizard_omitir(wizard),
        )
        self._wizard_btn_omitir.pack(side=tk.LEFT)

        self._wizard_btn_siguiente = tk.Button(
            f_botones,
            text="Siguiente →",
            bg="#7C5EF7",
            fg="#ffffff",
            relief=tk.FLAT,
            bd=0,
            font=("Segoe UI Variable", 9, "bold"),
            padx=16,
            pady=6,
            cursor="hand2",
            command=lambda: self._wizard_siguiente(wizard),
        )
        self._wizard_btn_siguiente.pack(side=tk.RIGHT)

        self._wizard_mostrar_paso(1)

    def _wizard_mostrar_paso(self, paso):
        self._wizard_paso_actual = paso
        self._wizard_label_paso.config(text=f"Paso {paso} de 4")

        for widget in self._wizard_frame_contenido.winfo_children():
            widget.destroy()

        if paso == 1:
            self._wizard_paso_1()
        elif paso == 2:
            self._wizard_paso_2()
        elif paso == 3:
            self._wizard_paso_3()
        elif paso == 4:
            self._wizard_paso_4()

    def _wizard_paso_1(self):
        from PIL import Image, ImageTk, ImageDraw

        f = self._wizard_frame_contenido

        try:
            logo_path = os.path.join(RESOURCE_DIR, "assets", "SpeakMe_logo.png")
            logo_img = (
                Image.open(logo_path).convert("RGBA").resize((90, 90), Image.LANCZOS)
            )
            mask = Image.new("L", (90, 90), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 90, 90), fill=255)
            logo_img.putalpha(mask)
            self._wizard_paso1_logo = ImageTk.PhotoImage(logo_img)
            tk.Label(f, image=self._wizard_paso1_logo, bg="#f0f0f5").pack(pady=(20, 8))
        except Exception:
            tk.Label(f, text="🎙", font=("Segoe UI Variable", 36), bg="#f0f0f5").pack(
                pady=(20, 8)
            )

        tk.Label(
            f,
            text="¡Bienvenido a SpeakMe!",
            bg="#f0f0f5",
            fg="#1a1a2e",
            font=("Segoe UI Variable", 12, "bold"),
        ).pack(pady=(0, 8))
        tk.Label(
            f,
            text="SpeakMe! convierte tu voz en texto usando IA local.\n"
            "En los próximos pasos configurarás los motores\n"
            "para obtener la mejor experiencia posible.",
            bg="#f0f0f5",
            fg="#444444",
            font=("Segoe UI Variable", 10),
            justify=tk.CENTER,
        ).pack(pady=8)

    def _wizard_paso_2(self):
        f = self._wizard_frame_contenido
        tk.Label(
            f,
            text="Motor STT — Voz a texto",
            bg="#f0f0f5",
            fg="#1a1a2e",
            font=("Segoe UI Variable", 11, "bold"),
        ).pack(pady=(24, 6))
        tk.Label(
            f,
            text="Convierte tu voz en texto. Proceso 100% local, sin internet.",
            bg="#f0f0f5",
            fg="#444444",
            font=("Segoe UI Variable", 10),
        ).pack()
        tk.Label(
            f,
            text="Recomendación:",
            bg="#f0f0f5",
            fg="#1a1a2e",
            font=("Segoe UI Variable", 9, "bold"),
        ).pack(pady=(8, 0), padx=24, anchor=tk.W)
        tk.Label(
            f,
            text="• Sin GPU: Parakeet TDT v3  (rápido y preciso)\n"
            "• Con GPU: Whisper Large-v3-Turbo  (máxima precisión)",
            bg="#f0f0f5",
            fg="#666666",
            font=("Segoe UI Variable", 9),
            justify=tk.LEFT,
        ).pack(pady=(8, 12), padx=24, anchor=tk.W)
        tk.Button(
            f,
            text="Abrir Gestionar Modelos",
            bg="#7C5EF7",
            fg="#ffffff",
            relief=tk.FLAT,
            bd=0,
            font=("Segoe UI Variable", 9, "bold"),
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._abrir_gestor_desde_wizard,
        ).pack()
        tk.Button(
            f,
            text="📖 Guía de motores",
            bg="#f0f0f5",
            fg="#7C5EF7",
            relief=tk.FLAT,
            bd=0,
            font=("Segoe UI Variable", 9),
            padx=14,
            pady=4,
            cursor="hand2",
            command=self._abrir_guia_motores,
        ).pack(pady=(6, 0))

    def _wizard_paso_3(self):
        f = self._wizard_frame_contenido
        tk.Label(
            f,
            text="Motor IA — Procesamiento de texto",
            bg="#f0f0f5",
            fg="#1a1a2e",
            font=("Segoe UI Variable", 11, "bold"),
        ).pack(pady=(24, 6))
        tk.Label(
            f,
            text="La IA mejora, formatea y procesa el texto dictado.",
            bg="#f0f0f5",
            fg="#444444",
            font=("Segoe UI Variable", 10),
        ).pack()
        tk.Label(
            f,
            text="Necesitas una API Key gratuita — encontrarás instrucciones\n"
            "paso a paso dentro de Configuración.",
            bg="#f0f0f5",
            fg="#666666",
            font=("Segoe UI Variable", 9),
            justify=tk.LEFT,
        ).pack(pady=(8, 12), padx=24, anchor=tk.W)
        tk.Button(
            f,
            text="Abrir Configuración de motores",
            bg="#7C5EF7",
            fg="#ffffff",
            relief=tk.FLAT,
            bd=0,
            font=("Segoe UI Variable", 9, "bold"),
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._abrir_config_motores,
        ).pack()
        tk.Button(
            f,
            text="📖 Guía de motores",
            bg="#f0f0f5",
            fg="#7C5EF7",
            relief=tk.FLAT,
            bd=0,
            font=("Segoe UI Variable", 9),
            padx=14,
            pady=4,
            cursor="hand2",
            command=self._abrir_guia_motores,
        ).pack(pady=(6, 0))

    def _wizard_paso_4(self):
        f = self._wizard_frame_contenido
        self._wizard_btn_siguiente.config(
            text="¡Empezar a usar SpeakMe!", command=lambda: self._wizard_finalizar()
        )
        self._wizard_btn_omitir.pack_forget()
        tk.Label(
            f,
            text="¡Todo listo!",
            bg="#f0f0f5",
            fg="#7C5EF7",
            font=("Segoe UI Variable", 13, "bold"),
        ).pack(pady=(30, 8))
        tk.Label(
            f,
            text="Pulsa  Ctrl derecho  para empezar a dictar.",
            bg="#f0f0f5",
            fg="#444444",
            font=("Segoe UI Variable", 10),
        ).pack(pady=(0, 12))

        try:
            from PIL import Image, ImageTk

            teclado_path = os.path.join(RESOURCE_DIR, "assets", "Teclado.png")
            teclado_img = Image.open(teclado_path).convert("RGBA")
            teclado_img.thumbnail((280, 120), Image.LANCZOS)
            self._wizard_teclado_img = ImageTk.PhotoImage(teclado_img)
            tk.Label(f, image=self._wizard_teclado_img, bg="#f0f0f5").pack(pady=(12, 0))
        except Exception:
            pass

        tk.Label(
            f,
            text="El texto aparecerá donde tengas el cursor.",
            bg="#f0f0f5",
            fg="#444444",
            font=("Segoe UI Variable", 10),
        ).pack(pady=(12, 0))
        tk.Label(
            f,
            text="Puedes consultar esta guía en cualquier momento\ndesde el icono de SpeakMe! en la bandeja del sistema.",
            bg="#f0f0f5",
            fg="#999999",
            font=("Segoe UI Variable", 8),
            justify=tk.CENTER,
        ).pack(pady=(16, 0))

    def _wizard_siguiente(self, wizard):
        if self._wizard_paso_actual < 4:
            self._wizard_mostrar_paso(self._wizard_paso_actual + 1)
        else:
            self._wizard_finalizar()

    def _wizard_omitir(self, wizard):
        if tk.messagebox.askyesno(
            "¿Abandonar la guía?",
            "¿Seguro que quieres salir de la guía?\nPodrás acceder a ella desde el menú de la bandeja.",
            parent=wizard,
        ):
            wizard.destroy()

    def _wizard_finalizar(self):
        self.config["bienvenida_mostrada"] = True
        guardar_config(self.config)
        self._wizard_ref.destroy()

    def _abrir_gestor_desde_wizard(self):
        # Cerrar config si está abierta para evitar conflictos
        if hasattr(self, "_config_win") and self._config_win:
            try:
                if self._config_win.win.winfo_exists():
                    self._config_win.win.destroy()
            except Exception:
                pass
            self._config_win = None
        self._abrir_configuracion()
        self.root.after(
            600,
            lambda: (
                self._config_win._mostrar_gestor_modelos()
                if hasattr(self, "_config_win") and self._config_win
                else None
            ),
        )

    def _abrir_config_motores(self):
        # Cerrar config si está abierta para forzar apertura en pestaña correcta
        if hasattr(self, "_config_win") and self._config_win:
            try:
                if self._config_win.win.winfo_exists():
                    self._config_win.win.destroy()
            except Exception:
                pass
            self._config_win = None
        self._abrir_configuracion(tab="Motores")

    def _abrir_guia_motores(self):
        import ctypes

        ruta = os.path.join(RESOURCE_DIR, "assets", "guia_motores.md")
        try:
            with open(ruta, encoding="utf-8") as f:
                contenido = f.read()
        except Exception:
            contenido = "No se pudo cargar la guía."

        popup = tk.Toplevel(self.root)
        popup.title("Guía de motores — SpeakMe!")
        popup.resizable(True, True)
        popup.geometry("640x520")

        try:
            popup.update()
            hwnd = ctypes.windll.user32.GetParent(popup.winfo_id()) or popup.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 35, ctypes.byref(ctypes.c_int(0x00F75E7C)), 4
            )
        except Exception:
            pass

        frame_guia = ttk.Frame(popup)
        frame_guia.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        frame_guia.rowconfigure(0, weight=1)
        frame_guia.columnconfigure(0, weight=1)

        txt = tk.Text(
            frame_guia, wrap=tk.WORD, font=("Segoe UI Variable", 10), padx=8, pady=8
        )
        txt.grid(row=0, column=0, sticky="nsew")

        sb = ttk.Scrollbar(frame_guia, command=txt.yview)
        sb.grid(row=0, column=1, sticky="ns")
        txt.config(yscrollcommand=sb.set)

        txt.insert(tk.END, contenido)
        txt.config(state="disabled")

        ttk.Button(popup, text="Cerrar", command=popup.destroy).pack(pady=(0, 8))

    def _set_inicio_windows(self, activo: bool):
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        if getattr(sys, "frozen", False):
            exe = sys.executable
        else:
            exe = f'pythonw "{os.path.abspath(__file__)}"'
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
            ) as k:
                if activo:
                    winreg.SetValueEx(k, "SpeakMe", 0, winreg.REG_SZ, exe)
                    log.info(f"Inicio con Windows activado: {exe}")
                else:
                    try:
                        winreg.DeleteValue(k, "SpeakMe")
                        log.info("Inicio con Windows eliminado")
                    except FileNotFoundError:
                        pass
        except Exception as e:
            log.error(f"Error registro inicio Windows: {e}")

    def _salir(self):
        if self.config.get("ia_motor", "ollama") == "ollama":
            cerrar_ollama()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()


import sys
import multiprocessing

if __name__ == "__main__":
    # Soporte para PyInstaller/Multiprocessing
    multiprocessing.freeze_support()

    app = SpeakMe()
    app.iniciar()
