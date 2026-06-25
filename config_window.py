import ctypes
import json
import os
import sys
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import webbrowser
import ai_processor
from ai_processor import MODOS, MODOS_DEFAULT, corregir_texto
import vocabulary
import history

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = BASE_DIR

MODOS_FILE = os.path.join(BASE_DIR, "modos.json")
_PREDEFINIDOS = frozenset(MODOS.keys())

# faster-whisper resuelve la mayoría de modelos en el repo Systran/faster-whisper-<nombre>,
# pero "large-v3-turbo" (alias "turbo") apunta a un repo distinto (ver faster_whisper.utils._MODELS).
_WHISPER_REPOS_ESPECIALES = {
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}


def _whisper_repo_id(nombre: str) -> str:
    return _WHISPER_REPOS_ESPECIALES.get(nombre, f"Systran/faster-whisper-{nombre}")


def _insertar_con_negrita(txt_widget, texto, tag_base):
    import re

    partes = re.split(r"\*\*(.+?)\*\*", texto)
    for i, parte in enumerate(partes):
        if i % 2 == 0:
            txt_widget.insert(tk.END, parte, tag_base)
        else:
            txt_widget.insert(tk.END, parte, "bold")


def _renderizar_markdown(txt_widget, contenido):
    txt_widget.config(state="normal")
    txt_widget.delete("1.0", tk.END)

    txt_widget.tag_config(
        "h1", font=("Segoe UI Variable", 14, "bold"), foreground="#7C5EF7", spacing3=8
    )
    txt_widget.tag_config(
        "h2", font=("Segoe UI Variable", 12, "bold"), foreground="#7C5EF7", spacing3=6
    )
    txt_widget.tag_config(
        "h3", font=("Segoe UI Variable", 11, "bold"), foreground="#aaaaff", spacing3=4
    )
    txt_widget.tag_config("bold", font=("Segoe UI Variable", 10, "bold"))
    txt_widget.tag_config("bullet", lmargin1=16, lmargin2=24)
    txt_widget.tag_config("separador", foreground="#555555")
    txt_widget.tag_config("normal", font=("Segoe UI Variable", 10))
    txt_widget.tag_config(
        "italic", font=("Segoe UI Variable", 10, "italic"), foreground="#aaaaaa"
    )

    for linea in contenido.split("\n"):
        if linea.startswith("# "):
            txt_widget.insert(tk.END, linea[2:] + "\n", "h1")
        elif linea.startswith("## "):
            txt_widget.insert(tk.END, linea[3:] + "\n", "h2")
        elif linea.startswith("### "):
            txt_widget.insert(tk.END, linea[4:] + "\n", "h3")
        elif linea.startswith("---") or linea.startswith("==="):
            txt_widget.insert(tk.END, "─" * 60 + "\n", "separador")
        elif linea.startswith("- ") or linea.startswith("* "):
            _insertar_con_negrita(txt_widget, "• " + linea[2:] + "\n", "bullet")
        elif linea.strip() == "":
            txt_widget.insert(tk.END, "\n")
        else:
            _insertar_con_negrita(txt_widget, linea + "\n", "normal")

    txt_widget.config(state="disabled")


class ConfigWindow:
    def __init__(self, parent, config, on_save, start_tab=None, on_modos_change=None):
        self.config = dict(config)
        self.on_save = on_save
        self._on_modos_change = on_modos_change
        self._vars = {}
        self._grab_vars = {}
        self._motor_check_ok = (
            True  # True=OK por defecto; None=cambio pendiente de verificar; False=error
        )

        self.win = tk.Toplevel(parent)
        self.win.title("SpeakMe! — Configuración")
        self.win.resizable(True, True)
        self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self._on_intentar_cerrar)
        self.win.minsize(480, 400)
        try:
            import ctypes

            self.win.update()
            hwnd = (
                ctypes.windll.user32.GetParent(self.win.winfo_id())
                or self.win.winfo_id()
            )
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                35,
                ctypes.byref(ctypes.c_int(0x00F75E7C)),
                ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass

        self._centrar(start_tab)
        self._construir(start_tab)

    def _centrar(self, _start_tab=None):
        self.win.update_idletasks()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        ancho = min(1300, int(sw * 0.80))
        alto = min(850, int(sh * 0.85))
        x = (sw - ancho) // 2
        y = (sh - alto) // 2
        self.win.geometry(f"{ancho}x{alto}+{x}+{y}")

    def _abrir_guia_motores(self):
        ruta = os.path.join(RESOURCE_DIR, "assets", "guia_motores.md")
        try:
            with open(ruta, encoding="utf-8") as f:
                contenido = f.read()
        except Exception:
            contenido = "No se pudo cargar la guía."

        popup = tk.Toplevel(self.win)
        popup.title("Guía de motores — SpeakMe!")
        popup.attributes("-topmost", True)
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
            frame_guia,
            wrap=tk.WORD,
            font=("Segoe UI Variable", 10),
            padx=8,
            pady=8,
            state="normal",
        )
        txt.grid(row=0, column=0, sticky="nsew")

        sb = ttk.Scrollbar(frame_guia, command=txt.yview)
        sb.grid(row=0, column=1, sticky="ns")
        txt.config(yscrollcommand=sb.set)

        _renderizar_markdown(txt, contenido)

        ttk.Button(popup, text="Cerrar", command=popup.destroy).pack(pady=(0, 8))

    def _construir(self, start_tab=None):
        def _aplicar_barra():
            DWMWA_CAPTION_COLOR = 35
            color = 0x00D47800  # #0078d4 en BGR
            hwnd = self.win.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(ctypes.c_int(color)), 4
            )

        self.win.after(100, _aplicar_barra)

        # Botones fijos abajo
        style = ttk.Style()
        style.configure(".", font=("Segoe UI Variable Display", 10))
        style.configure(
            "TLabelframe.Label", font=("Segoe UI Variable Text", 10, "bold")
        )
        style.configure("TNotebook.Tab", font=("Segoe UI Variable Text", 10))
        style.configure("TButton", padding=3)
        style.configure("Accent.TButton", padding=3)
        style.configure("Main.TButton", padding=6)
        style.configure("Main.Accent.TButton", padding=6)
        style.configure("Vocab.TNotebook", tabmargins=[2, 5, 2, 0])
        style.configure(
            "Vocab.TNotebook.Tab",
            foreground="black",
            background="#d0d0d0",
            padding=[12, 4],
            font=("Segoe UI Variable", 9, "bold"),
        )

        botones = ttk.Frame(self.win)
        botones.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(
            botones,
            text="Cancelar",
            style="Main.TButton",
            command=self._on_intentar_cerrar,
        ).pack(side=tk.RIGHT, padx=(4, 0))
        self._btn_guardar = ttk.Button(
            botones, text="Aceptar", style="Main.Accent.TButton", command=self._guardar
        )
        self._btn_guardar.pack(side=tk.RIGHT, padx=(4, 0))
        self._btn_aplicar = ttk.Button(
            botones, text="Aplicar", style="Main.Accent.TButton", command=self._aplicar
        )
        self._btn_aplicar.pack(side=tk.RIGHT, padx=(4, 0))
        self._lbl_config_activa = ttk.Label(
            botones,
            text="",
            foreground="#7C5EF7",
            font=("Segoe UI Variable", 9, "bold"),
        )
        self._lbl_config_activa.pack(side=tk.LEFT, padx=(4, 0))

        inner = ttk.Frame(self.win)
        inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.notebook = ttk.Notebook(inner)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        tabs = [
            ("General", self._tab_general),
            ("Modos", self._tab_modos),
            ("Motores", self._tab_motores),
            ("Vocabulario", self._tab_vocabulario),
            ("Historial", self._tab_historial),
        ]
        for nombre, builder in tabs:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=nombre)
            builder(frame, nombre)

        def _on_tab_change(event):
            tab_idx = self.notebook.index(self.notebook.select())
            mostrar_aplicar = tab_idx in (0, 2)
            if mostrar_aplicar:
                self._btn_aplicar.pack(side=tk.RIGHT, padx=5)
            else:
                self._btn_aplicar.pack_forget()
            # Verificar cambios al salir de pestaña Modos (índice 1)
            if hasattr(self, "_ultima_tab") and self._ultima_tab == 1 and tab_idx != 1:
                if self._hay_cambios_sin_guardar():
                    respuesta = tk.messagebox.askyesno(
                        "Cambios sin guardar",
                        "Hay cambios sin guardar en el modo actual.\n¿Deseas guardarlos?",
                        parent=self.win,
                    )
                    if respuesta:
                        self._guardar_modo_actual()
            self._ultima_tab = tab_idx

            if tab_idx == 1:
                self.win.after(100, self._aplicar_tema_widgets)

        self.notebook.bind("<<NotebookTabChanged>>", _on_tab_change)
        # Aplicar estado inicial
        _on_tab_change(None)

        if start_tab:
            nombres = [t[0] for t in tabs]
            if start_tab in nombres:
                self.notebook.select(nombres.index(start_tab))
        self.win.after(0, self._aplicar_tema_widgets)

    def _aplicar_tema_widgets(self):
        tema = self.config.get("tema", "light")
        bg = "#1A1A1A" if tema == "dark" else "white"
        fg = "#F0F0F0" if tema == "dark" else "black"
        sel_bg = "#7C5EF7" if tema == "dark" else "#0078D7"
        try:
            self.win.update_idletasks()
        except Exception:
            pass
        for widget in self.win.winfo_children():
            self._aplicar_tema_recursivo(widget, bg, fg, sel_bg)
        # Segundo pase con delay para widgets en tabs no activas del Notebook
        try:
            self.win.after(
                150,
                lambda: [
                    self._aplicar_tema_recursivo(w, bg, fg, sel_bg)
                    for w in self.win.winfo_children()
                ],
            )
        except Exception:
            pass

    def _aplicar_tema_recursivo(self, widget, bg, fg, sel_bg):
        try:
            cls = widget.winfo_class()
            tema = self.config.get("tema", "light")
            border_color = "#4a4a6a" if tema == "dark" else "#cccccc"

            # Actualizar frames y labels de tk (no ttk) si usan colores de fondo estándar
            if cls == "Frame":
                try:
                    curr_bg = str(widget.cget("bg")).lower()
                    if curr_bg in ("white", "#1a1a1a", "#2a2a3a", "#f0f0f0"):
                        widget.configure(bg=bg)
                        if "highlightbackground" in widget.keys():
                            widget.configure(highlightbackground=border_color)
                except Exception:
                    pass
            elif cls == "Label":
                try:
                    curr_bg = str(widget.cget("bg")).lower()
                    if curr_bg in ("white", "#1a1a1a", "#2a2a3a", "#f0f0f0"):
                        widget.configure(bg=bg, fg=fg)
                except Exception:
                    pass
            elif cls == "TLabel":
                # Para ttk.Label, solo forzar foreground si el tema lo requiere
                try:
                    widget.configure(foreground=fg)
                except Exception:
                    pass
            elif cls == "Button":
                # Para botones tk (no ttk) usados en el toggle de modos
                try:
                    curr_bg = str(widget.cget("bg")).lower()
                    # Si es un botón inactivo (gris claro o gris oscuro)
                    if curr_bg in ("#e0e0e0", "#333333"):
                        bg_btn = "#333333" if tema == "dark" else "#e0e0e0"
                        fg_btn = "#f0f0f0" if tema == "dark" else "#333333"
                        widget.configure(bg=bg_btn, fg=fg_btn)
                except Exception:
                    pass

            elif cls in ("Text", "Listbox", "Entry"):
                font = str(widget.cget("font"))
                if "Cascadia" not in font:
                    # Guardar y restaurar state para poder aplicar color a widgets disabled
                    try:
                        current_state = widget.cget("state")
                        widget.config(state="normal")
                        widget.configure(
                            bg=bg,
                            fg=fg,
                            insertbackground=fg,
                            selectbackground=sel_bg,
                            highlightbackground=border_color,
                        )
                        widget.config(state=current_state)
                    except Exception:
                        widget.configure(
                            bg=bg,
                            fg=fg,
                            insertbackground=fg,
                            selectbackground=sel_bg,
                            highlightbackground=border_color,
                        )
        except Exception:
            pass
        for child in widget.winfo_children():
            self._aplicar_tema_recursivo(child, bg, fg, sel_bg)

    def _tab_placeholder(self, frame, nombre):
        ttk.Label(
            frame, text=f"Configuración de {nombre} (próximamente)", foreground="gray"
        ).pack(expand=True)

    # ── PESTAÑA GENERAL ───────────────────────────────────────────────────────

    def _tab_general(self, frame, _):
        frame.columnconfigure(0, weight=1)
        PAD = {"padx": 8, "pady": 3, "sticky": "w"}
        row = 0

        # ── Idioma + Backup ──────────────────────────────────────────────────
        top_row = ttk.Frame(frame)
        top_row.grid(row=row, column=0, sticky="ew", padx=10, pady=(10, 4))
        row += 1
        top_row.columnconfigure(0, weight=1)
        top_row.columnconfigure(1, weight=1)
        top_row.columnconfigure(2, weight=1)

        sec = ttk.LabelFrame(top_row, text="Idioma")
        sec.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        sec.columnconfigure(1, weight=1)

        ttk.Label(sec, text="Idioma app:").grid(row=0, column=0, **PAD)
        cur_app = self.config.get("idioma_app", "es")
        var_app = tk.StringVar(value="Español" if cur_app == "es" else "Español")
        ttk.Combobox(
            sec,
            textvariable=var_app,
            values=["Español", "English (próximamente)"],
            state="readonly",
            width=24,
        ).grid(row=0, column=1, **PAD)
        self._vars["idioma_app"] = (
            var_app,
            {"Español": "es", "English (próximamente)": "en"},
        )

        sec_backup = ttk.LabelFrame(top_row, text="Backup")
        sec_backup.grid(row=0, column=1, sticky="nsew", padx=(4, 4))
        ttk.Button(
            sec_backup,
            text="Exportar configuración",
            style="Accent.TButton",
            command=self._exportar_config,
        ).pack(anchor="w", padx=8, pady=(8, 4))
        ttk.Button(
            sec_backup, text="Importar configuración", command=self._importar_config
        ).pack(anchor="w", padx=8, pady=(0, 8))

        sec_tema = ttk.LabelFrame(top_row, text="Apariencia")
        sec_tema.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        var_tema = tk.StringVar(value=self.config.get("tema", "light"))
        ttk.Radiobutton(
            sec_tema, text="☀ Claro", variable=var_tema, value="light"
        ).pack(anchor="w", padx=8, pady=(8, 2))
        ttk.Radiobutton(
            sec_tema, text="🌙 Oscuro", variable=var_tema, value="dark"
        ).pack(anchor="w", padx=8, pady=(2, 8))
        self._vars["tema"] = (var_tema, None)

        # ── Inicio ───────────────────────────────────────────────────────────
        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, sticky="ew", padx=10, pady=4
        )
        row += 1
        sec2 = ttk.LabelFrame(frame, text="Inicio")
        sec2.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 4))
        row += 1

        var_inicio = tk.BooleanVar(value=self.config.get("inicio_windows", False))
        ttk.Checkbutton(sec2, text="Iniciar con Windows", variable=var_inicio).grid(
            row=0, column=0, **PAD
        )
        self._vars["inicio_windows"] = (var_inicio, None)

        var_minimizado = tk.BooleanVar(
            value=self.config.get("iniciar_minimizado", False)
        )
        ttk.Checkbutton(sec2, text="Iniciar minimizado", variable=var_minimizado).grid(
            row=1, column=0, **PAD
        )
        self._vars["iniciar_minimizado"] = (var_minimizado, None)

        # ── Micrófono ────────────────────────────────────────────────────────
        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, sticky="ew", padx=10, pady=4
        )
        row += 1
        sec3 = ttk.LabelFrame(frame, text="Micrófono")
        sec3.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 4))
        row += 1
        sec3.columnconfigure(1, weight=1)

        ttk.Label(sec3, text="Micrófono:").grid(row=0, column=0, **PAD)
        mics = self._listar_microfonos()
        self._mic_map = {nombre: idx for idx, nombre in mics}
        mic_names = list(self._mic_map.keys())
        cur_idx = self.config.get("mic_index", 1)
        cur_name = next(
            (n for n, i in self._mic_map.items() if i == cur_idx),
            mic_names[0] if mic_names else "",
        )
        var_mic = tk.StringVar(value=cur_name)
        ttk.Combobox(
            sec3, textvariable=var_mic, values=mic_names, state="readonly", width=32
        ).grid(row=0, column=1, **PAD)
        self._grab_vars["mic"] = var_mic

        ttk.Label(sec3, text="Modo grabación:").grid(row=1, column=0, **PAD)
        var_modo_grab = tk.StringVar(value=self.config.get("modo_grabacion", "ptt"))
        mf = ttk.Frame(sec3)
        mf.grid(row=1, column=1, **PAD)
        ttk.Radiobutton(
            mf,
            text="Push to Talk",
            variable=var_modo_grab,
            value="ptt",
            command=lambda: _toggle_umbral(),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(
            mf,
            text="Toggle",
            variable=var_modo_grab,
            value="toggle",
            command=lambda: _toggle_umbral(),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(
            mf,
            text="Auto",
            variable=var_modo_grab,
            value="auto",
            command=lambda: _toggle_umbral(),
        ).pack(side=tk.LEFT)
        ttk.Label(
            sec3,
            text="Auto: una pulsación corta activa grabación continua (Toggle)"
            " - mantener pulsado activa modo ráfaga (Push to Talk).",
            foreground="gray",
            font=("Segoe UI Variable", 8),
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 4))
        self._grab_vars["modo_grabacion"] = var_modo_grab

        # Umbral PTT — solo visible en modo Auto
        row_umbral = ttk.Frame(sec3)
        row_umbral.grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 4))
        ttk.Label(row_umbral, text="Umbral PTT:").pack(side=tk.LEFT, padx=(0, 8))
        var_umbral = tk.IntVar(value=self.config.get("umbral_auto_ms", 300))
        ttk.Radiobutton(
            row_umbral, text="Normal (300 ms)", variable=var_umbral, value=300
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(
            row_umbral, text="Largo (600 ms)", variable=var_umbral, value=600
        ).pack(side=tk.LEFT)
        self._vars["umbral_auto_ms"] = (var_umbral, None)

        def _toggle_umbral():
            if var_modo_grab.get() == "auto":
                row_umbral.grid()
            else:
                row_umbral.grid_remove()

        _toggle_umbral()

        ttk.Label(sec3, text="Trigger de grabación:").grid(row=4, column=0, **PAD)

        cur_trigger = self.config.get("trigger_type", "mouse")
        var_trig_mouse = tk.BooleanVar(value=cur_trigger in ("mouse", "both"))
        var_trig_teclado = tk.BooleanVar(value=cur_trigger in ("teclado", "both"))

        # rows 4-5 – Ratón + Teclado en grid para alineación perfecta
        trig_grid = ttk.Frame(sec3)
        trig_grid.grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=2)

        _GP = {"padx": (0, 8), "pady": 2, "sticky": "w"}

        # Ratón
        chk_mouse = ttk.Checkbutton(trig_grid, text="Ratón", variable=var_trig_mouse)
        chk_mouse.grid(row=0, column=0, **_GP)
        ttk.Label(trig_grid, text="Botón:").grid(
            row=0, column=1, padx=(0, 4), pady=2, sticky="w"
        )
        var_boton = tk.StringVar(value=self.config.get("trigger_button", "x2"))
        ent_boton = ttk.Entry(
            trig_grid, textvariable=var_boton, width=12, state="readonly"
        )
        ent_boton.grid(row=0, column=2, padx=(0, 4), pady=2, sticky="ew")
        btn_cap_m = ttk.Button(trig_grid, text="Capturar", style="Accent.TButton")
        btn_cap_m.grid(row=0, column=3, pady=2)
        btn_cap_m.config(
            command=lambda: self._capturar_boton_mouse(var_boton, btn_cap_m)
        )
        self._grab_vars["trigger_button"] = var_boton
        row_mouse = trig_grid  # alias para _sync_trigger_type

        # Teclado
        chk_teclado = ttk.Checkbutton(
            trig_grid, text="Teclado", variable=var_trig_teclado
        )
        chk_teclado.grid(row=1, column=0, **_GP)
        ttk.Label(trig_grid, text="Tecla:").grid(
            row=1, column=1, padx=(0, 4), pady=2, sticky="w"
        )
        var_tecla = tk.StringVar(value=self.config.get("trigger_tecla", "ctrl_r"))
        ent_tecla = ttk.Entry(
            trig_grid, textvariable=var_tecla, width=12, state="readonly"
        )
        ent_tecla.grid(row=1, column=2, padx=(0, 4), pady=2, sticky="ew")
        btn_cap_t = ttk.Button(trig_grid, text="Capturar", style="Accent.TButton")
        btn_cap_t.grid(row=1, column=3, pady=2)
        btn_cap_t.config(command=lambda: self._capturar_tecla(var_tecla, btn_cap_t))
        self._grab_vars["trigger_tecla"] = var_tecla
        row_kbd = trig_grid  # alias para _sync_trigger_type

        _syncing = [False]

        def _sync_trigger_type(*_):
            if _syncing[0]:
                return
            m, t = var_trig_mouse.get(), var_trig_teclado.get()
            # Impedir que ambos queden desmarcados
            if not m and not t:
                _syncing[0] = True
                var_trig_mouse.set(True)
                m = True
                _syncing[0] = False
            if m and t:
                self._grab_vars["trigger_type"].set("both")
            elif t:
                self._grab_vars["trigger_type"].set("teclado")
            else:
                self._grab_vars["trigger_type"].set("mouse")
            ent_boton.configure(state="readonly" if m else "disabled")
            btn_cap_m.configure(state="normal" if m else "disabled")
            ent_tecla.configure(state="readonly" if t else "disabled")
            btn_cap_t.configure(state="normal" if t else "disabled")

        var_trig_mouse.trace_add("write", _sync_trigger_type)
        var_trig_teclado.trace_add("write", _sync_trigger_type)

        var_trigger_type = tk.StringVar(value=cur_trigger)
        self._grab_vars["trigger_type"] = var_trigger_type
        _sync_trigger_type()

        # ── Widget flotante ──────────────────────────────────────────────────
        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, sticky="ew", padx=10, pady=4
        )
        row += 1
        sec4 = ttk.LabelFrame(frame, text="Widget flotante")
        sec4.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 4))
        row += 1
        sec4.columnconfigure(1, weight=1)

        ttk.Label(sec4, text="Posición:").grid(row=0, column=0, **PAD)
        pos_frame = ttk.Frame(sec4)
        pos_frame.grid(row=0, column=1, **PAD)
        var_pos = tk.StringVar(value=self.config.get("widget_posicion", "centro"))
        ttk.Radiobutton(
            pos_frame, text="Centro", variable=var_pos, value="centro"
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(
            pos_frame, text="Derecha", variable=var_pos, value="lateral"
        ).pack(side=tk.LEFT)
        self._vars["widget_posicion"] = (var_pos, None)
        ttk.Label(pos_frame, text="Color:").pack(side=tk.LEFT, padx=(16, 4))
        self._var_widget_color = tk.StringVar(
            value=self.config.get("widget_color_inactivo", "#888888")
        )
        self._btn_color_widget = tk.Label(
            pos_frame,
            text="",
            width=4,
            height=1,
            bg=self._var_widget_color.get(),
            relief="solid",
            bd=1,
            cursor="hand2",
        )
        self._btn_color_widget.pack(side=tk.LEFT)
        self._btn_color_widget.bind("<Button-1>", lambda _: self._elegir_color_widget())
        self._vars["widget_color_inactivo"] = (self._var_widget_color, None)

        ttk.Label(sec4, text="Tamaño:").grid(row=1, column=0, **PAD)
        size_frame = ttk.Frame(sec4)
        size_frame.grid(row=1, column=1, sticky="w", padx=8, pady=3)
        var_widget_size = tk.StringVar(value=self.config.get("widget_size", "normal"))
        ttk.Combobox(
            size_frame,
            textvariable=var_widget_size,
            values=["pequeño", "normal", "grande"],
            state="readonly",
            width=12,
        ).pack(side=tk.LEFT, padx=(0, 12))
        self._vars["widget_size"] = (var_widget_size, None)
        var_widget_motor = tk.BooleanVar(value=self.config.get("widget_motor", True))
        ttk.Checkbutton(size_frame, text="Motor IA", variable=var_widget_motor).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self._vars["widget_motor"] = (var_widget_motor, None)
        var_vram = tk.BooleanVar(value=self.config.get("widget_vram", True))
        ttk.Checkbutton(size_frame, text="VRAM disponible", variable=var_vram).pack(
            side=tk.LEFT
        )
        self._vars["widget_vram"] = (var_vram, None)
        var_topmost = tk.BooleanVar(value=self.config.get("widget_topmost", True))
        ttk.Checkbutton(
            size_frame, text="Widget en primer plano", variable=var_topmost
        ).pack(side=tk.LEFT, padx=(10, 0))
        self._vars["widget_topmost"] = (var_topmost, None)

        # ── Atajos ───────────────────────────────────────────────────────────
        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, sticky="ew", padx=10, pady=4
        )
        row += 1
        sec5 = ttk.LabelFrame(frame, text="Atajos")
        sec5.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 4))
        row += 1
        sec5.columnconfigure(1, weight=1)

        self._atajo_vars = {}
        ATAJOS = [
            ("Nueva nota:", "atajo_nota", "<ctrl>+<alt>+n"),
        ]
        for r, (label, key, default) in enumerate(ATAJOS):
            ttk.Label(sec5, text=label).grid(
                row=r, column=0, sticky="w", padx=10, pady=4
            )
            var = tk.StringVar(value=self.config.get(key, default))
            self._atajo_vars[key] = var
            row_atajo = ttk.Frame(sec5)
            row_atajo.grid(row=r, column=1, sticky="w", pady=4)
            ttk.Entry(row_atajo, textvariable=var, state="readonly", width=22).pack(
                side=tk.LEFT, padx=(0, 4)
            )
            btn_c = ttk.Button(
                row_atajo, text="Capturar", width=9, style="Accent.TButton"
            )
            btn_c.pack(side=tk.LEFT, padx=(0, 2))
            btn_c.config(command=lambda v=var, b=btn_c: self._capturar_atajo(v, b))
            ttk.Button(
                row_atajo, text="✕", width=3, command=lambda v=var: v.set("")
            ).pack(side=tk.LEFT)

        # ── Acerca de ────────────────────────────────────────────────────────
        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, sticky="ew", padx=10, pady=4
        )
        row += 1
        sec6 = ttk.LabelFrame(frame, text="Acerca de")
        sec6.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 10))
        row += 1

        about_row = ttk.Frame(sec6)
        about_row.pack(fill=tk.X, padx=10, pady=(8, 10))

        try:
            from PIL import Image, ImageTk

            _logo = Image.open(os.path.join(RESOURCE_DIR, "assets", "SpeakMe_logo.png"))
            _logo = _logo.resize((64, 64), Image.LANCZOS)
            self._logo_img = ImageTk.PhotoImage(_logo)
            ttk.Label(about_row, image=self._logo_img).pack(side=tk.LEFT, padx=(0, 12))
        except Exception:
            pass

        about_text = ttk.Frame(about_row)
        about_text.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(
            about_text, text="SpeakMe! v0.9.5", font=("Segoe UI Variable", 10, "bold")
        ).pack(anchor="w", pady=(0, 6))
        btn_about = ttk.Frame(about_text)
        btn_about.pack(anchor="w")
        ttk.Button(
            btn_about, text="Buscar actualización  (próximamente)", state="disabled"
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btn_about,
            text="Ver en GitHub",
            command=lambda: webbrowser.open("https://github.com/TonynoARS/SpeakMe"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btn_about,
            text="☕ Apoyar el proyecto",
            command=lambda: webbrowser.open("https://ko-fi.com/speakme"),
        ).pack(side=tk.LEFT)

        def _toggle_dev(_=None):
            tabs_text = [
                self.notebook.tab(i, "text") for i in range(self.notebook.index("end"))
            ]
            if "Desarrollador" in tabs_text:
                for i in range(self.notebook.index("end")):
                    if self.notebook.tab(i, "text") == "Desarrollador":
                        self.notebook.forget(i)
                        break
            else:
                dev_frame = ttk.Frame(self.notebook)
                self.notebook.add(dev_frame, text="Desarrollador")
                self._tab_desarrollador(dev_frame, "Desarrollador")
                self.notebook.select(dev_frame)

        frame.bind_all("<Control-Shift-D>", _toggle_dev)
        frame.bind_all("<Control-Shift-d>", _toggle_dev)

    def _tab_desarrollador(self, frame, _):
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)

        _LOG_PATH = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "speakme.log"
        )

        # Wrapper editor
        f_wrapper = ttk.LabelFrame(
            frame, text="Wrapper de prompt (marcadores anti-instrucción)"
        )
        f_wrapper.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        f_wrapper.columnconfigure(0, weight=1)
        self._txt_wrapper = tk.Text(
            f_wrapper, wrap=tk.WORD, height=5, font=("Segoe UI Variable", 9)
        )
        self._txt_wrapper.insert(
            "1.0",
            self.config.get(
                "prompt_wrapper", ai_processor._INSTRUCCION_MARCADORES_DEFAULT
            ),
        )
        self._txt_wrapper.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))

        def _guardar_wrapper():
            val = self._txt_wrapper.get("1.0", tk.END).rstrip("\n")
            self.config["prompt_wrapper"] = val
            self.on_save(self.config)

        ttk.Button(f_wrapper, text="Guardar", command=_guardar_wrapper).grid(
            row=1, column=0, sticky="e", padx=4, pady=(0, 4)
        )

        header = ttk.Frame(frame)
        header.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(4, 4))
        ttk.Label(
            header, text="speakme.log", font=("Segoe UI Variable", 9, "bold")
        ).pack(side=tk.LEFT)

        txt = tk.Text(
            frame,
            wrap=tk.NONE,
            font=("Cascadia Code", 9),
            state="normal",
            cursor="arrow",
            background="#1e1e2e",
            foreground="#cdd6f4",
        )
        txt.grid(row=2, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))

        sb_v = ttk.Scrollbar(frame, command=txt.yview)
        sb_v.grid(row=2, column=1, sticky="ns", pady=(0, 8))
        sb_h = ttk.Scrollbar(frame, orient="horizontal", command=txt.xview)
        sb_h.grid(row=3, column=0, sticky="ew", padx=(8, 0))
        txt.config(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)

        # Readonly: bloquear edición pero permitir selección y Ctrl+C
        txt.bind(
            "<Key>",
            lambda e: (
                "break"
                if e.state & 0x4 == 0 or e.keysym not in ("c", "C", "a", "A")
                else None
            ),
        )
        txt.bind("<Control-c>", lambda _: None)
        txt.bind("<Control-C>", lambda _: None)
        txt.bind("<Control-a>", lambda _: (txt.tag_add("sel", "1.0", tk.END), "break"))
        txt.bind("<Control-A>", lambda _: (txt.tag_add("sel", "1.0", tk.END), "break"))

        var_scroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(header, text="Auto-scroll", variable=var_scroll).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

        def _copiar_log():
            contenido = txt.get("1.0", tk.END)
            frame.clipboard_clear()
            frame.clipboard_append(contenido)

        def _limpiar_log():
            try:
                open(_LOG_PATH, "w").close()
            except Exception:
                pass

        ttk.Button(header, text="Copiar", command=_copiar_log).pack(
            side=tk.RIGHT, padx=(0, 4)
        )
        ttk.Button(header, text="Limpiar", command=_limpiar_log).pack(side=tk.RIGHT)

        def _actualizar():
            try:
                if txt.tag_ranges("sel"):
                    frame.after(1000, _actualizar)
                    return
                with open(_LOG_PATH, encoding="utf-8", errors="replace") as f:
                    contenido = f.read()
                if contenido != txt.get("1.0", tk.END):
                    pos = txt.yview()
                    txt.delete("1.0", tk.END)
                    txt.insert("1.0", contenido)
                    if var_scroll.get():
                        txt.see(tk.END)
                    else:
                        txt.yview_moveto(pos[0])
            except Exception:
                pass
            frame.after(1000, _actualizar)

        _actualizar()

    def _reset_coste_sesion(self):
        motor = self._var_motor.get()
        self.config[f"{motor}_coste_sesion"] = 0.0
        self._lbl_coste_sesion.config(text="$0.000000")

    def _exportar_config(self):
        import zipfile, json as _json
        from tkinter import filedialog, messagebox

        dest = filedialog.asksaveasfilename(
            parent=self.win,
            defaultextension=".zip",
            filetypes=[("ZIP", "*.zip")],
            initialfile="speakme_backup.zip",
            title="Exportar configuración",
        )
        if not dest:
            return
        base = os.path.dirname(os.path.abspath(__file__))
        _CLAVES_API = {"groq_key", "gemini_key", "openai_key"}
        try:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                cfg_clean = {
                    k: v for k, v in self.config.items() if k not in _CLAVES_API
                }
                zf.writestr(
                    "config.json", _json.dumps(cfg_clean, ensure_ascii=False, indent=2)
                )
                for nombre in ("modos.json", "vocabulario.json"):
                    ruta = os.path.join(base, nombre)
                    if os.path.exists(ruta):
                        zf.write(ruta, nombre)
            messagebox.showinfo(
                "Exportar", "Configuración exportada correctamente.", parent=self.win
            )
        except Exception as e:
            messagebox.showerror(
                "Exportar", f"Error al exportar:\n{e}", parent=self.win
            )

    def _importar_config(self):
        import zipfile, json as _json
        from tkinter import filedialog, messagebox

        if not messagebox.askokcancel(
            "Importar configuración",
            "Esto sobreescribirá la configuración actual, los modos y el vocabulario.\n\n"
            "¿Continuar?",
            parent=self.win,
        ):
            return
        src = filedialog.askopenfilename(
            parent=self.win,
            filetypes=[("ZIP", "*.zip")],
            title="Importar configuración",
        )
        if not src:
            return
        base = os.path.dirname(os.path.abspath(__file__))
        try:
            with zipfile.ZipFile(src, "r") as zf:
                nombres = zf.namelist()
                for nombre in ("modos.json", "vocabulario.json"):
                    if nombre in nombres:
                        zf.extract(nombre, base)
                if "config.json" in nombres:
                    nueva = _json.loads(zf.read("config.json").decode("utf-8"))
                    for k, v in nueva.items():
                        self.config[k] = v

            # Recargar MODOS desde el nuevo modos.json
            modos_path = os.path.join(base, "modos.json")
            if os.path.exists(modos_path):
                with open(modos_path, encoding="utf-8") as f:
                    nuevos_modos = _json.load(f)

                # Migración de modos legacy al nuevo formato modular
                for k, modo in nuevos_modos.items():
                    if "instrucciones" not in modo:
                        modo["instrucciones"] = modo.get(
                            "prompt_es", modo.get("prompt", "")
                        )
                    if "base" not in modo:
                        modo["base"] = ""
                    if "ejemplos" not in modo:
                        modo["ejemplos"] = []

                ai_processor.MODOS.clear()
                ai_processor.MODOS.update(nuevos_modos)
                self._modos_data = dict(nuevos_modos)
                self._modos_keys = list(nuevos_modos.keys())

            self.on_save(self.config)
            self._notify_modos_change()

            # Refrescar pestaña Modos si está visible
            if hasattr(self, "_modos_listbox"):
                self._modos_listbox.delete(0, tk.END)
                for k in self._modos_keys:
                    self._modos_listbox.insert(tk.END, self._nombre_lista(k))
                if self._modos_keys:
                    self._modos_listbox.selection_set(0)
                    self._modos_listbox.event_generate("<<ListboxSelect>>")

            messagebox.showinfo(
                "Importar",
                "Configuración importada. Reinicia SpeakMe para aplicar todos los cambios.",
                parent=self.win,
            )
        except Exception as e:
            messagebox.showerror(
                "Importar", f"Error al importar:\n{e}", parent=self.win
            )

    def _listar_microfonos(self):
        _EXCLUIR = ("stereo mix", "pc speaker", "output", "wasapi")
        try:
            import pyaudio

            p = pyaudio.PyAudio()
            mics = []
            seen_names = set()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) <= 0:
                    continue
                nombre = info["name"]
                nombre_lower = nombre.lower()
                if any(ex in nombre_lower for ex in _EXCLUIR):
                    continue
                if nombre in seen_names:
                    continue
                seen_names.add(nombre)
                mics.append((i, nombre))
            p.terminate()
            return mics
        except Exception:
            return []

    def _toggle_trigger(self, tipo, frame_mouse, frame_kbd):
        if tipo == "mouse":
            frame_mouse.grid()
            frame_kbd.grid_remove()
        else:
            frame_mouse.grid_remove()
            frame_kbd.grid()

    def _capturar_boton_mouse(self, var_boton, btn):
        from pynput import mouse as ms

        btn.config(text="Esperando...", state="disabled")

        _boton_map = {
            ms.Button.x1: "x1",
            ms.Button.x2: "x2",
            ms.Button.middle: "middle",
        }

        def on_click(x, y, button, pressed):
            if not pressed:
                return
            nombre = _boton_map.get(button, str(button).split(".")[-1])
            self.win.after(0, lambda: var_boton.set(nombre))
            self.win.after(0, lambda: btn.config(text="Capturar", state="normal"))
            return False

        t = ms.Listener(on_click=on_click)
        t.daemon = True
        t.start()

    def _capturar_tecla(self, var_tecla, btn):
        from pynput import keyboard as kb

        btn.config(text="Esperando...", state="disabled")

        def on_press(key):
            nombre = key.name if hasattr(key, "name") else str(key).strip("'")
            self.win.after(0, lambda: var_tecla.set(nombre))
            self.win.after(0, lambda: btn.config(text="Capturar", state="normal"))
            return False

        t = kb.Listener(on_press=on_press)
        t.daemon = True
        t.start()

    # ── PESTAÑA MODOS ─────────────────────────────────────────────────────────

    def _cargar_modos_custom(self):
        try:
            with open(MODOS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _guardar_modos_json(self):
        import logging

        log = logging.getLogger(__name__)
        tmp = MODOS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._modos_data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, MODOS_FILE)
        log.info(
            f"modos.json guardado con {len(self._modos_data)} modos: {list(self._modos_data.keys())}"
        )
        import ai_processor

        ai_processor._cargar_modos_persistidos()
        if callable(self._on_modos_change):
            self._on_modos_change()

    def _instalar_modelo_ollama(self, nombre=None):
        from tkinter import simpledialog
        import threading, subprocess

        if not nombre:
            nombre = simpledialog.askstring(
                "Instalar modelo Ollama",
                "Nombre del modelo (ej: llama3.2:3b, mistral:7b):",
                parent=self.win,
            )
        if not nombre:
            return
        self._lbl_ia_activar.config(text=f"Descargando {nombre}...", foreground="gray")

        def run():
            try:
                result = subprocess.run(
                    ["ollama", "pull", nombre],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    self.win.after(
                        0,
                        lambda: self._lbl_ia_activar.config(
                            text=f"✓ {nombre} instalado", foreground="green"
                        ),
                    )
                    self.win.after(0, self._refrescar_modelos_ollama)
                else:
                    self.win.after(
                        0,
                        lambda: self._lbl_ia_activar.config(
                            text=f"✗ Error: {result.stderr[:60]}", foreground="red"
                        ),
                    )
            except subprocess.TimeoutExpired:
                self.win.after(
                    0,
                    lambda: self._lbl_ia_activar.config(
                        text="✗ Timeout — modelo muy grande", foreground="red"
                    ),
                )
            except Exception as e:
                self.win.after(
                    0,
                    lambda e_val=e: self._lbl_ia_activar.config(
                        text=f"✗ {str(e_val)[:60]}", foreground="red"
                    ),
                )

        threading.Thread(target=run, daemon=True).start()

    def _ver_modelos_disponibles(self):
        win = tk.Toplevel(self.win)
        win.title("Modelos disponibles para SpeakMe")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.geometry("480x450")

        modelos = [
            ("llama3.2:3b", "~2GB", "Rápido, ligero"),
            ("llama3.1:8b", "~4.5GB", "Equilibrio calidad/velocidad"),
            ("qwen2.5:7b", "~4.5GB", "Muy bueno en español"),
            ("qwen2.5:3b", "~2GB", "Rápido, bueno en español"),
            ("mistral:7b", "~4GB", "Bueno para edición de texto"),
            ("phi3:mini", "~2GB", "Muy rápido, ligero"),
            ("gemma2:2b", "~1.5GB", "Ultra ligero"),
            ("deepseek-r1:7b", "~4.5GB", "Razonamiento avanzado"),
            ("llama3.2:1b", "~1GB", "Mínimo, pruebas"),
        ]

        ttk.Label(
            win,
            text="Modelos recomendados para SpeakMe",
            font=("Segoe UI Variable", 10, "bold"),
        ).pack(pady=(12, 4))
        ttk.Label(
            win,
            text="Los modelos se cargan en VRAM (GPU) o RAM según disponibilidad.",
            foreground="gray",
        ).pack(pady=(0, 2))
        ttk.Label(
            win,
            text="Con GPU dedicada el rendimiento es significativamente mayor.",
            foreground="gray",
        ).pack(pady=(0, 8))

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=12)

        for nombre, tamaño, desc in modelos:
            row = ttk.Frame(frame, relief="ridge")
            row.pack(fill=tk.X, pady=2)
            ttk.Label(
                row, text=nombre, font=("Segoe UI Variable", 9, "bold"), width=18
            ).pack(side=tk.LEFT, padx=8, pady=6)
            ttk.Label(row, text=tamaño, foreground="gray", width=6).pack(side=tk.LEFT)
            ttk.Label(row, text=desc, foreground="gray").pack(side=tk.LEFT, padx=4)

            def instalar(n=nombre):
                win.destroy()
                self._instalar_modelo_ollama(n)

            ttk.Button(
                row, text="Instalar", width=8, style="Accent.TButton", command=instalar
            ).pack(side=tk.RIGHT, padx=8, pady=4)

        ttk.Separator(win, orient="horizontal").pack(fill=tk.X, padx=12, pady=4)
        frame_custom = ttk.Frame(win)
        frame_custom.pack(fill=tk.X, padx=12, pady=(0, 4))
        ttk.Label(frame_custom, text="Modelo personalizado:").pack(side=tk.LEFT)
        var_custom = tk.StringVar()
        ttk.Entry(frame_custom, textvariable=var_custom, width=20).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(
            frame_custom,
            text="Instalar",
            command=lambda: (
                [win.destroy(), self._instalar_modelo_ollama(var_custom.get().strip())]
                if var_custom.get().strip()
                else None
            ),
        ).pack(side=tk.LEFT)

        ttk.Button(win, text="Cerrar", command=win.destroy).pack(pady=8)

    def _refrescar_modelos_ollama(self):
        import subprocess

        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            lineas = result.stdout.strip().split("\n")[1:]
            modelos = [l.split()[0] for l in lineas if l.strip()]
        except subprocess.TimeoutExpired:
            modelos = []
        except Exception:
            modelos = []
        if hasattr(self, "_cb_ia_version"):
            self._cb_ia_version.config(values=modelos)
            actual = self._cb_ia_version.get()
            if modelos and actual not in modelos:
                self._cb_ia_version.set(modelos[0])
        if hasattr(self, "_lbl_ia_modelo"):
            if modelos:
                self._lbl_ia_modelo.config(
                    text=f"Ollama — {len(modelos)} modelo(s) instalado(s)"
                )
            else:
                self._lbl_ia_modelo.config(text="Ollama — no disponible")

    def _refrescar_modelos_groq(self):
        import requests as req

        key = self.config.get("groq_key", "")
        try:
            r = req.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=5,
            )
            modelos = sorted(m["id"] for m in r.json().get("data", []))
        except Exception:
            modelos = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
        if hasattr(self, "_cb_ia_version"):
            self._cb_ia_version.config(values=modelos)
            actual = self._cb_ia_version.get()
            if modelos and actual not in modelos:
                self._cb_ia_version.set(modelos[0])

    def _refrescar_modelos_openai(self):
        import requests as req, threading

        key = self.config.get("openai_key", "")
        if not key:
            return

        def _fetch():
            try:
                r = req.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10,
                )
                r.raise_for_status()
                ids = sorted(
                    set(
                        m["id"]
                        for m in r.json()["data"]
                        if m["id"].startswith(("gpt-4", "gpt-5"))
                    )
                )

                def _update():
                    if hasattr(self, "_cb_ia_version"):
                        self._cb_ia_version.config(values=ids)
                        actual = self._cb_ia_version.get()
                        if ids and actual not in ids:
                            self._cb_ia_version.set(ids[0])

                self.win.after(0, _update)
            except Exception:
                pass

        threading.Thread(target=_fetch, daemon=True).start()

    def _refrescar_modelos_gemini(self):
        import requests as req

        key = self.config.get("gemini_key", "")
        try:
            r = req.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                timeout=5,
            )
            modelos = sorted(
                m["name"].split("/")[-1]
                for m in r.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            )
        except Exception:
            modelos = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
        if hasattr(self, "_cb_ia_version"):
            self._cb_ia_version.config(values=modelos)
            actual = self._cb_ia_version.get()
            if modelos and actual not in modelos:
                self._cb_ia_version.set(modelos[0])

    def _on_modo_select(self, _event=None):
        sel = self._modos_listbox.curselection()
        if not sel:
            return

        # Verificar cambios sin guardar antes de cambiar de modo
        if hasattr(self, "_modo_seleccionado_key") and self._modo_seleccionado_key:
            key_actual = self._modo_seleccionado_key
            datos_actuales = self._modos_data.get(key_actual, {})
            modo_editor = (
                self._modo_editor_var.get()
                if hasattr(self, "_modo_editor_var")
                else "estructurado"
            )

            if modo_editor == "libre":
                texto_actual = self._txt_prompt_libre.get("1.0", tk.END).strip()
                texto_guardado = datos_actuales.get(
                    "prompt_libre", datos_actuales.get("prompt", "")
                ).strip()
                hay_cambios = texto_actual != texto_guardado
            else:
                base_actual = self._txt_base.get("1.0", tk.END).strip()
                prompt_actual = self._txt_prompt.get("1.0", tk.END).strip()
                hay_cambios = (
                    base_actual != datos_actuales.get("base", "").strip()
                    or prompt_actual
                    != datos_actuales.get(
                        "instrucciones", datos_actuales.get("prompt", "")
                    ).strip()
                )

            if hay_cambios:
                respuesta = tk.messagebox.askyesnocancel(
                    "Cambios sin guardar",
                    "Hay cambios sin guardar en el modo actual.\n\n"
                    "¿Deseas guardarlos antes de continuar?",
                    parent=self.win,
                )
                if respuesta is True:
                    self._guardar_modo_actual()
                elif respuesta is None:
                    # Cancelar — volver al modo anterior en la lista
                    try:
                        idx_actual = self._modos_keys.index(key_actual)
                        self._modos_listbox.selection_clear(0, tk.END)
                        self._modos_listbox.selection_set(idx_actual)
                    except (ValueError, IndexError):
                        pass
                    return

        key = self._modos_keys[sel[0]]
        self._modo_seleccionado_key = key
        datos = self._modos_data[key]

        # Actualizar campos básicos
        self._var_modo_nombre.set(datos.get("nombre", key))
        self._var_modo_desc.set(datos.get("descripcion", ""))

        # Actualizar estado de favorito y sistema
        es_fav = datos.get("favorito", False)
        es_sistema = datos.get("sistema", False)

        if hasattr(self, "_btn_favorito"):
            self._btn_favorito.config(text="★" if es_fav else "☆")

        # Cargar contenido en el editor modular
        self._txt_base.config(state="normal")
        self._txt_base.delete("1.0", tk.END)
        self._txt_base.insert("1.0", datos.get("base", ""))

        self._txt_prompt.config(state="normal")
        self._txt_prompt.delete("1.0", tk.END)
        self._txt_prompt.insert(
            "1.0",
            datos.get("instrucciones", datos.get("prompt_es", datos.get("prompt", ""))),
        )

        # Refrescar tarjetas de ejemplos
        if hasattr(self, "_frame_tarjetas"):
            self._refrescar_tarjetas_ejemplos(key)

        # Cargar prompt libre y modo editor
        modo_editor = datos.get("modo_editor", "estructurado")
        self._txt_prompt_libre.config(state="normal")
        self._txt_prompt_libre.delete("1.0", tk.END)
        self._txt_prompt_libre.insert(
            "1.0", datos.get("prompt_libre", datos.get("prompt", ""))
        )
        self._cambiar_modo_editor(modo_editor)

        import copy

        self._ejemplos_respaldo = copy.deepcopy(datos.get("ejemplos", []))

        # Actualizar estado visual de botones toggle
        tema = self.config.get("tema", "light")
        bg_inactive = "#333333" if tema == "dark" else "#e0e0e0"
        fg_inactive = "#F0F0F0" if tema == "dark" else "#333333"

        if modo_editor == "libre":
            self._btn_editor_libre.config(bg="#7C5EF7", fg="white", relief="flat")
            self._btn_editor_estructurado.config(
                bg=bg_inactive, fg=fg_inactive, relief="flat"
            )
        else:
            self._btn_editor_estructurado.config(
                bg="#7C5EF7", fg="white", relief="flat"
            )
            self._btn_editor_libre.config(bg=bg_inactive, fg=fg_inactive, relief="flat")

        # Actualizar tokens
        if hasattr(self, "_actualizar_tokens_prompt_es"):
            self._actualizar_tokens_prompt_es()

        # Parámetros avanzados
        self._var_temp_es.set(
            datos.get("temperatura_es", datos.get("temperatura", 0.1))
        )
        self._var_temp_en.set(
            datos.get("temperatura_en", datos.get("temperatura", 0.1))
        )
        self._var_top_p.set(datos.get("top_p", 0.9))
        self._var_top_k.set(datos.get("top_k", 40))
        self._var_auto_enter.set(datos.get("auto_enter", False))
        self._var_auto_enter_delay.set(datos.get("auto_enter_delay", 2))

        if hasattr(self, "_btn_eliminar"):
            self._btn_eliminar.config(state="disabled" if es_sistema else "normal")

        try:
            if hasattr(self, "_btn_restaurar"):
                self._btn_restaurar.config(
                    state="normal"
                    if (es_sistema and key in MODOS_DEFAULT)
                    else "disabled"
                )
        except NameError:
            pass

        self._refresh_lock_state(key)

    def _restaurar_modo_original(self):
        key = getattr(self, "_modo_seleccionado_key", None)
        if not key or key not in MODOS_DEFAULT:
            return
        nombre = self._modos_data[key].get("nombre", key)
        if not messagebox.askyesno(
            "Restaurar original",
            f"¿Restaurar el prompt original de '{nombre}'?\nSe perderán tus cambios.",
            parent=self.win,
        ):
            return
        orig = MODOS_DEFAULT[key]
        prompt_es_orig = orig["prompt_es"]
        prompt_en_orig = orig["prompt_en"]
        self._modos_data[key]["prompt"] = orig["prompt"]
        self._modos_data[key]["prompt_es"] = prompt_es_orig
        self._modos_data[key]["prompt_en"] = prompt_en_orig
        self._txt_prompt.delete("1.0", tk.END)
        self._txt_prompt.insert("1.0", prompt_es_orig)
        self._txt_prompt_en.delete("1.0", tk.END)
        self._txt_prompt_en.insert("1.0", prompt_en_orig)
        try:
            self._guardar_modos_json()
            ai_processor.MODOS[key].update(
                {
                    "prompt": orig["prompt"],
                    "prompt_es": prompt_es_orig,
                    "prompt_en": prompt_en_orig,
                }
            )
            self._lbl_guardado.config(
                text="✓ Prompt restaurado al original", fg="#007700"
            )
        except Exception as e:
            self._lbl_guardado.config(text=f"✗ Error: {str(e)[:40]}", fg="#cc0000")
        self.win.after(2000, lambda: self._lbl_guardado.config(text=""))

    def _guardar_modo_actual(self):
        import logging

        log = logging.getLogger(__name__)
        key = getattr(self, "_modo_seleccionado_key", None)
        if not key or key not in self._modos_data:
            log.info("Guardar modo: ningún modo seleccionado")
            return

        # Leer todos los campos del formulario, preservando 'sistema'
        base_val = self._txt_base.get("1.0", tk.END).strip()
        instrucciones_val = self._txt_prompt.get("1.0", tk.END).strip()
        ejemplos_val = self._modos_data[key].get("ejemplos", [])
        nuevo_nombre = self._var_modo_nombre.get().strip()

        # Ensamblar prompt completo
        ejemplos_txt = ""
        for ej in ejemplos_val:
            ejemplos_txt += (
                f"Entrada: {ej.get('entrada', '')}\nSalida: {ej.get('salida', '')}\n"
            )

        prompt_ensamblado = f"""<system_base>
{base_val}
</system_base>

<mode_instructions>
{instrucciones_val}
</mode_instructions>

<examples>
{ejemplos_txt}</examples>"""

        self._modos_data[key]["nombre"] = nuevo_nombre
        self._modos_data[key]["descripcion"] = self._var_modo_desc.get().strip()
        self._modos_data[key]["base"] = base_val
        self._modos_data[key]["instrucciones"] = instrucciones_val
        self._modos_data[key]["prompt"] = prompt_ensamblado
        self._modos_data[key]["prompt_es"] = prompt_ensamblado
        self._modos_data[key]["prompt_en"] = ""

        self._modos_data[key]["temperatura_es"] = round(self._var_temp_es.get(), 2)
        self._modos_data[key]["temperatura_en"] = round(self._var_temp_en.get(), 2)
        self._modos_data[key]["top_p"] = round(self._var_top_p.get(), 2)
        self._modos_data[key]["top_k"] = int(self._var_top_k.get())
        self._modos_data[key]["auto_enter"] = self._var_auto_enter.get()
        self._modos_data[key]["auto_enter_delay"] = int(
            self._var_auto_enter_delay.get()
        )
        # 'sistema' no se toca — conserva su valor original

        self._modos_data[key]["modo_editor"] = self._modo_editor_var.get()
        if self._modo_editor_var.get() == "libre":
            prompt_libre = self._txt_prompt_libre.get("1.0", tk.END).strip()
            self._modos_data[key]["prompt_libre"] = prompt_libre
            self._modos_data[key]["prompt"] = prompt_libre
            self._modos_data[key]["prompt_es"] = prompt_libre

        # Renombrar clave cuando el nombre cambia (solo modos de usuario)
        nuevo_nombre = self._var_modo_nombre.get().strip()
        if not self._modos_data[key].get("sistema", False):
            nuevo_key = nuevo_nombre.lower().replace(" ", "_")
            base, i = nuevo_key, 2
            while nuevo_key in self._modos_data and nuevo_key != key:
                nuevo_key = f"{base}_{i}"
                i += 1
            if nuevo_key != key:
                self._modos_data[nuevo_key] = self._modos_data.pop(key)
                idx_k = self._modos_keys.index(key)
                self._modos_keys[idx_k] = nuevo_key
                if self.config.get("modo_ia") == key:
                    self.config["modo_ia"] = nuevo_key
                ai_processor.MODOS[nuevo_key] = ai_processor.MODOS.pop(key, {})
                self._modo_seleccionado_key = nuevo_key
                log.info(f"Clave renombrada: '{key}' → '{nuevo_key}'")
                key = nuevo_key

        log.info(
            f"_guardar_modo_actual | key='{key}' | datos completos: {self._modos_data[key]}"
        )

        idx = self._modos_keys.index(key)
        self._modos_listbox.delete(idx)
        self._modos_listbox.insert(idx, self._nombre_lista(key))
        self._modos_listbox.selection_set(idx)

        try:
            self._guardar_modos_json()
            ai_processor.MODOS.update(self._modos_data)
            log.info(
                f"ai_processor.MODOS actualizado | claves: {list(ai_processor.MODOS.keys())}"
            )
            self._lbl_guardado.config(
                text="✓ Modo guardado correctamente", fg="#007700"
            )
            self._notify_modos_change()

            import copy

            self._ejemplos_respaldo = copy.deepcopy(
                self._modos_data[key].get("ejemplos", [])
            )

        except Exception as e:
            log.error(f"Error guardando modo: {e}")
            self._lbl_guardado.config(text=f"✗ Error: {str(e)[:40]}", fg="#cc0000")
        self.win.after(2000, lambda: self._lbl_guardado.config(text=""))

    def _hay_cambios_sin_guardar(self):
        key = getattr(self, "_modo_seleccionado_key", None)
        if not key or key not in self._modos_data:
            return False
        datos = self._modos_data[key]
        try:
            modo_editor = self._modo_editor_var.get()
            if modo_editor == "libre":
                actual = self._txt_prompt_libre.get("1.0", tk.END).strip()
                guardado = datos.get("prompt_libre", datos.get("prompt", "")).strip()
                return actual != guardado
            else:
                base_actual = self._txt_base.get("1.0", tk.END).strip()
                prompt_actual = self._txt_prompt.get("1.0", tk.END).strip()

                ejemplos_actuales = datos.get("ejemplos", [])
                ejemplos_cambiaron = ejemplos_actuales != getattr(
                    self, "_ejemplos_respaldo", ejemplos_actuales
                )

                return (
                    base_actual != datos.get("base", "").strip()
                    or prompt_actual
                    != datos.get("instrucciones", datos.get("prompt", "")).strip()
                    or ejemplos_cambiaron
                )
        except Exception:
            return False

    def _on_intentar_cerrar(self):
        if self._hay_cambios_sin_guardar():
            respuesta = tk.messagebox.askyesnocancel(
                "Cambios sin guardar",
                "Hay cambios sin guardar en el modo actual.\n\n"
                "¿Deseas guardarlos antes de cerrar?",
                parent=self.win,
            )
            if respuesta is True:
                self._guardar_modo_actual()
                self.win.destroy()
            elif respuesta is False:
                self.win.destroy()
            # None = cancelar, no cierra
        else:
            self.win.destroy()

    def _refrescar_tarjetas_ejemplos(self, key):
        for w in self._frame_tarjetas.winfo_children():
            w.destroy()

        ejemplos = self._modos_data[key].get("ejemplos", [])

        tema = self.config.get("tema", "light")
        card_bg = "#2a2a3a" if tema == "dark" else "white"
        card_fg = "#F0F0F0" if tema == "dark" else "#333333"
        card_fg_dim = "#aaaaaa" if tema == "dark" else "#555555"
        card_border = "#4a4a6a" if tema == "dark" else "#cccccc"

        for i, ej in enumerate(ejemplos):
            # Tarjeta
            card = tk.Frame(
                self._frame_tarjetas,
                bg=card_bg,
                highlightbackground=card_border,
                highlightthickness=1,
            )
            card.pack(fill=tk.X, pady=(0, 6))
            card.columnconfigure(0, weight=1)

            def _editar_ejemplo(idx=i, k=key):
                ej_data = self._modos_data[k]["ejemplos"][idx]

                popup = tk.Toplevel(self.win)
                popup.title(f"Editar ejemplo [{idx + 1}]")
                popup.attributes("-topmost", True)
                popup.resizable(False, False)
                popup.geometry("460x280")

                try:
                    popup.update()
                    import ctypes

                    hwnd = (
                        ctypes.windll.user32.GetParent(popup.winfo_id())
                        or popup.winfo_id()
                    )
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, 35, ctypes.byref(ctypes.c_int(0x00F75E7C)), 4
                    )
                except Exception:
                    pass

                f = ttk.Frame(popup)
                f.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)
                f.columnconfigure(0, weight=1)

                ttk.Label(
                    f,
                    text="Entrada (texto sucio STT):",
                    font=("Segoe UI Variable", 9, "bold"),
                ).grid(row=0, column=0, sticky="w", pady=(0, 2))
                txt_entrada = tk.Text(
                    f,
                    wrap=tk.WORD,
                    height=4,
                    font=("Segoe UI Variable", 9),
                    relief="solid",
                    bd=1,
                )
                txt_entrada.insert("1.0", ej_data.get("entrada", ""))
                txt_entrada.grid(row=1, column=0, sticky="ew", pady=(0, 8))

                ttk.Label(
                    f,
                    text="Salida (texto limpio esperado):",
                    font=("Segoe UI Variable", 9, "bold"),
                ).grid(row=2, column=0, sticky="w", pady=(0, 2))
                txt_salida = tk.Text(
                    f,
                    wrap=tk.WORD,
                    height=4,
                    font=("Segoe UI Variable", 9),
                    relief="solid",
                    bd=1,
                )
                txt_salida.insert("1.0", ej_data.get("salida", ""))
                txt_salida.grid(row=3, column=0, sticky="ew", pady=(0, 8))

                def _guardar_edicion():
                    entrada = txt_entrada.get("1.0", tk.END).strip()
                    salida = txt_salida.get("1.0", tk.END).strip()
                    if not entrada or not salida:
                        tk.messagebox.showwarning(
                            "Campos vacíos", "Rellena ambos campos.", parent=popup
                        )
                        return
                    self._modos_data[k]["ejemplos"][idx] = {
                        "entrada": entrada,
                        "salida": salida,
                    }
                    self._refrescar_tarjetas_ejemplos(k)
                    popup.destroy()

                ttk.Button(
                    f,
                    text="Guardar cambios",
                    style="Accent.TButton",
                    command=_guardar_edicion,
                ).grid(row=4, column=0, sticky="e")

            card.bind(
                "<Double-Button-1>", lambda e, idx=i, k=key: _editar_ejemplo(idx, k)
            )

            # Header tarjeta
            f_card_top = tk.Frame(card, bg=card_bg)
            f_card_top.pack(fill=tk.X, padx=6, pady=(4, 2))

            tk.Label(
                f_card_top,
                text=f"[{i + 1}]",
                bg=card_bg,
                fg=card_fg,
                font=("Segoe UI Variable", 9, "bold"),
                anchor="w",
            ).pack(side=tk.LEFT, padx=(6, 4))
            tk.Label(
                f_card_top,
                text=f"Entrada: {ej.get('entrada', '')[:55]}{'…' if len(ej.get('entrada', '')) > 55 else ''}",
                bg=card_bg,
                fg=card_fg,
                font=("Segoe UI Variable", 9),
                anchor="w",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

            def _eliminar(idx=i, k=key):
                self._modos_data[k]["ejemplos"].pop(idx)
                self._refrescar_tarjetas_ejemplos(k)

            tk.Button(
                f_card_top,
                text="✕",
                bg=card_bg,
                fg="#999999" if tema == "light" else "#777777",
                relief="flat",
                bd=0,
                font=("Segoe UI Variable", 9),
                cursor="hand2",
                command=_eliminar,
            ).pack(side=tk.RIGHT)

            # Salida
            tk.Label(
                card,
                text=f"       Salida: {ej.get('salida', '')[:55]}{'…' if len(ej.get('salida', '')) > 55 else ''}",
                bg=card_bg,
                fg=card_fg_dim,
                font=("Segoe UI Variable", 9),
                anchor="w",
            ).pack(fill=tk.X, padx=6, pady=(0, 4))

            for child in card.winfo_children():
                child.bind(
                    "<Double-Button-1>", lambda e, idx=i, k=key: _editar_ejemplo(idx, k)
                )
                # Propagar también a los hijos de los hijos (como f_card_top)
                for grandchild in child.winfo_children():
                    grandchild.bind(
                        "<Double-Button-1>",
                        lambda e, idx=i, k=key: _editar_ejemplo(idx, k),
                    )

    def _abrir_popup_ejemplo(self):
        key = (
            self._modo_seleccionado_key
            if hasattr(self, "_modo_seleccionado_key")
            else None
        )
        if not key:
            return

        ejemplos = self._modos_data[key].get("ejemplos", [])
        if len(ejemplos) >= 3:
            tk.messagebox.showinfo(
                "Límite alcanzado", "Máximo 3 ejemplos por modo.", parent=self.win
            )
            return

        popup = tk.Toplevel(self.win)
        popup.title("Nuevo ejemplo")
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.update_idletasks()
        pw, ph = 460, 280
        wx = self.win.winfo_x() + (self.win.winfo_width() - pw) // 2
        wy = self.win.winfo_y() + (self.win.winfo_height() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{wx}+{wy}")

        try:
            popup.update()
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(popup.winfo_id()) or popup.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 35, ctypes.byref(ctypes.c_int(0x00F75E7C)), 4
            )
        except Exception:
            pass

        f = ttk.Frame(popup)
        f.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)
        f.columnconfigure(0, weight=1)

        ttk.Label(
            f, text="Entrada (texto sucio STT):", font=("Segoe UI Variable", 9, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 2))
        txt_entrada = tk.Text(
            f,
            wrap=tk.WORD,
            height=4,
            font=("Segoe UI Variable", 9),
            relief="solid",
            bd=1,
        )
        txt_entrada.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(
            f,
            text="Salida (texto limpio esperado):",
            font=("Segoe UI Variable", 9, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(0, 2))
        txt_salida = tk.Text(
            f,
            wrap=tk.WORD,
            height=4,
            font=("Segoe UI Variable", 9),
            relief="solid",
            bd=1,
        )
        txt_salida.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        def _guardar_ejemplo():
            entrada = txt_entrada.get("1.0", tk.END).strip()
            salida = txt_salida.get("1.0", tk.END).strip()
            if not entrada or not salida:
                tk.messagebox.showwarning(
                    "Campos vacíos",
                    "Rellena ambos campos antes de guardar.",
                    parent=popup,
                )
                return
            if "ejemplos" not in self._modos_data[key]:
                self._modos_data[key]["ejemplos"] = []
            self._modos_data[key]["ejemplos"].append(
                {"entrada": entrada, "salida": salida}
            )
            # Refrescar vista de ejemplos
            self._refrescar_tarjetas_ejemplos(key)
            popup.destroy()

        ttk.Button(
            f, text="Guardar ejemplo", style="Accent.TButton", command=_guardar_ejemplo
        ).grid(row=4, column=0, sticky="e")

    def _notify_modos_change(self):
        if callable(self._on_modos_change):
            self._on_modos_change()

    def _elegir_color_widget(self):
        from tkinter import colorchooser

        color = colorchooser.askcolor(
            color=self._var_widget_color.get(),
            title="Color texto inactivo",
            parent=self.win,
        )
        if color[1]:
            self._var_widget_color.set(color[1])
            self._btn_color_widget.config(bg=color[1])

    def _crear_tooltip(self, widget, texto):
        tooltip = None

        def mostrar(_):
            nonlocal tooltip
            tooltip = tk.Toplevel(widget)
            tooltip.overrideredirect(True)
            tooltip.attributes("-topmost", True)
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tooltip.geometry(f"+{x}+{y}")
            tk.Label(
                tooltip,
                text=texto,
                font=("Segoe UI Variable Display", 9),
                bg="#FFFFCC",
                fg="#333333",
                relief="solid",
                bd=1,
                padx=6,
                pady=4,
                wraplength=280,
            ).pack()

        def ocultar(_):
            nonlocal tooltip
            if tooltip:
                tooltip.destroy()
                tooltip = None

        widget.bind("<Enter>", mostrar)
        widget.bind("<Leave>", ocultar)

    def _nombre_lista(self, key):
        datos = self._modos_data.get(key, {})
        nombre = datos.get("nombre", key)
        if datos.get("favorito", False):
            nombre = f"★ {nombre}"
        if datos.get("protegido", False):
            nombre = f"🔒 {nombre}"
        return nombre

    def _toggle_favorito(self):
        key = getattr(self, "_modo_seleccionado_key", None)
        if not key or key not in self._modos_data:
            return
        nuevo_valor = not self._modos_data[key].get("favorito", False)
        self._modos_data[key]["favorito"] = nuevo_valor
        self._var_favorito.set(nuevo_valor)
        self._btn_favorito.configure(text="★" if nuevo_valor else "☆")
        idx = self._modos_keys.index(key)
        self._modos_listbox.delete(idx)
        self._modos_listbox.insert(idx, self._nombre_lista(key))
        self._modos_listbox.selection_set(idx)
        self._guardar_modos_json()
        ai_processor.MODOS[key]["favorito"] = nuevo_valor
        self._notify_modos_change()

    def _toggle_candado(self):
        k = getattr(self, "_modo_seleccionado_key", None)
        if not k or k not in self._modos_data:
            return
        actual = self._modos_data[k].get("protegido", False)
        self._modos_data[k]["protegido"] = not actual
        self._guardar_modos_json()
        self._refresh_lock_state(k)
        idx = self._modos_keys.index(k)
        self._modos_listbox.delete(idx)
        self._modos_listbox.insert(idx, self._nombre_lista(k))
        self._modos_listbox.selection_set(idx)

    def _refresh_lock_state(self, k):
        protegido = self._modos_data[k].get("protegido", False)
        self._btn_candado.config(text="🔒" if protegido else "🔓")
        state = "disabled" if protegido else "normal"
        # Text widgets — editor modular y libre
        for w in (self._txt_base, self._txt_prompt, self._txt_prompt_libre):
            try:
                w.config(state=state)
            except Exception:
                pass
        # Botón guardar cambios
        try:
            if hasattr(self, "_btn_guardar_modo"):
                self._btn_guardar_modo.config(state=state)
        except Exception:
            pass
        # Botones del editor de ejemplos
        try:
            self._btn_nuevo_ej.config(state=state)
        except Exception:
            pass
        # Entry de nombre y descripción
        self._entry_modo_nombre.config(state=state)
        self._entry_modo_desc.config(state=state)
        # Spinboxes de parámetros avanzados
        for w in (self._spinbox_temp_es, self._spinbox_top_p):
            w.config(state=state)
        # Comboboxes de parámetros avanzados
        for w in (self._cmb_top_k,):
            w.config(state="disabled" if protegido else "readonly")
        # Botón eliminar: solo forzar disabled si protegido;
        # si no protegido, respetar lógica de sistema (ya establecida antes de llamar aquí)
        if protegido:
            self._btn_eliminar.config(state="disabled")
        # Botón restaurar: solo forzar disabled si protegido;
        # si no protegido, respetar el estado que ya tenía (calculado en _on_modo_select)
        if protegido:
            try:
                self._btn_restaurar.config(state="disabled")
            except AttributeError:
                pass

    def _nuevo_modo(self):
        import logging

        log = logging.getLogger(__name__)
        nombre = simpledialog.askstring(
            "Nuevo modo", "Nombre del modo:", parent=self.win
        )
        if not nombre:
            return
        key = nombre.lower().replace(" ", "_")
        base, i = key, 1
        while key in self._modos_data:
            key = f"{base}_{i}"
            i += 1
        self._modos_data[key] = {
            "nombre": nombre,
            "prompt": "",
            "prompt_es": "",
            "prompt_en": "",
            "temperatura": 0.1,
            "temperatura_es": 0.1,
            "temperatura_en": 0.1,
            "top_p": 0.9,
            "top_k": 40,
            "sistema": False,
        }
        self._modos_keys.append(key)
        self._modos_listbox.insert(tk.END, self._nombre_lista(key))
        self._modos_listbox.selection_clear(0, tk.END)
        self._modos_listbox.selection_set(tk.END)
        self._on_modo_select()
        self._guardar_modos_json()
        ai_processor.MODOS[key] = self._modos_data[key]
        log.info(
            f"Nuevo modo '{key}' creado, guardado en modos.json y añadido a ai_processor.MODOS"
        )
        self._notify_modos_change()

    def _duplicar_modo(self):
        sel = self._modos_listbox.curselection()
        if not sel:
            return
        key = self._modos_keys[sel[0]]
        import copy

        datos = copy.deepcopy(self._modos_data[key])
        datos["nombre"] += " (copia)"
        datos["sistema"] = False
        nuevo_key = key + "_copia"
        base, i = nuevo_key, 1
        while nuevo_key in self._modos_data:
            nuevo_key = f"{base}_{i}"
            i += 1
        self._modos_data[nuevo_key] = datos
        self._modos_keys.append(nuevo_key)
        self._modos_listbox.insert(tk.END, self._nombre_lista(nuevo_key))
        self._modos_listbox.selection_clear(0, tk.END)
        self._modos_listbox.selection_set(tk.END)
        self._on_modo_select()

    def _eliminar_modo(self):
        sel = self._modos_listbox.curselection()
        if not sel:
            return
        key = self._modos_keys[sel[0]]
        if self._modos_data[key].get("sistema", False):
            return
        del self._modos_data[key]
        self._modos_keys.pop(sel[0])
        self._modos_listbox.delete(sel[0])
        if self._modos_keys:
            new_sel = min(sel[0], len(self._modos_keys) - 1)
            self._modos_listbox.selection_set(new_sel)
            self._on_modo_select()
        self._guardar_modos_json()
        ai_processor.MODOS.pop(key, None)
        self._notify_modos_change()

    def _tab_modos(self, frame, _):
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=0)  # panel izquierdo ancho fijo
        frame.columnconfigure(1, weight=1)  # panel derecho se expande

        # ── Panel izquierdo ──
        left = ttk.Frame(frame)
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self._modos_listbox = tk.Listbox(
            left, width=40, activestyle="dotbox", selectmode=tk.SINGLE
        )
        self._modos_listbox.grid(row=0, column=0, sticky="nsew")
        self._modos_listbox.bind("<<ListboxSelect>>", self._on_modo_select)

        sb = ttk.Scrollbar(left, command=self._modos_listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._modos_listbox.config(yscrollcommand=sb.set)

        btn_frame = ttk.Frame(left)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(btn_frame, text="Nuevo", command=self._nuevo_modo).pack(
            fill=tk.X, pady=1
        )
        ttk.Button(btn_frame, text="Duplicar", command=self._duplicar_modo).pack(
            fill=tk.X, pady=1
        )
        self._btn_eliminar = ttk.Button(
            btn_frame, text="Eliminar", command=self._eliminar_modo
        )
        self._btn_eliminar.pack(fill=tk.X, pady=1)

        # ── Panel derecho ──
        right = ttk.LabelFrame(frame, text="Detalles del modo")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(0, weight=0)  # nombre/descripción
        right.rowconfigure(1, weight=0, minsize=0)
        right.rowconfigure(2, weight=0, minsize=0)
        right.rowconfigure(3, weight=1)  # editor modular — se expande
        right.rowconfigure(4, weight=0)  # barra inferior — fija abajo
        right.rowconfigure(5, weight=0)  # botones modo

        PAD = {"padx": 8, "pady": 4, "sticky": "w"}

        # ── Fila superior compacta ──
        f_top = ttk.Frame(right)
        f_top.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(6, 2))
        f_top.columnconfigure(2, weight=1)

        self._var_favorito = tk.BooleanVar()
        self._var_protegido = tk.BooleanVar()

        self._btn_favorito = ttk.Button(
            f_top, text="☆", width=3, command=self._toggle_favorito
        )
        self._btn_favorito.pack(side=tk.LEFT, padx=(0, 2))

        self._btn_candado = ttk.Button(
            f_top, text="🔓", width=3, command=self._toggle_candado
        )
        self._btn_candado.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(f_top, text="Nombre:", font=("Segoe UI Variable", 9)).pack(
            side=tk.LEFT
        )

        self._var_modo_nombre = tk.StringVar()
        self._entry_modo_nombre = ttk.Entry(
            f_top, textvariable=self._var_modo_nombre, width=18
        )
        self._entry_modo_nombre.pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(f_top, text="Descripción:", font=("Segoe UI Variable", 9)).pack(
            side=tk.LEFT
        )

        self._var_modo_desc = tk.StringVar()
        self._entry_modo_desc = ttk.Entry(f_top, textvariable=self._var_modo_desc)
        self._entry_modo_desc.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # ── Editor de prompt modular ──
        editor_frame = ttk.Frame(right)
        editor_frame.grid(
            row=3, column=0, columnspan=2, sticky="nsew", padx=8, pady=(4, 0)
        )
        editor_frame.columnconfigure(0, weight=1)

        tema = self.config.get("tema", "light")
        bg_panel = "#1A1A1A" if tema == "dark" else "white"
        fg_label = "#F0F0F0" if tema == "dark" else "#444444"

        # ── Toggle modo editor ──
        f_toggle = tk.Frame(editor_frame, bg=bg_panel)
        f_toggle.grid(row=0, column=0, sticky="ew", pady=(4, 6))

        self._modo_editor_var = tk.StringVar(value="estructurado")

        def _cambiar_modo_editor(modo):
            self._modo_editor_var.set(modo)
            tema_curr = self.config.get("tema", "light")
            bg_inactive = "#333333" if tema_curr == "dark" else "#e0e0e0"
            fg_inactive = "#F0F0F0" if tema_curr == "dark" else "#333333"

            if modo == "estructurado":
                self._frame_editor_estructurado.grid()
                self._frame_editor_libre.grid_remove()
                if hasattr(self, "_btn_editor_estructurado"):
                    self._btn_editor_estructurado.config(
                        bg="#7C5EF7", fg="white", relief="flat"
                    )
                if hasattr(self, "_btn_editor_libre"):
                    self._btn_editor_libre.config(
                        bg=bg_inactive, fg=fg_inactive, relief="flat"
                    )
            else:
                self._frame_editor_estructurado.grid_remove()
                self._frame_editor_libre.grid()
                if hasattr(self, "_btn_editor_libre"):
                    self._btn_editor_libre.config(
                        bg="#7C5EF7", fg="white", relief="flat"
                    )
                if hasattr(self, "_btn_editor_estructurado"):
                    self._btn_editor_estructurado.config(
                        bg=bg_inactive, fg=fg_inactive, relief="flat"
                    )
            # Guardar preferencia en el modo actual
            key = getattr(self, "_modo_seleccionado_key", None)
            if key and key in self._modos_data:
                self._modos_data[key]["modo_editor"] = modo

            if hasattr(self, "_actualizar_tokens_prompt_es"):
                self._actualizar_tokens_prompt_es()

            # Forzar aplicación del tema a los widgets de texto
            bg_txt = "#1A1A1A" if tema_curr == "dark" else "white"
            fg_txt = "#F0F0F0" if tema_curr == "dark" else "black"
            sel_bg = "#7C5EF7" if tema_curr == "dark" else "#0078D7"
            for txt in (self._txt_base, self._txt_prompt, self._txt_prompt_libre):
                try:
                    current_state = txt.cget("state")
                    txt.config(state="normal")
                    txt.configure(
                        bg=bg_txt,
                        fg=fg_txt,
                        insertbackground=fg_txt,
                        selectbackground=sel_bg,
                    )
                    txt.config(state=current_state)
                except Exception:
                    pass

        btn_plantilla = tk.Button(
            f_toggle,
            text="Plantilla",
            bg="#e0e0e0",
            relief="sunken",
            font=("Segoe UI Variable", 9),
            bd=1,
            padx=8,
            pady=2,
            cursor="hand2",
            command=lambda: _cambiar_modo_editor("estructurado"),
        )
        btn_plantilla.pack(side=tk.LEFT)

        btn_libre = tk.Button(
            f_toggle,
            text="Prompt libre",
            bg="white",
            relief="flat",
            font=("Segoe UI Variable", 9),
            bd=1,
            padx=8,
            pady=2,
            cursor="hand2",
            command=lambda: _cambiar_modo_editor("libre"),
        )
        btn_libre.pack(side=tk.LEFT, padx=(2, 0))

        self._btn_editor_estructurado = btn_plantilla
        self._btn_editor_libre = btn_libre
        self._cambiar_modo_editor = _cambiar_modo_editor

        # Frame estructurado (contenedor de BASE/PROMPT/EJEMPLOS)
        self._frame_editor_estructurado = ttk.Frame(editor_frame)
        self._frame_editor_estructurado.grid(row=1, column=0, sticky="nsew")
        self._frame_editor_estructurado.columnconfigure(0, weight=1)

        # Frame libre (prompt único editable)
        self._frame_editor_libre = ttk.Frame(editor_frame)
        self._frame_editor_libre.grid(row=1, column=0, sticky="nsew")
        self._frame_editor_libre.grid_remove()
        self._frame_editor_libre.columnconfigure(0, weight=1)

        ttk.Label(
            self._frame_editor_libre,
            text="PROMPT LIBRE:",
            foreground=fg_label,
            font=("Segoe UI Variable", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(4, 2))

        self._txt_prompt_libre = tk.Text(
            self._frame_editor_libre,
            wrap=tk.WORD,
            height=22,
            font=("Segoe UI Variable", 9),
            relief="solid",
            bd=1,
            highlightbackground="#4a4a6a",
            highlightthickness=1,
        )
        self._txt_prompt_libre.grid(row=1, column=0, sticky="nsew", pady=(2, 6))
        self._frame_editor_libre.rowconfigure(1, weight=1)

        # Bloque BASE
        ttk.Label(
            self._frame_editor_estructurado,
            text="LIMPIEZA BÁSICA:",
            foreground=fg_label,
            font=("Segoe UI Variable", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(10, 2))

        self._txt_base = tk.Text(
            self._frame_editor_estructurado,
            wrap=tk.WORD,
            height=8,
            font=("Segoe UI Variable", 9),
            relief="solid",
            bd=1,
            highlightbackground="#4a4a6a",
            highlightthickness=1,
        )
        self._txt_base.grid(row=1, column=0, sticky="ew", pady=(2, 6))

        # Bloque PROMPT
        ttk.Label(
            self._frame_editor_estructurado,
            text="INSTRUCCIONES DE EDICIÓN:",
            foreground=fg_label,
            font=("Segoe UI Variable", 9, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(10, 2))

        self._txt_prompt = tk.Text(
            self._frame_editor_estructurado,
            wrap=tk.WORD,
            height=10,
            font=("Segoe UI Variable", 9),
            relief="solid",
            bd=1,
            highlightbackground="#3a5a4a",
            highlightthickness=1,
        )
        self._txt_prompt.grid(row=3, column=0, sticky="ew", pady=(2, 6))

        # Bloque EJEMPLOS
        f_ej_header = tk.Frame(self._frame_editor_estructurado, bg=bg_panel)
        f_ej_header.grid(row=4, column=0, sticky="ew", pady=(10, 2))
        f_ej_header.columnconfigure(0, weight=1)

        ttk.Label(
            f_ej_header,
            text="CONTEXTO DE REFERENCIA:",
            foreground=fg_label,
            font=("Segoe UI Variable", 9, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Button(
            f_ej_header, text="+ nuevo ejemplo", command=self._abrir_popup_ejemplo
        ).pack(side=tk.RIGHT)

        # Frame contenedor de tarjetas de ejemplos
        self._frame_tarjetas = tk.Frame(self._frame_editor_estructurado, bg=bg_panel)
        self._frame_tarjetas.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        self._frame_tarjetas.columnconfigure(0, weight=1)

        # Referencia legacy para compatibilidad
        self._txt_ejemplos = tk.Text(self._frame_editor_estructurado, height=0)
        self._txt_ejemplos.grid_remove()

        def _actualizar_tokens(event=None):
            try:
                wrapper = self.config.get(
                    "prompt_wrapper", ai_processor._INSTRUCCION_MARCADORES_DEFAULT
                )
                if self._modo_editor_var.get() == "libre":
                    texto = self._txt_prompt_libre.get("1.0", tk.END).strip()
                else:
                    base = self._txt_base.get("1.0", tk.END).strip()
                    prompt = self._txt_prompt.get("1.0", tk.END).strip()
                    key = getattr(self, "_modo_seleccionado_key", None)
                    ejemplos_txt = ""
                    if key and key in self._modos_data:
                        for ej in self._modos_data[key].get("ejemplos", []):
                            ejemplos_txt += (
                                ej.get("entrada", "") + " " + ej.get("salida", "")
                            )
                    texto = base + prompt + ejemplos_txt
                # Añadimos el wrapper y los marcadores a la estimación
                texto_total = (
                    texto
                    + wrapper
                    + ai_processor._MARCADOR_INICIO
                    + ai_processor._MARCADOR_FIN
                )
                total = int(len(texto_total.split()) * 1.3)
                self._lbl_tokens.config(text=f"Tokens: ~{total}")
            except Exception:
                pass

        self._txt_base.bind("<KeyRelease>", _actualizar_tokens)
        self._txt_prompt.bind("<KeyRelease>", _actualizar_tokens)
        self._txt_prompt_libre.bind("<KeyRelease>", _actualizar_tokens)
        self._actualizar_tokens_prompt_es = _actualizar_tokens

        # Eliminar referencia antigua (compatibilidad)
        self._txt_prompt_en = tk.Text(self._frame_editor_estructurado)
        self._txt_prompt_en.pack_forget()

        # Sección avanzada (oculta por defecto)
        # ── Parámetros avanzados + botón en una sola fila ──
        f_bottom = ttk.Frame(right)
        f_bottom.grid(row=4, column=0, columnspan=2, sticky="sew", padx=8, pady=(0, 6))

        PAD2 = {"padx": 4, "pady": 2}

        ttk.Label(f_bottom, text="Temp:").grid(row=0, column=0, **PAD2)
        self._var_temp_es = tk.DoubleVar()
        self._spinbox_temp_es = ttk.Spinbox(
            f_bottom,
            textvariable=self._var_temp_es,
            from_=0.0,
            to=2.0,
            increment=0.05,
            width=5,
            format="%.2f",
        )
        self._spinbox_temp_es.grid(row=0, column=1, sticky="w", **PAD2)
        self._var_temp_en = tk.DoubleVar()
        self._crear_tooltip(
            self._spinbox_temp_es,
            "Controla la creatividad de la respuesta.\n"
            "Valores bajos → más precisa. Valores altos → más creativa.",
        )

        ttk.Label(f_bottom, text="Top P:").grid(row=0, column=2, **PAD2)
        self._var_top_p = tk.DoubleVar()
        self._spinbox_top_p = ttk.Spinbox(
            f_bottom,
            textvariable=self._var_top_p,
            from_=0.0,
            to=1.0,
            increment=0.05,
            width=5,
            format="%.2f",
        )
        self._spinbox_top_p.grid(row=0, column=3, sticky="w", **PAD2)

        ttk.Label(f_bottom, text="Top K:").grid(row=0, column=4, **PAD2)
        self._var_top_k = tk.IntVar()
        self._cmb_top_k = ttk.Combobox(
            f_bottom,
            textvariable=self._var_top_k,
            values=[0, 1, 5, 10, 20, 40, 100],
            width=5,
            state="readonly",
        )
        self._cmb_top_k.grid(row=0, column=5, sticky="w", **PAD2)

        self._lbl_tokens = ttk.Label(
            f_bottom,
            text="Tokens: ~0",
            foreground="#444444",
            font=("Segoe UI Variable", 9, "bold"),
        )
        self._lbl_tokens.grid(row=0, column=6, padx=(12, 4), sticky="e")
        f_bottom.columnconfigure(6, weight=1)
        _actualizar_tokens()

        ttk.Button(
            f_bottom,
            text="Guardar cambios",
            style="Accent.TButton",
            command=self._guardar_modo_actual,
        ).grid(row=0, column=8, padx=(8, 0))

        self._lbl_guardado = tk.Label(
            f_bottom, text="", fg="#007700", font=("Segoe UI Variable", 10)
        )
        self._lbl_guardado.grid(row=0, column=9, padx=(4, 0))

        # Compatibilidad — btn_restaurar oculto
        self._btn_restaurar = ttk.Button(
            f_bottom, text="", command=self._restaurar_modo_original, state="disabled"
        )

        # Variables legacy para evitar errores si se referencian
        self._var_auto_enter = tk.BooleanVar()
        self._var_auto_enter_delay = tk.IntVar()

        # ── Poblar listbox ──
        self._modos_data = {k: dict(v) for k, v in MODOS.items()}
        self._modos_data.update(self._cargar_modos_custom())
        self._modos_keys = list(self._modos_data.keys())
        for k in self._modos_keys:
            self._modos_listbox.insert(tk.END, self._nombre_lista(k))
        if self._modos_keys:
            self._modos_listbox.selection_set(0)
            self._on_modo_select()

        self.win.after(500, self._aplicar_tema_widgets)

    # ── PESTAÑA ATAJOS ────────────────────────────────────────────────────────

    def _capturar_atajo(self, var, btn):
        from pynput import keyboard as kb
        import threading

        btn.config(text="Esperando...", state="disabled")
        pressed = set()
        resultado = []

        MOD_NAMES = {
            kb.Key.ctrl: "ctrl",
            kb.Key.ctrl_l: "ctrl",
            kb.Key.ctrl_r: "ctrl",
            kb.Key.alt: "alt",
            kb.Key.alt_l: "alt",
            kb.Key.alt_r: "alt",
            kb.Key.shift: "shift",
            kb.Key.shift_l: "shift",
            kb.Key.shift_r: "shift",
            kb.Key.cmd: "cmd",
            kb.Key.cmd_l: "cmd",
            kb.Key.cmd_r: "cmd",
        }
        MODIFIERS = set(MOD_NAMES.keys())

        def on_press(key):
            if key in MODIFIERS:
                pressed.add(key)
                return
            mods = sorted({MOD_NAMES[m] for m in pressed if m in MOD_NAMES})
            parts = [f"<{m}>" for m in mods]
            if hasattr(key, "char") and key.char:
                parts.append(key.char)
            elif hasattr(key, "name"):
                parts.append(f"<{key.name}>")
            else:
                parts.append(str(key))
            resultado.append("+".join(parts))
            return False

        def on_release(key):
            pressed.discard(key)

        def listen():
            with kb.Listener(on_press=on_press, on_release=on_release) as lst:
                lst.join()
            if resultado:
                self.win.after(0, lambda: var.set(resultado[0]))
            self.win.after(0, lambda: btn.config(text="Capturar", state="normal"))

        threading.Thread(target=listen, daemon=True).start()

    def _tab_atajos(self, frame, _):
        frame.columnconfigure(1, weight=1)

        FILAS = [
            ("Grabación (teclado):", "trigger_tecla", "ctrl_r"),
            ("Corrección manual:", "atajo_correccion", "<ctrl>+<alt>+c"),
            ("Abrir configuración:", "atajo_config", "<ctrl>+<alt>+s"),
            ("Activar / Desactivar:", "atajo_toggle", "<ctrl>+<alt>+t"),
            ("Cambiar modo siguiente:", "atajo_modo_siguiente", "<ctrl>+<alt>+m"),
            ("Nota de voz:", "atajo_nota", "<ctrl>+<alt>+n"),
        ]

        self._atajo_vars = {}

        for row, (label, key, default) in enumerate(FILAS):
            ttk.Label(frame, text=label).grid(
                row=row, column=0, sticky="w", padx=12, pady=6
            )

            var = tk.StringVar(value=self.config.get(key, default))
            self._atajo_vars[key] = var

            ttk.Entry(frame, textvariable=var, state="readonly", width=22).grid(
                row=row, column=1, sticky="w", padx=(0, 4), pady=6
            )

            btn_cap = ttk.Button(
                frame, text="Capturar", width=9, style="Accent.TButton"
            )
            btn_cap.grid(row=row, column=2, padx=(0, 2), pady=6)
            btn_cap.config(command=lambda v=var, b=btn_cap: self._capturar_atajo(v, b))

            ttk.Button(
                frame, text="✕", width=3, command=lambda v=var, d=default: v.set("")
            ).grid(row=row, column=3, padx=(0, 8), pady=6)

    # ── PESTAÑA MOTORES ───────────────────────────────────────────────────────

    def _refrescar_estado_modelos_stt(self):
        HF_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")

        def _hf_ok(repo_id: str) -> bool:
            snaps = os.path.join(
                HF_CACHE, "models--" + repo_id.replace("/", "--"), "snapshots"
            )
            try:
                return any(True for _ in os.scandir(snaps))
            except OSError:
                return False

        # ── Radiobuttons de modelo Whisper ────────────────────────────────────
        if hasattr(self, "_stt_modelo_rbs"):
            for nombre, rb in self._stt_modelo_rbs.items():
                instalado = _hf_ok(_whisper_repo_id(nombre))
                try:
                    rb.config(state="normal" if instalado else "disabled")
                except tk.TclError:
                    pass

        # ── Radiobuttons de motor ────────────────────────────────────────────
        hay_whisper = any(
            _hf_ok(_whisper_repo_id(m))
            for m in (
                "tiny",
                "base",
                "small",
                "medium",
                "large-v2",
                "large-v3",
                "large-v3-turbo",
            )
        )
        hay_parakeet = os.path.exists(
            os.path.join(HF_CACHE, "models--istupakov--parakeet-tdt-0.6b-v3-onnx")
        )

        for rb_attr in ("_rb_whisper_gpu", "_rb_whisper_cpu"):
            rb = getattr(self, rb_attr, None)
            if rb:
                try:
                    rb.config(state="normal" if hay_whisper else "disabled")
                except tk.TclError:
                    pass

        rb_pk = getattr(self, "_rb_parakeet", None)
        if rb_pk:
            try:
                rb_pk.config(state="normal" if hay_parakeet else "disabled")
            except tk.TclError:
                pass

        # ── Radiobutton de motor Ollama ──────────────────────────────────────
        rb_ollama = getattr(self, "_rb_ollama", None)
        if rb_ollama:
            ollama_ok = self.config.get("ollama_disponible", False)
            texto = "Ollama (local)" if ollama_ok else "Instalar Ollama."
            try:
                rb_ollama.config(state="normal", text=texto)
            except tk.TclError:
                pass

    def _comprobar_stt(self):
        import threading

        motor = self._var_stt_motor.get()
        self._lbl_stt_status.config(text="Comprobando...", foreground="gray")

        def check():
            try:
                if motor in ("local_gpu", "local_cpu"):
                    import faster_whisper

                    ver = getattr(faster_whisper, "__version__", "?")
                    modelo = self.config.get("stt_modelo", "large-v3-turbo")
                    tipo = "GPU" if motor == "local_gpu" else "CPU"
                    msg = f"✓ Whisper {tipo} v{ver} — modelo: {modelo}"
                    color = "green"
                elif motor in ("parakeet", "parakeet_gpu"):
                    import onnx_asr

                    ver = getattr(onnx_asr, "__version__", "?")
                    tipo = "CPU" if motor == "parakeet" else "GPU"
                    msg = f"✓ Parakeet TDT v3 {tipo} — onnx_asr v{ver}"
                    color = "green"
                else:
                    msg = "✗ Motor no reconocido"
                    color = "red"
            except ImportError as e:
                msg = f"✗ No disponible: {str(e)[:50]}"
                color = "red"
            if self.config.get("languagetool_activo", False):
                try:
                    import language_tool_python

                    msg += " · LanguageTool ✓"
                except Exception:
                    msg += " · LanguageTool ✗"
            self.win.after(
                0, lambda: self._lbl_stt_status.config(text=msg, foreground=color)
            )

        threading.Thread(target=check, daemon=True).start()

    def _comprobar_parakeet_stt(self):
        def _check():
            try:
                __import__("onnx_asr")  # mismo import que usa speakme.py
                disponible = True
                detalle = "✓ Disponible"
            except ImportError:
                disponible = False
                detalle = "✗ No instalado"
            except Exception as e:
                disponible = False
                detalle = f"✗ Error: {type(e).__name__}"

            def _update():
                self._lbl_parakeet_estado.config(
                    text=detalle, foreground="green" if disponible else "red"
                )
                if disponible:
                    self._btn_parakeet_instalar.grid_remove()
                else:
                    self._btn_parakeet_instalar.grid()

            self.win.after(0, _update)

        import threading

        threading.Thread(target=_check, daemon=True).start()

    def _mostrar_gestor_modelos(
        self, bienvenida: bool = False, autoinstalar: str | None = None
    ):
        import threading, shutil

        WHISPER_MODELS = [
            ("tiny", "~75 MB"),
            ("base", "~140 MB"),
            ("small", "~460 MB"),
            ("medium", "~1.5 GB"),
            ("large-v2", "~3.1 GB"),
            ("large-v3", "~3.1 GB"),
            ("large-v3-turbo", "~1.6 GB"),
        ]
        HF_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
        PARAKEET_REPO = "istupakov/parakeet-tdt-0.6b-v3-onnx"

        def _hf_folder(repo_id: str) -> str:
            return os.path.join(HF_CACHE, "models--" + repo_id.replace("/", "--"))

        def _hf_installed(repo_id: str) -> bool:
            snaps = os.path.join(_hf_folder(repo_id), "snapshots")
            try:
                return any(True for _ in os.scandir(snaps))
            except OSError:
                return False

        _whisper_repo = _whisper_repo_id

        # ── Popup ────────────────────────────────────────────────────────────
        parent = self.win if hasattr(self, "win") and self.win.winfo_exists() else None
        popup = tk.Toplevel(parent)
        popup.title("Gestor de modelos STT")
        popup.resizable(False, False)
        popup.grab_set()
        sw, sh = popup.winfo_screenwidth(), popup.winfo_screenheight()
        w, h = 570, 510
        popup.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        if bienvenida:
            ttk.Label(
                popup,
                text="¡Bienvenido a SpeakMe!  Instala al menos un modelo para empezar.",
                foreground="#7C5EF7",
                font=("Segoe UI Variable", 10, "bold"),
            ).pack(pady=(14, 2), padx=16)

        ttk.Label(
            popup,
            text="Modelos Whisper (CPU/GPU)",
            font=("Segoe UI Variable", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 2))

        f_whisper = ttk.Frame(popup)
        f_whisper.pack(fill=tk.X, padx=14)

        # Progress bar (shared, hidden until needed)
        lbl_pb_text = ttk.Label(
            popup, text="", foreground="#7C5EF7", font=("Segoe UI Variable", 8)
        )
        pb = ttk.Progressbar(popup, mode="indeterminate", length=534)

        _rows: dict = {}
        _installing = [False]
        _cancelar = [False]
        _hilo_descarga = [None]

        def _refresh(name, is_parakeet=False):
            repo = PARAKEET_REPO if is_parakeet else _whisper_repo(name)
            ok = _hf_installed(repo)
            row = _rows[name]
            row["lbl_status"].config(
                text="✓ Instalado" if ok else "— No instalado",
                foreground="green" if ok else "gray",
            )
            row["btn_install"].config(
                state="disabled" if (ok or _installing[0]) else "normal"
            )
            row["btn_remove"].config(
                state="normal" if (ok and not _installing[0]) else "disabled"
            )

        def _refresh_all():
            for name, _ in WHISPER_MODELS:
                _refresh(name)
            _refresh("parakeet", is_parakeet=True)

        btn_cancelar = ttk.Button(popup, text="Cancelar descarga")

        def _cancelar_descarga():
            _cancelar[0] = True
            lbl_pb_text.config(text="Cancelando…")
            btn_cancelar.config(state="disabled")
            t = _hilo_descarga[0]
            if t and t.is_alive():
                try:
                    import ctypes

                    ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_ulong(t.ident),
                        ctypes.py_object(KeyboardInterrupt),
                    )
                except Exception:
                    pass

        btn_cancelar.config(command=_cancelar_descarga)

        def _start_pb(msg):
            _installing[0] = True
            _cancelar[0] = False
            lbl_pb_text.config(text=msg, foreground="#7C5EF7")
            lbl_pb_text.pack(anchor="w", padx=14, pady=(4, 0))
            pb.pack(padx=14, pady=(2, 2))
            pb.start(10)
            btn_cancelar.config(state="normal")
            btn_cancelar.pack(pady=(0, 4))
            _refresh_all()

        def _stop_pb():
            _installing[0] = False
            _cancelar[0] = False
            pb.stop()
            pb.pack_forget()
            btn_cancelar.pack_forget()
            lbl_pb_text.config(foreground="#7C5EF7")
            lbl_pb_text.pack_forget()
            _refresh_all()
            try:
                self._refrescar_estado_modelos_stt()
            except Exception:
                pass

        import logging as _logging

        _log = _logging.getLogger(__name__)

        def _show_error_pb(msg):
            _installing[0] = False
            pb.stop()
            pb.pack_forget()
            lbl_pb_text.config(text=msg, foreground="red")
            lbl_pb_text.pack(anchor="w", padx=14, pady=(4, 0))
            _refresh_all()

        def _install_whisper(name):
            if _installing[0]:
                return

            def _do():
                popup.after(0, lambda: _start_pb(f"Descargando {name}…"))
                try:
                    from faster_whisper import WhisperModel

                    WhisperModel(name, device="cpu", compute_type="int8")
                    if _cancelar[0]:
                        shutil.rmtree(
                            _hf_folder(_whisper_repo(name)), ignore_errors=True
                        )
                    popup.after(0, _stop_pb)
                except (Exception, KeyboardInterrupt) as e:
                    if _cancelar[0]:
                        shutil.rmtree(
                            _hf_folder(_whisper_repo(name)), ignore_errors=True
                        )
                        popup.after(0, _stop_pb)
                    else:
                        err = str(e)[:70]
                        popup.after(0, lambda m=err: _show_error_pb(f"❌ Error: {m}"))
                        popup.after(3000, _stop_pb)

            t = threading.Thread(target=_do, daemon=True)
            _hilo_descarga[0] = t
            t.start()

        def _remove_whisper(name):
            ruta = _hf_folder(_whisper_repo(name))
            _log.info(f"Desinstalando: {ruta}")
            shutil.rmtree(ruta, ignore_errors=True)
            _refresh(name)
            try:
                self._refrescar_estado_modelos_stt()
            except Exception:
                pass

        def _install_parakeet():
            if _installing[0]:
                return
            if not messagebox.askokcancel(
                "Instalar Parakeet TDT v3",
                "Se descargarán ~600MB. Esto puede tardar varios minutos.\n\n"
                "⚠ Es posible que SpeakMe! se cierre automáticamente al finalizar "
                "la descarga — esto es normal, solo tendrás que volver a abrirlo.\n\n"
                "¿Continuar con la descarga?",
                parent=popup,
            ):
                return

            def _do():
                popup.after(0, lambda: _start_pb("Descargando Parakeet TDT v3…"))
                try:
                    from onnx_asr import load_model

                    load_model("nemo-parakeet-tdt-0.6b-v3")
                    if _cancelar[0]:
                        shutil.rmtree(_hf_folder(PARAKEET_REPO), ignore_errors=True)
                    popup.after(0, _stop_pb)
                except (Exception, KeyboardInterrupt) as e:
                    if _cancelar[0]:
                        shutil.rmtree(_hf_folder(PARAKEET_REPO), ignore_errors=True)
                        popup.after(0, _stop_pb)
                    else:
                        err = str(e)[:70]
                        popup.after(0, lambda m=err: _show_error_pb(f"❌ Error: {m}"))
                        popup.after(3000, _stop_pb)

            t = threading.Thread(target=_do, daemon=True)
            _hilo_descarga[0] = t
            t.start()

        def _remove_parakeet():
            ruta = _hf_folder(PARAKEET_REPO)
            _log.info(f"Desinstalando: {ruta}")
            shutil.rmtree(ruta, ignore_errors=True)
            _refresh("parakeet", is_parakeet=True)
            try:
                self._refrescar_estado_modelos_stt()
            except Exception:
                pass

        # ── Whisper rows ─────────────────────────────────────────────────────
        for name, size in WHISPER_MODELS:
            row_f = ttk.Frame(f_whisper)
            row_f.pack(fill=tk.X, pady=1)
            etiqueta = f"* {name.capitalize()}" if name == "base" else name.capitalize()
            ttk.Label(row_f, text=etiqueta, width=16).pack(side=tk.LEFT)
            ttk.Label(
                row_f,
                text=size,
                foreground="gray",
                font=("Segoe UI Variable", 8),
                width=9,
            ).pack(side=tk.LEFT)
            lbl_st = ttk.Label(
                row_f, text="— No instalado", foreground="gray", width=14
            )
            lbl_st.pack(side=tk.LEFT)
            btn_in = ttk.Button(
                row_f,
                text="Instalar",
                width=9,
                command=lambda n=name: _install_whisper(n),
            )
            btn_in.pack(side=tk.LEFT, padx=(4, 2))
            btn_rm = ttk.Button(
                row_f,
                text="Desinstalar",
                width=11,
                command=lambda n=name: _remove_whisper(n),
            )
            btn_rm.pack(side=tk.LEFT)
            _rows[name] = {
                "lbl_status": lbl_st,
                "btn_install": btn_in,
                "btn_remove": btn_rm,
            }
            _refresh(name)

        # ── Parakeet row ─────────────────────────────────────────────────────
        ttk.Separator(popup, orient="horizontal").pack(fill=tk.X, padx=14, pady=(8, 4))
        ttk.Label(
            popup, text="Parakeet TDT v3 (CPU)", font=("Segoe UI Variable", 9, "bold")
        ).pack(anchor="w", padx=14, pady=(0, 2))

        row_pk = ttk.Frame(popup)
        row_pk.pack(fill=tk.X, padx=14, pady=1)
        ttk.Label(row_pk, text="Nemo-parakeet-tdt-0.6b-v3", width=25).pack(side=tk.LEFT)
        ttk.Label(
            row_pk,
            text="~600 MB",
            foreground="gray",
            font=("Segoe UI Variable", 8),
            width=9,
        ).pack(side=tk.LEFT)
        lbl_pk = ttk.Label(row_pk, text="— No instalado", foreground="gray", width=14)
        lbl_pk.pack(side=tk.LEFT)
        btn_pk_in = ttk.Button(
            row_pk, text="Instalar", width=9, command=_install_parakeet
        )
        btn_pk_in.pack(side=tk.LEFT, padx=(4, 2))
        btn_pk_rm = ttk.Button(
            row_pk, text="Desinstalar", width=11, command=_remove_parakeet
        )
        btn_pk_rm.pack(side=tk.LEFT)
        _rows["parakeet"] = {
            "lbl_status": lbl_pk,
            "btn_install": btn_pk_in,
            "btn_remove": btn_pk_rm,
        }
        _refresh("parakeet", is_parakeet=True)

        ttk.Label(
            popup,
            text="* Necesario para uso de motor Whisper",
            foreground="gray",
            font=("Segoe UI Variable", 8),
        ).pack(anchor="w", padx=14, pady=(4, 0))

        ttk.Button(
            popup,
            text="Aplicar y cerrar",
            style="Accent.TButton",
            command=lambda: (self._guardar_sin_cerrar(False), popup.destroy()),
        ).pack(pady=(8, 10))

        if autoinstalar:
            if autoinstalar == "parakeet":
                popup.after(200, _install_parakeet)
            else:
                popup.after(200, lambda m=autoinstalar: _install_whisper(m))

    def _instalar_parakeet_stt(self):
        import threading, subprocess, sys

        def _install():
            self.win.after(
                0,
                lambda: self._lbl_parakeet_estado.config(
                    text="Instalando...", foreground="gray"
                ),
            )
            self.win.after(
                0, lambda: self._btn_parakeet_instalar.configure(state="disabled")
            )
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "onnx-asr"],
                    capture_output=True,
                    check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self.win.after(
                    0,
                    lambda: self._lbl_parakeet_estado.config(
                        text="✓ Instalado — reinicia la app", foreground="green"
                    ),
                )
                self.win.after(0, lambda: self._btn_parakeet_instalar.grid_remove())
            except Exception:
                self.win.after(
                    0,
                    lambda: self._lbl_parakeet_estado.config(
                        text="✗ Error al instalar", foreground="red"
                    ),
                )
                self.win.after(
                    0, lambda: self._btn_parakeet_instalar.configure(state="normal")
                )

        threading.Thread(target=_install, daemon=True).start()

    def _popup_coste_stt(self):
        p = tk.Toplevel(self.win)
        p.title("Estimador de coste STT")
        p.attributes("-topmost", True)
        p.resizable(False, False)
        sw, sh = p.winfo_screenwidth(), p.winfo_screenheight()
        p.geometry(f"360x230+{(sw - 360) // 2}+{(sh - 230) // 2}")

        ttk.Label(
            p,
            text="OpenAI Whisper API: $0.006 / minuto",
            font=("Segoe UI Variable", 11, "bold"),
        ).pack(pady=(14, 4))
        ttk.Label(p, text="Minutos de uso por día:").pack()

        var_min = tk.IntVar(value=10)
        var_coste = tk.StringVar(value="")

        def actualizar(val):
            coste = int(float(val)) * 30 * 0.006
            var_coste.set(f"Coste mensual estimado: ${coste:.2f}")

        ttk.Scale(
            p,
            from_=1,
            to=120,
            variable=var_min,
            command=actualizar,
            orient=tk.HORIZONTAL,
            length=300,
        ).pack(pady=4)
        ttk.Label(p, textvariable=var_coste).pack()
        actualizar(10)

        ttk.Separator(p, orient="horizontal").pack(fill=tk.X, padx=16, pady=8)
        ttk.Label(
            p,
            text="⚠  El audio se envía a servidores de OpenAI.",
            foreground="#cc8800",
            wraplength=320,
        ).pack(padx=16)
        ttk.Label(
            p,
            text="Para máxima privacidad usa el motor local.",
            foreground="gray",
            wraplength=320,
        ).pack(padx=16, pady=(2, 12))

    def _popup_coste_ia(self):
        p = tk.Toplevel(self.win)
        p.title("Motores de IA en la nube")
        p.attributes("-topmost", True)
        p.resizable(False, False)
        sw, sh = p.winfo_screenwidth(), p.winfo_screenheight()
        p.geometry(f"440x540+{(sw - 440) // 2}+{(sh - 540) // 2}")

        motores = [
            (
                "Groq",
                "Groq es GRATUITO sin tarjeta de crédito.\n\n"
                "Tus datos NO se usan para entrenar modelos.\n"
                "Consulta tus límites actuales en console.groq.com\n\n"
                "Si superas el límite, SpeakMe cambia automáticamente a Ollama local.\n\n"
                "Pasos:\n1) Crea cuenta en console.groq.com\n"
                "2) Ve a API Keys\n3) Crea una nueva key\n4) Pégala aquí",
                "Abrir console.groq.com",
                "https://console.groq.com",
            ),
            (
                "Gemini",
                "Gemini es GRATUITO sin tarjeta de crédito.\n\n"
                "⚠️ Google puede usar tus datos en tier gratuito.\n"
                "Consulta tus límites actuales en aistudio.google.com\n\n"
                "Si superas el límite, SpeakMe cambia automáticamente a Ollama local.\n\n"
                "Pasos:\n1) Crea cuenta en aistudio.google.com\n"
                "2) Ve a Get API Key\n3) Crea una nueva key\n4) Pégala aquí",
                "Abrir aistudio.google.com",
                "https://aistudio.google.com",
            ),
            (
                "OpenAI",
                "OpenAI es de PAGO.\n\n"
                "Coste aproximado: ~1-2€/mes uso normal de dictado.\n"
                "Tus datos NO se usan para entrenar modelos por defecto.\n\n"
                "Pasos:\n1) Crea cuenta en platform.openai.com\n"
                "2) Ve a API Keys\n3) Añade créditos en Billing\n"
                "4) Crea una nueva key\n5) Pégala aquí",
                "Abrir platform.openai.com",
                "https://platform.openai.com",
            ),
        ]

        for nombre, texto, btn_texto, url in motores:
            lf = ttk.LabelFrame(p, text=nombre)
            lf.pack(fill=tk.X, padx=12, pady=6)
            ttk.Label(lf, text=texto, wraplength=390, justify="left").pack(
                anchor="w", padx=8, pady=(4, 2)
            )
            ttk.Button(
                lf, text=btn_texto, command=lambda u=url: webbrowser.open(u)
            ).pack(anchor="e", padx=8, pady=(0, 6))

    @staticmethod
    def _call_gemini_test(key, modelo):
        """Llamada síncrona a Gemini. Ejecutar siempre en hilo secundario."""
        import requests as req

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models"
            f"/{modelo}:generateContent?key={key}"
        )
        try:
            r = req.post(
                url, json={"contents": [{"parts": [{"text": "test"}]}]}, timeout=5
            )
            if r.status_code == 200:
                return True, f"✓ Gemini {modelo} OK"
            elif r.status_code == 404:
                return False, f"✗ 404 — modelo '{modelo}' no existe"
            elif r.status_code == 403:
                return False, "✗ 403 — clave inválida o sin permisos"
            elif r.status_code == 429:
                return False, "✗ 429 — límite de peticiones alcanzado"
            else:
                return False, f"✗ HTTP {r.status_code}"
        except Exception as e:
            return False, f"✗ {type(e).__name__}"

    def _probar_conexion_ollama(self):
        import threading, subprocess

        for lbl in [
            l
            for l in (
                getattr(self, "_lbl_test_ollama", None),
                getattr(self, "_lbl_test_ollama_panel", None),
            )
            if l
        ]:
            lbl.config(text="Probando...", foreground="gray")

        def test():
            try:
                result = subprocess.run(
                    ["ollama", "list"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                lineas = [l for l in result.stdout.strip().split("\n")[1:] if l.strip()]
                modelos = [l.split()[0] for l in lineas]
                if not modelos:
                    ok = False
                    msg = "⚠ Sin modelos instalados. Descarga uno primero."
                    self.win.after(0, self._ver_modelos_disponibles)
                else:
                    ok = True
                    msg = f"✓ Ollama OK — {len(modelos)} modelo(s) disponible(s)"
            except Exception:
                ok = False
                msg = "✗ Ollama no está ejecutándose. Inicia Ollama antes de continuar."
            self._motor_check_ok = ok
            color = "green" if ok else ("orange" if "⚠" in msg else "red")
            for lbl in [
                l
                for l in (
                    getattr(self, "_lbl_test_ollama", None),
                    getattr(self, "_lbl_test_ollama_panel", None),
                )
                if l
            ]:
                self.win.after(
                    0, lambda lb=lbl, c=color, m=msg: lb.config(text=m, foreground=c)
                )

        threading.Thread(target=test, daemon=True).start()

    def _probar_conexion(self, motor):
        import threading

        self._lbl_test_ia.config(text="Probando...", foreground="gray")

        def test():
            ok, msg = False, ""
            try:
                import requests as req

                if motor == "ollama":
                    r = req.get("http://localhost:11434/api/version", timeout=3)
                    ok = r.status_code == 200
                    msg = (
                        f"✓ Ollama {r.json().get('version', '')}"
                        if ok
                        else "✗ Sin respuesta"
                    )
                else:
                    key = self._ia_key_vars.get(motor, tk.StringVar()).get()
                    if not key:
                        msg = "✗ Falta API key"
                    elif motor == "gemini":
                        modelo = (
                            self._var_gemini_model.get()
                            if hasattr(self, "_var_gemini_model")
                            else self.config.get(
                                "gemini_model", "gemini-2.5-flash-lite"
                            )
                        )
                        ok, msg = self._call_gemini_test(key, modelo)
                    elif motor == "openai":
                        modelo = self._cb_ia_version.get() or self.config.get(
                            "openai_model", "gpt-4o-mini"
                        )
                        r = req.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": modelo,
                                "messages": [{"role": "user", "content": "test"}],
                                "max_tokens": 1,
                            },
                            timeout=10,
                        )
                        ok = r.status_code == 200
                        msg = f"✓ {modelo} OK" if ok else f"✗ Error {r.status_code}"
                    else:
                        url = "https://api.groq.com/openai/v1/models"
                        headers = {"Authorization": f"Bearer {key}"}
                        r = req.get(url, headers=headers, timeout=5)
                        ok = r.status_code == 200
                        msg = f"✓ Groq OK" if ok else f"✗ Error {r.status_code}"
            except Exception as e:
                msg = f"✗ {type(e).__name__}"
            color = "green" if ok else "red"
            self._motor_check_ok = ok
            self.win.after(
                0, lambda: self._lbl_test_ia.config(text=msg, foreground=color)
            )

        threading.Thread(target=test, daemon=True).start()

    def _tab_motores(self, frame, _):
        import logging

        log = logging.getLogger(__name__)
        frame.columnconfigure(0, weight=1)

        # ── STT ──────────────────────────────────────────────────────────────
        stt = ttk.LabelFrame(frame, text="Motor STT (voz a texto)")
        stt.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        self._var_stt_motor = tk.StringVar(
            value=self.config.get("stt_motor", "local_gpu")
        )
        var_stt = self._var_stt_motor
        var_stt_modelo = tk.StringVar(
            value=self.config.get("stt_modelo", "large-v3-turbo")
        )

        _HF_CACHE_STT = os.path.join(
            os.path.expanduser("~"), ".cache", "huggingface", "hub"
        )

        def _modelo_instalado(nombre):
            repo = _whisper_repo_id(nombre)
            folder = os.path.join(_HF_CACHE_STT, "models--" + repo.replace("/", "--"))
            snaps = os.path.join(folder, "snapshots")
            try:
                return any(True for _ in os.scandir(snaps))
            except OSError:
                return False

        # row 0 – Whisper GPU + CPU + Idioma
        row0 = ttk.Frame(stt)
        row0.grid(row=0, column=0, sticky="w", padx=8, pady=(6, 2))
        self._rb_whisper_gpu = ttk.Radiobutton(
            row0,
            text="Whisper GPU",
            variable=self._var_stt_motor,
            value="local_gpu",
            command=lambda: toggle_stt(var_stt.get()),
        )
        self._rb_whisper_gpu.pack(side=tk.LEFT)
        self._rb_whisper_cpu = ttk.Radiobutton(
            row0,
            text="Whisper CPU",
            variable=self._var_stt_motor,
            value="local_cpu",
            command=lambda: toggle_stt(var_stt.get()),
        )
        self._rb_whisper_cpu.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Label(row0, text="Idioma:").pack(side=tk.LEFT, padx=(16, 6))
        var_idioma = tk.StringVar(value=self.config.get("idioma", "auto"))
        cb_idioma = ttk.Combobox(
            row0,
            textvariable=var_idioma,
            values=["auto", "es", "en"],
            state="readonly",
            width=8,
        )
        cb_idioma.pack(side=tk.LEFT)
        self._vars["idioma"] = (var_idioma, None)

        # row 1 – Radiobuttons de modelo Whisper (uno por modelo, disabled si no instalado)
        WHISPER_NOMBRES = [
            "tiny",
            "base",
            "small",
            "medium",
            "large-v2",
            "large-v3",
            "large-v3-turbo",
        ]
        self._stt_modelo_rbs = {}
        row_modelos = ttk.Frame(stt)
        row_modelos.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 2))
        ttk.Label(row_modelos, text="Modelo:").pack(side=tk.LEFT, padx=(0, 6))
        for nombre in WHISPER_NOMBRES:
            instalado = _modelo_instalado(nombre)
            state = "normal" if instalado else "disabled"
            rb = ttk.Radiobutton(
                row_modelos,
                text=nombre,
                variable=var_stt_modelo,
                value=nombre,
                state=state,
            )
            rb.pack(side=tk.LEFT, padx=(0, 6))
            if not instalado:
                self._crear_tooltip(
                    rb, "Modelo no instalado. Ve a Gestionar modelos para instalarlo."
                )
            self._stt_modelo_rbs[nombre] = rb

        # row 2 – Parakeet CPU
        self._rb_parakeet = ttk.Radiobutton(
            stt,
            text="Parakeet TDT v3 CPU",
            variable=self._var_stt_motor,
            value="parakeet",
            command=lambda: toggle_stt(var_stt.get()),
        )
        self._rb_parakeet.grid(row=2, column=0, sticky="w", padx=8, pady=2)

        # row 3 – Parakeet GPU (deshabilitado)
        ttk.Radiobutton(
            stt,
            text="Parakeet TDT v3 GPU  (próximamente)",
            variable=self._var_stt_motor,
            value="parakeet_gpu",
            state="disabled",
        ).grid(row=3, column=0, sticky="w", padx=8, pady=2)

        # row 4 – Gestionar modelos
        row_check = ttk.Frame(stt)
        row_check.grid(row=4, column=0, sticky="w", padx=8, pady=(2, 6))
        ttk.Button(
            row_check, text="📖 Guía de motores", command=self._abrir_guia_motores
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            row_check,
            text="Gestionar modelos",
            style="Accent.TButton",
            command=self._mostrar_gestor_modelos,
        ).pack(side=tk.LEFT)
        self._lbl_stt_status = ttk.Label(row_check, text="", foreground="gray")
        self._lbl_stt_status.pack(side=tk.LEFT, padx=(8, 0))

        def toggle_stt(motor):
            is_whisper = motor in ("local_gpu", "local_cpu")
            if is_whisper:
                row_modelos.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 2))
            else:
                row_modelos.grid_remove()

        toggle_stt(var_stt.get())

        var_lt = tk.BooleanVar(value=self.config.get("languagetool_activo", False))
        ttk.Checkbutton(
            frame, text="Corrección gramatical (LanguageTool)", variable=var_lt
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(2, 6))
        self._vars["languagetool_activo"] = (var_lt, None)

        # ── IA ───────────────────────────────────────────────────────────────
        ia_header = ttk.Frame(frame)
        ia_header.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 0))
        self._var_ia_activo = tk.BooleanVar(value=self.config.get("ia_activo", True))
        ttk.Checkbutton(
            ia_header,
            text="Procesamiento con IA",
            variable=self._var_ia_activo,
            command=lambda: _toggle_ia(),
        ).pack(side=tk.LEFT)
        var_fallback_activo = tk.BooleanVar(
            value=self.config.get("fallback_activo", True)
        )

        def _toggle_fallback_activo():
            activo = var_fallback_activo.get()
            motor_activo = var_ia.get()
            for motor, cb in _fallback_cbs.items():
                if not activo:
                    cb.configure(state="disabled")
                elif motor == motor_activo:
                    cb.configure(state="disabled")
                else:
                    cb.configure(state="normal")

        self._vars["fallback_activo"] = (var_fallback_activo, None)

        ia = ttk.LabelFrame(frame, text="")
        ia.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 0))
        ia.columnconfigure(3, weight=1)

        def _toggle_ia():
            activo = self._var_ia_activo.get()
            self.config["ia_activo"] = activo
            if activo:
                ia.grid()
                self._frame_avanzado_motores.grid()
                if hasattr(self, "_fb_frame"):
                    self._fb_frame.grid()
            else:
                ia.grid_remove()
                self._frame_avanzado_motores.grid_remove()
                if hasattr(self, "_fb_frame"):
                    self._fb_frame.grid_remove()

        var_ia = tk.StringVar(value=self.config.get("ia_motor", "ollama"))
        self._var_motor = var_ia

        self._ia_key_vars = {
            "groq": tk.StringVar(value=self.config.get("groq_key", "")),
            "gemini": tk.StringVar(value=self.config.get("gemini_key", "")),
            "openai": tk.StringVar(value=self.config.get("openai_key", "")),
        }

        # Panel derecho informativo — cambia según motor
        self._frame_ia_info = ttk.LabelFrame(ia, text="Configuración del motor")
        self._frame_ia_info.grid(
            row=0, column=3, rowspan=9, sticky="nsew", padx=(8, 8), pady=8
        )
        self._frame_ia_info.columnconfigure(0, weight=1)
        self._frame_ia_info.columnconfigure(1, weight=1)
        self._frame_ia_info.rowconfigure(2, minsize=0)
        self._frame_ia_info.rowconfigure(3, minsize=32)

        _IA_PANEL = {
            "ollama": {
                "nombre": "Ollama",
                "modelos": [],
                "config_key": "ia_modelo",
                "instrucciones": "No requiere KEY — motor local.\n1. Instala Ollama desde ollama.ai\n2. Descarga un modelo\n3. Prueba la conexión",
                "enlace_txt": "Abrir ollama.ai",
                "enlace_url": "https://ollama.ai",
                "key": False,
                "rpm_default": 0,
                "rpd_default": 0,
            },
            "groq": {
                "nombre": "Groq",
                "modelos": [
                    "llama-3.1-8b-instant",
                    "llama-3.3-70b-versatile",
                    "mixtral-8x7b-32768",
                    "gemma2-9b-it",
                ],
                "config_key": "groq_model",
                "instrucciones": "1. Crea cuenta en console.groq.com\n2. Genera nueva Key\n3. Pega la Key aquí\n4. Prueba conexión",
                "enlace_txt": "Acceso a Groq.com",
                "enlace_url": "https://console.groq.com",
                "key": True,
                "rpm_default": 28,
                "rpd_default": 14400,
                "tier_url_gratuito": "https://console.groq.com/docs/rate-limits",
                "tier_url_pago": "https://console.groq.com/docs/models",
            },
            "gemini": {
                "nombre": "Gemini",
                "modelos": [
                    "gemini-2.5-flash-lite",
                    "gemini-2.0-flash",
                    "gemini-1.5-flash",
                    "gemini-1.5-pro",
                ],
                "config_key": "gemini_model",
                "instrucciones": "1. Crea cuenta en aistudio.google.com\n2. Genera nueva Key\n3. Pega la Key aquí\n4. Prueba conexión",
                "enlace_txt": "Acceso a Google AI Studio",
                "enlace_url": "https://aistudio.google.com",
                "key": True,
                "rpm_default": 13,
                "rpd_default": 1500,
                "tier_url_gratuito": "https://ai.google.dev/gemini-api/docs/rate-limits",
                "tier_url_pago": "https://ai.google.dev/pricing",
            },
            "openai": {
                "nombre": "OpenAI",
                "modelos": [
                    "gpt-4.1-nano",
                    "gpt-4.1-mini",
                    "gpt-4.1",
                    "gpt-5.4-nano",
                    "gpt-5.4-mini",
                    "gpt-5.4",
                    "gpt-4o-mini",
                    "gpt-4o",
                ],
                "config_key": "openai_model",
                "instrucciones": "1. Crea cuenta en platform.openai.com\n2. Añade créditos en Billing\n3. Genera nueva Key\n4. Pega la Key aquí\n5. Prueba conexión",
                "enlace_txt": "Acceso a OpenAI.com",
                "enlace_url": "https://platform.openai.com",
                "key": True,
                "rpm_default": 500,
                "rpd_default": 10000,
                "tier_url_gratuito": "",
                "tier_url_pago": "https://openai.com/pricing",
            },
        }

        _TIER_DEFS = {
            "groq": {"entrada": 0.05, "salida": 0.08},
            "gemini": {"entrada": 0.10, "salida": 0.40},
            "openai": {"entrada": 0.15, "salida": 0.60},
        }
        _tier_vars = {}
        _precio_entrada_vars = {}
        _precio_salida_vars = {}
        _rpm_vars = {}
        _rpd_vars = {}
        _aviso_tpm_vars = {}
        _tpm_vars = {}
        _tpd_vars = {}
        _TPM_DEFAULTS = {"groq": 6000, "gemini": 1000, "openai": 40000}
        _TPD_DEFAULTS = {"groq": 500000, "gemini": 1500, "openai": 0}
        for m in ("groq", "gemini", "openai"):
            _tier_vars[m] = tk.StringVar(value=self.config.get(f"{m}_tier", "gratuito"))
            _precio_entrada_vars[m] = tk.StringVar(
                value=str(
                    self.config.get(f"{m}_precio_entrada", _TIER_DEFS[m]["entrada"])
                )
            )
            _precio_salida_vars[m] = tk.StringVar(
                value=str(
                    self.config.get(f"{m}_precio_salida", _TIER_DEFS[m]["salida"])
                )
            )
            _rpm_vars[m] = tk.StringVar(
                value=str(
                    self.config.get(f"{m}_rpm_limite", _IA_PANEL[m]["rpm_default"])
                )
            )
            _rpd_vars[m] = tk.StringVar(
                value=str(
                    self.config.get(f"{m}_rpd_limite", _IA_PANEL[m]["rpd_default"])
                )
            )
            _aviso_tpm_vars[m] = tk.BooleanVar(
                value=self.config.get(f"{m}_aviso_tpm_activo", m != "openai")
            )
            _tpm_vars[m] = tk.StringVar(
                value=str(self.config.get(f"{m}_tpm_limite", _TPM_DEFAULTS[m]))
            )
            _tpd_vars[m] = tk.StringVar(
                value=str(self.config.get(f"{m}_tpd_limite", _TPD_DEFAULTS[m]))
            )
            self._vars[f"{m}_tier"] = (_tier_vars[m], None)
            self._vars[f"{m}_precio_entrada"] = (_precio_entrada_vars[m], None)
            self._vars[f"{m}_precio_salida"] = (_precio_salida_vars[m], None)
            self._vars[f"{m}_rpm_limite"] = (_rpm_vars[m], None)
            self._vars[f"{m}_rpd_limite"] = (_rpd_vars[m], None)
            self._vars[f"{m}_aviso_tpm_activo"] = (_aviso_tpm_vars[m], None)
            self._vars[f"{m}_tpm_limite"] = (_tpm_vars[m], None)
            self._vars[f"{m}_tpd_limite"] = (_tpd_vars[m], None)
        self._tier_vars = _tier_vars

        # ── Fila 0: Modelo — versión — Activar ──────────────────────────────────
        f_modelo_row = ttk.Frame(self._frame_ia_info)
        f_modelo_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        ttk.Label(
            f_modelo_row, text="Modelo:", font=("Segoe UI Variable", 9, "bold")
        ).pack(side=tk.LEFT)
        self._lbl_ia_modelo = ttk.Label(
            f_modelo_row, text="", font=("Segoe UI Variable", 9, "bold")
        )
        self._lbl_ia_modelo.pack(side=tk.LEFT, padx=(6, 10))
        self._cb_ia_version = ttk.Combobox(f_modelo_row, width=22, state="readonly")
        self._cb_ia_version.pack(side=tk.LEFT, padx=(0, 6))

        def _activar_version():
            motor = var_ia.get()
            ck = _IA_PANEL.get(motor, {}).get("config_key", "")
            ver = self._cb_ia_version.get()
            if ck and ver:
                self.config[ck] = ver
            self._lbl_ia_activar.config(text="✓", foreground="green")
            self.win.after(1500, lambda: self._lbl_ia_activar.config(text=""))

        def _desinstalar_modelo_ollama():
            modelo = self._cb_ia_version.get()
            if not modelo:
                return
            if not messagebox.askyesno(
                "Desinstalar modelo",
                f"¿Eliminar el modelo «{modelo}»?\nEsta acción no se puede deshacer.",
                parent=self.win,
            ):
                return
            import subprocess as _sp, threading as _t

            self._lbl_ia_activar.config(text=f"Eliminando {modelo}…", foreground="blue")

            def _rm():
                try:
                    _sp.run(
                        ["ollama", "rm", modelo],
                        timeout=30,
                        creationflags=_sp.CREATE_NO_WINDOW,
                    )
                    self.win.after(
                        0,
                        lambda: self._lbl_ia_activar.config(
                            text=f"✓ {modelo} eliminado", foreground="green"
                        ),
                    )
                    self.win.after(0, self._refrescar_modelos_ollama)
                except Exception as e:
                    self.win.after(
                        0,
                        lambda e_val=e: self._lbl_ia_activar.config(
                            text=f"✗ Error: {e_val}", foreground="red"
                        ),
                    )
                self.win.after(4000, lambda: self._lbl_ia_activar.config(text=""))

            _t.Thread(target=_rm, daemon=True).start()

        _refrescar_fn_map = {
            "ollama": self._refrescar_modelos_ollama,
            "groq": self._refrescar_modelos_groq,
            "gemini": self._refrescar_modelos_gemini,
            "openai": self._refrescar_modelos_openai,
        }
        self._btn_ia_refrescar = ttk.Button(
            f_modelo_row,
            text="⟳",
            command=lambda: _refrescar_fn_map.get(var_ia.get(), lambda: None)(),
            width=3,
        )
        self._btn_ia_refrescar.pack(side=tk.LEFT, padx=(0, 4))
        self._btn_instalar_ollama = ttk.Button(
            f_modelo_row, text="Instalar", command=self._ver_modelos_disponibles
        )
        self._btn_instalar_ollama.pack(side=tk.LEFT, padx=(0, 4))
        self._btn_desinstalar_ollama = ttk.Button(
            f_modelo_row, text="Desinstalar", command=_desinstalar_modelo_ollama
        )
        self._btn_desinstalar_ollama.pack(side=tk.LEFT, padx=(0, 4))
        self._btn_activar_version = ttk.Button(
            f_modelo_row,
            text="Activar",
            style="Accent.TButton",
            command=_activar_version,
        )
        self._btn_activar_version.pack(side=tk.LEFT, padx=(0, 6))
        self._lbl_ia_activar = ttk.Label(
            f_modelo_row,
            text="",
            foreground="green",
            font=("Segoe UI Variable", 9, "bold"),
        )
        self._lbl_ia_activar.pack(side=tk.LEFT)

        # ── Sep ──────────────────────────────────────────────────────────────────
        ttk.Separator(self._frame_ia_info, orient="horizontal").grid(
            row=1, column=0, sticky="ew", padx=10, pady=4
        )

        # ── Fila 2: KEY / Ollama — contenedor de altura fija ─────────────────────
        _frame_row2 = ttk.Frame(self._frame_ia_info, height=36)
        _frame_row2.grid(row=2, column=0, sticky="ew", padx=10, pady=2)
        _frame_row2.pack_propagate(False)
        _frame_row2.grid_propagate(False)

        self._frame_key = ttk.Frame(_frame_row2)
        self._frame_key.pack(fill=tk.X)
        ttk.Label(
            self._frame_key, text="KEY:", font=("Segoe UI Variable", 9, "bold")
        ).pack(side=tk.LEFT)
        self._ia_key_entry = ttk.Entry(self._frame_key, width=22, show="*")
        self._ia_key_entry.pack(side=tk.LEFT, padx=(6, 6))
        self._btn_probar_ia = ttk.Button(
            self._frame_key,
            text="Comprobar KEY",
            style="Accent.TButton",
            command=lambda: self._probar_conexion(var_ia.get()),
        )
        self._btn_probar_ia.pack(side=tk.LEFT, padx=(0, 6))
        self._lbl_test_ia = ttk.Label(self._frame_key, text="", foreground="gray")
        self._lbl_test_ia.pack(side=tk.LEFT)

        self._frame_ollama_probar = ttk.Frame(_frame_row2)
        self._btn_probar_ollama_panel = ttk.Button(
            self._frame_ollama_probar,
            text="Probar conexión",
            style="Accent.TButton",
            command=self._probar_conexion_ollama,
        )
        self._btn_probar_ollama_panel.pack(side=tk.LEFT)
        self._lbl_test_ollama_panel = ttk.Label(
            self._frame_ollama_probar, text="", foreground="gray"
        )
        self._lbl_test_ollama_panel.pack(side=tk.LEFT, padx=(6, 0))

        # ── Fila 3: Tier ─────────────────────────────────────────────────────────
        # ── Fila 3: Tier en una línea (tier + enlace + aviso) ───────────────────
        self._frame_tier_section = ttk.Frame(self._frame_ia_info)
        self._frame_tier_section.grid(
            row=3, column=0, sticky="ew", padx=10, pady=(4, 4)
        )
        self._frame_tier_section.grid_remove()

        # ── Sep ──────────────────────────────────────────────────────────────────
        ttk.Separator(self._frame_ia_info, orient="horizontal").grid(
            row=4, column=0, sticky="ew", padx=10, pady=4
        )

        # ── Fila 7: Botones de enlace y ayuda ────────────────────────────────────
        f_enlaces = ttk.Frame(self._frame_ia_info)
        f_enlaces.grid(row=7, column=0, sticky="w", padx=10, pady=(0, 6))
        self._btn_ayuda_key = ttk.Button(
            f_enlaces,
            text="❓ Instrucciones para obtener KEY",
            command=lambda: self._mostrar_ayuda_key(
                self._var_motor.get() if hasattr(self, "_var_motor") else ""
            ),
        )
        self._btn_ayuda_key.pack(side=tk.LEFT, padx=(0, 8))
        self._btn_ia_enlace = ttk.Button(f_enlaces, text="")
        self._btn_ia_enlace.pack(side=tk.LEFT)

        # ── Sep ──────────────────────────────────────────────────────────────────
        ttk.Separator(self._frame_ia_info, orient="horizontal").grid(
            row=8, column=0, sticky="ew", padx=10, pady=4
        )

        # ── Fila 9: Control de consumo ────────────────────────────────────────────
        f_avanzado = ttk.LabelFrame(
            self._frame_ia_info, text="Control de consumo/límites"
        )
        f_avanzado.grid(row=9, column=0, sticky="ew", padx=10, pady=(0, 10))

        self._f_consumo_row_pago = ttk.Frame(f_avanzado)

        self._lbl_campo1 = ttk.Label(self._f_consumo_row_pago, text="$/1M entrada:")
        self._lbl_campo1.pack(side=tk.LEFT)
        self._entry_precio_entrada = ttk.Entry(self._f_consumo_row_pago, width=7)
        self._entry_precio_entrada.pack(side=tk.LEFT, padx=(4, 0))

        self._lbl_campo2 = ttk.Label(self._f_consumo_row_pago, text="$/1M salida:")
        self._lbl_campo2.pack(side=tk.LEFT, padx=(10, 4))
        self._entry_precio_salida = ttk.Entry(self._f_consumo_row_pago, width=7)
        self._entry_precio_salida.pack(side=tk.LEFT)

        self._lbl_campo3 = ttk.Label(self._f_consumo_row_pago, text="Coste sesión:")
        self._lbl_campo3.pack(side=tk.LEFT, padx=(12, 4))
        self._lbl_coste_sesion = ttk.Label(
            self._f_consumo_row_pago,
            text="$0.0000",
            font=("Segoe UI Variable", 9, "bold"),
        )
        self._lbl_coste_sesion.pack(side=tk.LEFT)
        ttk.Button(
            self._f_consumo_row_pago,
            text="Resetear",
            width=8,
            command=self._reset_coste_sesion,
        ).pack(side=tk.LEFT, padx=(8, 0))

        # ── Frame gratuito: aviso TPM/TPD (oculto hasta _toggle_tier) ────────────
        self._f_gratuito_row = ttk.Frame(f_avanzado)
        self._cb_aviso_tpm = ttk.Checkbutton(
            self._f_gratuito_row, text="Avisar cuando se supere el TPM"
        )
        self._cb_aviso_tpm.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(self._f_gratuito_row, text="TPM:").pack(side=tk.LEFT)
        self._ent_tpm = ttk.Entry(self._f_gratuito_row, width=7)
        self._ent_tpm.pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(self._f_gratuito_row, text="TPD:").pack(side=tk.LEFT)
        self._ent_tpd = ttk.Entry(self._f_gratuito_row, width=8)
        self._ent_tpd.pack(side=tk.LEFT, padx=(4, 0))
        self._lbl_palabras_minuto = ttk.Label(
            self._f_gratuito_row, text="≈ 0 palabras/min"
        )
        self._lbl_palabras_minuto.pack(side=tk.LEFT, padx=(12, 0))
        ttk.Button(
            self._f_gratuito_row, text="❓", width=3, command=self._mostrar_ayuda_tpm
        ).pack(side=tk.LEFT, padx=(8, 0))

        def _actualizar_palabras(m, *_):
            try:
                tpm = int(_tpm_vars[m].get())
                palabras = max(0, int(((tpm - 500) / 2) * 0.75))
            except (ValueError, tk.TclError):
                palabras = 0
            if self._var_motor.get() == m:
                try:
                    self._lbl_palabras_minuto.config(text=f"≈ {palabras} palabras/min")
                except Exception:
                    pass

        for m in ("groq", "gemini", "openai"):
            _tpm_vars[m].trace_add("write", lambda *_, _m=m: _actualizar_palabras(_m))

        # ── toggle_tier ──────────────────────────────────────────────────────────
        def _toggle_tier(motor):
            tier = _tier_vars[motor].get()
            info = _IA_PANEL.get(motor, {})
            if tier == "gratuito":
                url = info.get("tier_url_gratuito", info.get("enlace_url", ""))
                if hasattr(self, "_btn_tier_enlace"):
                    self._btn_tier_enlace.config(
                        text="Ver límites gratuitos",
                        command=lambda u=url: webbrowser.open(u) if u else None,
                    )
                if hasattr(self, "_lbl_tier_warning"):
                    self._lbl_tier_warning.pack_forget()
                # Ocultar frame pago, mostrar frame gratuito
                self._f_consumo_row_pago.pack_forget()
                self._f_gratuito_row.pack(anchor="w", padx=6, pady=(4, 6))
                # Rebind vars del motor actual
                self._cb_aviso_tpm.config(variable=_aviso_tpm_vars[motor])
                self._ent_tpm.config(textvariable=_tpm_vars[motor])
                self._ent_tpd.config(textvariable=_tpd_vars[motor])
                _actualizar_palabras(motor)
            else:
                url = info.get("tier_url_pago", info.get("enlace_url", ""))
                if hasattr(self, "_btn_tier_enlace"):
                    self._btn_tier_enlace.config(
                        text="Ver precios oficiales",
                        command=lambda u=url: webbrowser.open(u) if u else None,
                    )
                if hasattr(self, "_lbl_tier_warning"):
                    self._lbl_tier_warning.pack(side=tk.LEFT)
                self._f_gratuito_row.pack_forget()
                self._f_consumo_row_pago.pack(anchor="w", padx=6, pady=(4, 2))
                self._lbl_campo1.config(text="$/1M entrada:")
                self._lbl_campo2.config(text="$/1M salida:")
                self._lbl_campo3.config(text="Coste sesión:")
                self._entry_precio_entrada.config(
                    textvariable=_precio_entrada_vars[motor], state="normal"
                )
                self._entry_precio_salida.config(
                    textvariable=_precio_salida_vars[motor], state="normal"
                )
                coste = self.config.get(f"{motor}_coste_sesion", 0.0)
                self._lbl_coste_sesion.config(text=f"${coste:.4f}")

        # ── toggle_ia ────────────────────────────────────────────────────────────
        def toggle_ia(motor):
            info = _IA_PANEL.get(motor, {})
            self._lbl_ia_modelo.config(text=info.get("nombre", motor.upper()))
            url = info.get("enlace_url", "")
            self._btn_ia_enlace.config(
                text=info.get("enlace_txt", ""),
                command=lambda u=url: webbrowser.open(u),
            )
            if info.get("key", False):
                self._btn_ayuda_key.pack(side=tk.LEFT)
            else:
                self._btn_ayuda_key.pack_forget()

            modelos = info.get("modelos", [])
            # Ollama carga modelos en hilo — nunca deshabilitar por lista vacía
            estado = "readonly" if (modelos or motor == "ollama") else "disabled"
            self._cb_ia_version.config(values=modelos, state=estado)
            ck = info.get("config_key", "")
            self._cb_ia_version.set(self.config.get(ck, modelos[0] if modelos else ""))

            if hasattr(self, "_btn_ia_refrescar"):
                self._btn_ia_refrescar.configure(
                    state="normal" if motor in _refrescar_fn_map else "disabled"
                )

            if hasattr(self, "_btn_instalar_ollama"):
                if motor == "ollama":
                    self._btn_instalar_ollama.pack(
                        side=tk.LEFT, padx=(0, 4), before=self._btn_activar_version
                    )
                    self._btn_desinstalar_ollama.pack(
                        side=tk.LEFT, padx=(0, 4), before=self._btn_activar_version
                    )
                else:
                    self._btn_instalar_ollama.pack_forget()
                    self._btn_desinstalar_ollama.pack_forget()

            if motor == "ollama":
                self._frame_key.pack_forget()
                self._frame_ollama_probar.pack(fill=tk.X)
                self._lbl_test_ollama_panel.config(text="", foreground="gray")
                self._frame_tier_section.grid()
                for w in self._frame_tier_section.winfo_children():
                    w.destroy()
                self._lbl_ia_modelo.config(text="Ollama — consultando...")
                if hasattr(self, "_entry_rpm_fallback"):
                    self._entry_rpm_fallback.config(state="disabled")
                    self._entry_rpd_fallback.config(state="disabled")

                def _fetch_ollama_info():
                    import subprocess as _sp

                    try:
                        result = _sp.run(
                            ["ollama", "list"],
                            capture_output=True,
                            text=True,
                            timeout=3,
                            creationflags=_sp.CREATE_NO_WINDOW,
                        )
                    except _sp.TimeoutExpired:
                        self.win.after(
                            0,
                            lambda: self._lbl_ia_modelo.config(
                                text="Ollama — no disponible"
                            ),
                        )
                        return
                    except Exception:
                        self.win.after(
                            0,
                            lambda: self._lbl_ia_modelo.config(
                                text="Ollama — no disponible"
                            ),
                        )
                        return
                    lineas = [
                        l for l in result.stdout.strip().split("\n")[1:] if l.strip()
                    ]
                    modelos = [l.split()[0] for l in lineas]

                    def _actualizar_ui():
                        try:
                            if not self.win.winfo_exists():
                                return
                            self._cb_ia_version["values"] = modelos
                            self._cb_ia_version.config(state="readonly")
                            if modelos:
                                actual = self.config.get("ia_modelo", "")
                                self._cb_ia_version.set(
                                    actual if actual in modelos else modelos[0]
                                )
                            self._lbl_ia_modelo.config(
                                text=f"Ollama — {len(modelos)} modelo(s) instalado(s)"
                            )
                        except Exception:
                            pass

                    self.win.after(0, _actualizar_ui)

                import threading as _t

                _t.Thread(target=_fetch_ollama_info, daemon=True).start()
            elif info.get("key"):
                self._frame_ollama_probar.pack_forget()
                self._frame_key.pack(fill=tk.X)
                self._ia_key_entry.config(
                    textvariable=self._ia_key_vars.get(motor, tk.StringVar())
                )
                self._lbl_test_ia.config(text="", foreground="gray")
                for w in self._frame_tier_section.winfo_children():
                    w.destroy()
                ttk.Label(
                    self._frame_tier_section,
                    text="Tier:",
                    font=("Segoe UI Variable", 9, "bold"),
                ).pack(side=tk.LEFT, padx=(0, 8))
                if motor != "openai":
                    ttk.Radiobutton(
                        self._frame_tier_section,
                        text="Gratuito",
                        variable=_tier_vars[motor],
                        value="gratuito",
                        command=lambda m=motor: _toggle_tier(m),
                    ).pack(side=tk.LEFT)
                else:
                    _tier_vars[motor].set("pago")
                ttk.Radiobutton(
                    self._frame_tier_section,
                    text="De pago",
                    variable=_tier_vars[motor],
                    value="pago",
                    command=lambda m=motor: _toggle_tier(m),
                ).pack(side=tk.LEFT, padx=(8, 0))
                self._btn_tier_enlace = ttk.Button(self._frame_tier_section, text="")
                self._btn_tier_enlace.pack(side=tk.LEFT, padx=(16, 6))
                self._lbl_tier_warning = ttk.Label(
                    self._frame_tier_section,
                    text="⚠ Se acumula en contador de sesión",
                    foreground="gray",
                    font=("Segoe UI Variable", 8),
                )
                self._lbl_tier_warning.pack(side=tk.LEFT)
                self._frame_tier_section.grid()
                _toggle_tier(motor)
                self._entry_precio_entrada.config(
                    textvariable=_precio_entrada_vars[motor]
                )
                self._entry_precio_salida.config(
                    textvariable=_precio_salida_vars[motor]
                )
                _toggle_tier(motor)
                if hasattr(self, "_entry_rpm_fallback"):
                    self._entry_rpm_fallback.config(
                        textvariable=_rpm_vars[motor], state="normal"
                    )
                    self._entry_rpd_fallback.config(
                        textvariable=_rpd_vars[motor], state="normal"
                    )

        # ── Headers: row 0 ───────────────────────────────────────────────────────
        _PAD_H = {"pady": (4, 0)}
        ttk.Label(
            ia, text="Motor", font=("Segoe UI Variable", 8), foreground="gray"
        ).grid(row=0, column=0, sticky="w", padx=8, **_PAD_H)
        ttk.Label(
            ia, text="Keep-Alive", font=("Segoe UI Variable", 8), foreground="gray"
        ).grid(row=0, column=1, padx=(4, 4), **_PAD_H)
        ttk.Label(
            ia, text="Fallback", font=("Segoe UI Variable", 8), foreground="gray"
        ).grid(row=0, column=2, padx=(4, 8), **_PAD_H)

        _fallback_cbs = {}
        _fallback_vars = {}
        _motores = [
            ("Ollama (local)", "ollama"),
            ("Groq", "groq"),
            ("Gemini", "gemini"),
            ("OpenAI", "openai"),
        ]

        _motor_previo = [self.config.get("ia_motor", "ollama")]

        def _actualizar_fallback_cbs(motor_activo):
            prev = _motor_previo[0]
            _motor_previo[0] = motor_activo
            if not var_fallback_activo.get():
                return
            if prev in _fallback_cbs:
                _fallback_cbs[prev].configure(state="normal")
            _fallback_cbs[motor_activo].configure(state="disabled")

        # ── Keep-Alive: col 1, row 1 (solo Ollama) ───────────────────────────────
        self._var_keep_alive = tk.BooleanVar(
            value=self.config.get("ollama_keep_alive", True)
        )
        self._vars["ollama_keep_alive"] = (self._var_keep_alive, None)
        cb_keep_alive = ttk.Checkbutton(ia, variable=self._var_keep_alive, padding=0)
        cb_keep_alive.grid(row=1, column=1, padx=(4, 4), pady=1)
        self._crear_tooltip(
            cb_keep_alive,
            "Mantiene el modelo Ollama cargado en memoria entre dictados.\n"
            "Actívalo para eliminar el tiempo de carga en cada dictado.\n"
            "Desactívalo si necesitas liberar RAM/VRAM entre usos.",
        )

        # ── Ollama: info popup si no está disponible ─────────────────────────────
        def _mostrar_info_ollama():
            popup = tk.Toplevel(self.win)
            popup.title("Instalar Ollama")
            popup.attributes("-topmost", True)
            popup.resizable(False, False)
            popup.grab_set()
            texto = (
                "Ollama es un motor de IA local que se ejecuta completamente en tu PC.\n"
                "No requiere conexión a internet ni API key una vez instalado.\n\n"
                "⚠ Requiere GPU NVIDIA para un rendimiento óptimo.\n\n"
                "Pasos para instalarlo:\n"
                "  1. Descarga Ollama para Windows desde ollama.ai\n"
                "  2. Instálalo como cualquier programa Windows\n"
                "  3. Abre SpeakMe! → Motores → Ollama\n"
                "  4. Descarga un modelo recomendado: Qwen3:8b (~5 GB)\n"
                "  5. Pulsa «Probar conexión» para verificar\n\n"
                "💡 Modelo recomendado: Qwen3:8b — buena relación\n"
                "   calidad/velocidad para dictado."
            )
            ttk.Label(
                popup,
                text=texto,
                justify="left",
                font=("Segoe UI Variable", 9),
                wraplength=380,
            ).pack(padx=20, pady=(16, 8))
            f_btns = ttk.Frame(popup)
            f_btns.pack(pady=(0, 12))

            def _reintentar():
                popup.destroy()
                import threading, subprocess

                def _check():
                    try:
                        subprocess.run(
                            ["ollama", "list"],
                            capture_output=True,
                            timeout=3,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                        ok = True
                    except Exception:
                        ok = False
                    self.config["ollama_disponible"] = ok

                    def _aplicar():
                        if hasattr(self, "_rb_ollama"):
                            self._rb_ollama.config(
                                text="Ollama (local)" if ok else "Instalar Ollama.",
                                command=_on_ollama_click,
                            )
                        if ok:
                            self._refrescar_modelos_ollama()
                            messagebox.showinfo(
                                "Ollama",
                                "✓ Ollama detectado correctamente.",
                                parent=self.win,
                            )
                        else:
                            messagebox.showwarning(
                                "Ollama",
                                "✗ No se ha detectado Ollama. Verifica que esté instalado e inténtalo de nuevo.",
                                parent=self.win,
                            )

                    self.win.after(0, _aplicar)

                threading.Thread(target=_check, daemon=True).start()

            ttk.Button(
                f_btns,
                text="Abrir ollama.ai",
                style="Accent.TButton",
                command=lambda: webbrowser.open("https://ollama.com/download"),
            ).pack(side=tk.LEFT, padx=(0, 8))
            ttk.Button(
                f_btns, text="Ya lo instalé, comprobar", command=_reintentar
            ).pack(side=tk.LEFT, padx=(0, 8))
            ttk.Button(f_btns, text="Cerrar", command=popup.destroy).pack(side=tk.LEFT)

        def _on_ollama_click():
            if not self.config.get("ollama_disponible", False):
                var_ia.set(self.config.get("ia_motor", "gemini"))
                _mostrar_info_ollama()
            else:
                toggle_ia("ollama")
                if hasattr(self, "_toggle_adv_motor_fn"):
                    self._toggle_adv_motor_fn("ollama")
                self._motor_check_ok = None
                _actualizar_fallback_cbs("ollama")

        # ── Motores: col 0 rows 1-4 / Fallback: col 2 rows 1-4 ──────────────────
        for i, (lbl, val) in enumerate(_motores):
            rb = ttk.Radiobutton(
                ia,
                text=lbl,
                variable=var_ia,
                value=val,
                command=lambda m=val: (
                    toggle_ia(m),
                    self._toggle_adv_motor_fn(m)
                    if hasattr(self, "_toggle_adv_motor_fn")
                    else None,
                    setattr(self, "_motor_check_ok", None),
                    _actualizar_fallback_cbs(m),
                ),
            )
            rb.grid(row=i + 1, column=0, sticky="w", padx=8, pady=1)
            if val == "ollama":
                ollama_ok = self.config.get("ollama_disponible", False)
                rb.config(
                    text="Ollama (local)" if ollama_ok else "Instalar Ollama.",
                    command=_on_ollama_click,
                )
                self._rb_ollama = rb
                self._crear_tooltip(
                    rb,
                    "Recomendado solo con GPU (NVIDIA).\n"
                    "Consumo VRAM según modelo (3B~2GB, 8B~5GB).\n"
                    "En CPU los resultados son lentos.",
                )
            cb_var = tk.BooleanVar(value=self.config.get(f"fallback_{val}", True))
            log.info(
                f"fallback init | {val} = {self.config.get(f'fallback_{val}', True)}"
            )
            cb = ttk.Checkbutton(ia, variable=cb_var, padding=0)
            cb.grid(row=i + 1, column=2, padx=(4, 8), pady=1)
            _fallback_cbs[val] = cb
            _fallback_vars[val] = cb_var
            self._vars[f"fallback_{val}"] = (cb_var, None)

        self._fallback_vars = _fallback_vars  # accesible desde _toggle_fallback_activo

        _actualizar_fallback_cbs(var_ia.get())
        _toggle_fallback_activo()  # aplicar estado inicial según config
        toggle_ia(var_ia.get())

        ttk.Label(
            ia,
            text="Si el motor falla, usa los marcados como fallback",
            foreground="gray",
            font=("Segoe UI Variable", 8),
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 4))

        # ── Opciones Fallback ─────────────────────────────────────────────────
        self._frame_avanzado_motores = ttk.LabelFrame(frame, text="Opciones Fallback")
        self._frame_avanzado_motores.grid(
            row=5, column=0, sticky="ew", padx=10, pady=(0, 10)
        )

        f_fallback_row = ttk.Frame(self._frame_avanzado_motores)
        f_fallback_row.pack(anchor="w", padx=10, pady=(6, 2))
        ttk.Checkbutton(
            f_fallback_row,
            text="Fallback automático",
            variable=var_fallback_activo,
            command=_toggle_fallback_activo,
        ).pack(side=tk.LEFT)
        lbl_rpm = ttk.Label(f_fallback_row, text="RPM:")
        lbl_rpm.pack(side=tk.LEFT, padx=(16, 4))
        self._crear_tooltip(
            lbl_rpm,
            "Peticiones por minuto — SpeakMe cambia de motor automáticamente al alcanzar este límite",
        )
        self._entry_rpm_fallback = ttk.Entry(f_fallback_row, width=6)
        self._entry_rpm_fallback.pack(side=tk.LEFT)
        lbl_rpd = ttk.Label(f_fallback_row, text="RPD:")
        lbl_rpd.pack(side=tk.LEFT, padx=(10, 4))
        self._crear_tooltip(
            lbl_rpd, "Peticiones por día — límite diario de llamadas a la API del motor"
        )
        self._entry_rpd_fallback = ttk.Entry(f_fallback_row, width=7)
        self._entry_rpd_fallback.pack(side=tk.LEFT)

        # toggle_ia ya se llamó antes de crear estos entries — conectar textvariable ahora
        _m = var_ia.get()
        if _m in _rpm_vars:
            self._entry_rpm_fallback.config(textvariable=_rpm_vars[_m], state="normal")
            self._entry_rpd_fallback.config(textvariable=_rpd_vars[_m], state="normal")
        else:
            self._entry_rpm_fallback.config(state="disabled")
            self._entry_rpd_fallback.config(state="disabled")

        ttk.Label(
            self._frame_avanzado_motores,
            text="Si el motor principal falla, se usarán automáticamente los marcados como Fallback.",
            foreground="gray",
            font=("Segoe UI Variable", 8),
        ).pack(anchor="w", padx=10, pady=(0, 8))

        self._toggle_ia_fn = toggle_ia

        if not self.config.get("ia_activo", True):
            ia.grid_remove()
            self._frame_avanzado_motores.grid_remove()

        self._motores_vars = {
            "stt_motor": var_stt,
            "stt_modelo": var_stt_modelo,
            "ia_motor": var_ia,
        }

        _STT_NOMBRES = {
            "local_gpu": "Whisper GPU",
            "local_cpu": "Whisper CPU",
            "parakeet": "Parakeet CPU",
            "parakeet_gpu": "Parakeet GPU",
        }

        def _actualizar_lbl_config(*_):
            stt = var_stt.get()
            modelo = var_stt_modelo.get()
            partes = [f"▶ Motor STT: {_STT_NOMBRES.get(stt, stt)}"]
            if stt in ("local_gpu", "local_cpu"):
                partes.append(modelo)
            ia_activo = (
                self._var_ia_activo.get() if hasattr(self, "_var_ia_activo") else True
            )
            if ia_activo:
                motor_ia = var_ia.get().capitalize()
                try:
                    modelo_ia = self._cb_ia_version.get()
                except Exception:
                    modelo_ia = ""
                partes.append(f"Motor IA:  {motor_ia}")
                if modelo_ia:
                    partes.append(modelo_ia)
            else:
                partes.append("Motor IA:  desactivado")
            try:
                self._lbl_config_activa.config(text="  |  ".join(partes))
            except tk.TclError:
                pass

        self._actualizar_lbl_config_fn = _actualizar_lbl_config
        var_stt.trace_add("write", _actualizar_lbl_config)
        var_stt_modelo.trace_add("write", _actualizar_lbl_config)
        var_ia.trace_add("write", _actualizar_lbl_config)
        self._var_ia_activo.trace_add("write", _actualizar_lbl_config)
        self._cb_ia_version.bind("<<ComboboxSelected>>", _actualizar_lbl_config)
        _actualizar_lbl_config()

    # ── PESTAÑA VOCABULARIO ───────────────────────────────────────────────────

    def _dialogo_sustitucion(self, origen="", destino=""):
        dlg = tk.Toplevel(self.win)
        dlg.title("Sustitución")
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        dlg.grab_set()
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"340x140+{(sw - 340) // 2}+{(sh - 140) // 2}")

        ttk.Label(dlg, text="Whisper escribe:").grid(
            row=0, column=0, padx=12, pady=8, sticky="w"
        )
        var_orig = tk.StringVar(value=origen)
        ttk.Entry(dlg, textvariable=var_orig, width=28).grid(
            row=0, column=1, padx=(0, 12), pady=8
        )

        ttk.Label(dlg, text="Debería ser:").grid(
            row=1, column=0, padx=12, pady=4, sticky="w"
        )
        var_dest = tk.StringVar(value=destino)
        ttk.Entry(dlg, textvariable=var_dest, width=28).grid(
            row=1, column=1, padx=(0, 12), pady=4
        )

        resultado = []

        def aceptar():
            o, d = var_orig.get().strip(), var_dest.get().strip()
            if o and d:
                resultado.append((o, d))
            dlg.destroy()

        bf = ttk.Frame(dlg)
        bf.grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(bf, text="Aceptar", command=aceptar, style="Accent.TButton").pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(bf, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
        dlg.wait_window()
        return resultado[0] if resultado else None

    def _refrescar_vocab_trees(self):
        vocabulary._cache = None
        vocab = vocabulary.cargar_vocabulario()
        for tree_attr, clave in (
            ("_vocab_tree", "sustituciones"),
            ("_vocab_tree_ia", "sustituciones_ia"),
        ):
            tree = getattr(self, tree_attr, None)
            if tree is None:
                continue
            tree.delete(*tree.get_children())
            for origen, destino in vocab.get(clave, {}).items():
                tree.insert("", tk.END, values=(origen, destino))

    _AYUDA_KEYS = {
        "groq": (
            "1. Accede a console.groq.com e inicia sesión.\n"
            "2. En el panel lateral izquierdo, entra en API Keys.\n"
            "3. Pulsa el botón Create API Key.\n"
            "4. Introduce un nombre y haz clic en Submit.\n"
            "5. Copia la clave generada y guárdala (no se volverá a mostrar).\n"
            "6. Pega la clave en SpeakMe! y pulsa Comprobar KEY."
        ),
        "gemini": (
            "1. Entra en aistudio.google.com con tu cuenta de Google.\n"
            "2. En el menú lateral, haz clic en Get API key.\n"
            "3. Pulsa Create API key.\n"
            "4. Selecciona Create API key in new project.\n"
            "5. Copia la clave obtenida.\n"
            "6. Pega la clave en SpeakMe! y pulsa Comprobar KEY."
        ),
        "OpenAi": (
            "1. Accede a platform.openai.com e inicia sesión.\n"
            "⚠ PASO CRÍTICO: Ve a Settings > Billing y añade fondos (mínimo 5$).\n"
            "   La API no funciona sin saldo previo.\n"
            "2. En el menú izquierdo, entra en API keys.\n"
            "3. Pulsa Create new secret key.\n"
            "4. Ponle un nombre y pulsa Create secret key.\n"
            "5. Copia la clave inmediatamente (no se puede consultar después).\n"
            "6. Pega la clave en SpeakMe! y pulsa Comprobar KEY.\n\n"
            "💡 Consulta precios en openai.com/pricing para configurar\n"
            "   el Control de consumo en SpeakMe!"
        ),
    }

    def _mostrar_ayuda_key(self, motor):
        texto = self._AYUDA_KEYS.get(motor, "")
        if not texto:
            return
        popup = tk.Toplevel(self.win)
        popup.title("Cómo obtener tu API Key")
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.configure(bg=self.win.cget("bg"))
        ttk.Label(
            popup,
            text=texto,
            justify="left",
            font=("Segoe UI Variable", 9),
            wraplength=380,
        ).pack(padx=20, pady=16)
        ttk.Label(
            popup,
            text="⚠ Las API keys son como contraseñas. No las compartas\nni las subas a repositorios públicos.",
            foreground="gray",
            font=("Segoe UI Variable", 8),
            justify="center",
        ).pack(padx=20, pady=(0, 8))
        ttk.Button(popup, text="Cerrar", command=popup.destroy).pack(pady=(0, 12))
        popup.update_idletasks()
        w, h = popup.winfo_reqwidth(), popup.winfo_reqheight()
        x = self.win.winfo_x() + (self.win.winfo_width() - w) // 2
        y = self.win.winfo_y() + (self.win.winfo_height() - h) // 2
        popup.geometry(f"+{x}+{y}")

    @staticmethod
    def _calcular_palabras_minuto(tpm: int) -> int:
        tokens_disponibles = (tpm - 500) / 2
        return max(0, int(tokens_disponibles * 0.75))

    def _mostrar_ayuda_tpm(self):
        try:
            tpm = int(self._ent_tpm.get())
        except Exception:
            tpm = 0
        palabras = self._calcular_palabras_minuto(tpm)
        texto = (
            f"TPM (Tokens Por Minuto) es el límite de tokens que\n"
            f"el proveedor permite procesar en una ventana de 60s.\n\n"
            f"Con tu TPM actual de {tpm:,}:\n"
            f"  · Tokens disponibles para texto: {max(0, tpm - 500):,}\n"
            f"  · Palabras/minuto estimadas: ≈ {palabras:,}\n\n"
            f"Fórmula: (TPM − 500 tokens_prompt) ÷ 2 × 0.75"
        )
        popup = tk.Toplevel(self.win)
        popup.title("¿Qué es el TPM?")
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.configure(bg=self.win.cget("bg"))
        ttk.Label(
            popup,
            text=texto,
            justify="left",
            font=("Segoe UI Variable", 9),
            wraplength=360,
        ).pack(padx=20, pady=16)
        ttk.Button(popup, text="Cerrar", command=popup.destroy).pack(pady=(0, 12))
        popup.update_idletasks()
        w, h = popup.winfo_reqwidth(), popup.winfo_reqheight()
        x = self.win.winfo_x() + (self.win.winfo_width() - w) // 2
        y = self.win.winfo_y() + (self.win.winfo_height() - h) // 2
        popup.geometry(f"+{x}+{y}")

    def _tab_vocabulario(self, frame, _):
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        vocab = vocabulary.cargar_vocabulario()

        nb_vocab = ttk.Notebook(frame, style="Vocab.TNotebook")
        nb_vocab.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        tab_stt = ttk.Frame(nb_vocab)
        tab_ia = ttk.Frame(nb_vocab)
        nb_vocab.add(tab_stt, text="STT (local)")
        nb_vocab.add(tab_ia, text="Resultado IA")

        def _build_sus_tab(
            parent, data, tree_attr, col_origen="Texto STT", col_destino="Corrección"
        ):
            parent.rowconfigure(0, weight=1)
            parent.rowconfigure(1, weight=0)
            parent.columnconfigure(0, weight=1)

            cols = ("origen", "destino")
            tree = ttk.Treeview(parent, columns=cols, show="headings", height=6)
            tree.heading("origen", text=col_origen)
            tree.heading("destino", text=col_destino)
            tree.column("origen", width=200)
            tree.column("destino", width=200)
            tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 4))

            sb = ttk.Scrollbar(parent, command=tree.yview)
            sb.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=(8, 4))
            tree.config(yscrollcommand=sb.set)

            for origen, destino in data.items():
                tree.insert("", tk.END, values=(origen, destino))

            panel = ttk.LabelFrame(parent, text="Edición")
            panel.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
            panel.columnconfigure(1, weight=1)
            panel.columnconfigure(3, weight=1)

            ttk.Label(panel, text="Palabra/s detectadas:").grid(
                row=0, column=0, padx=(8, 4), pady=(6, 0), sticky="w"
            )
            var_orig = tk.StringVar()
            ttk.Entry(panel, textvariable=var_orig).grid(
                row=0, column=1, sticky="ew", padx=(0, 12), pady=(6, 0)
            )

            ttk.Label(panel, text="Corrección:").grid(
                row=0, column=2, padx=(0, 4), pady=(6, 0), sticky="w"
            )
            var_dest = tk.StringVar()
            ttk.Entry(panel, textvariable=var_dest).grid(
                row=0, column=3, sticky="ew", padx=(0, 8), pady=(6, 0)
            )

            def guardar():
                o, d = var_orig.get().strip(), var_dest.get().strip()
                if not o or not d:
                    return
                sel = tree.selection()
                if sel:
                    tree.item(sel[0], values=(o, d))
                    tree.selection_remove(sel[0])
                else:
                    tree.insert("", tk.END, values=(o, d))
                var_orig.set("")
                var_dest.set("")

            ttk.Button(
                panel,
                text="Añadir / Actualizar",
                command=guardar,
                style="Accent.TButton",
            ).grid(row=0, column=4, padx=(4, 8), pady=(6, 0))

            ttk.Label(
                panel,
                text="Tip: separa variantes con  ;  en el campo Origen  (ej: hola; hi; hey)",
                foreground="gray",
                font=("Segoe UI Variable", 8),
            ).grid(row=1, column=0, columnspan=5, sticky="w", padx=8, pady=(2, 0))

            bf = ttk.Frame(panel)
            bf.grid(row=2, column=0, columnspan=5, sticky="w", padx=8, pady=(4, 6))

            def limpiar():
                var_orig.set("")
                var_dest.set("")
                tree.selection_remove(*tree.selection())

            def eliminar():
                for item in tree.selection():
                    tree.delete(item)
                var_orig.set("")
                var_dest.set("")

            def on_select(_e):
                sel = tree.selection()
                if sel:
                    vals = tree.item(sel[0], "values")
                    var_orig.set(vals[0])
                    var_dest.set(vals[1])

            tree.bind("<<TreeviewSelect>>", on_select)

            ttk.Button(bf, text="Eliminar seleccionado", command=eliminar).pack(
                side=tk.LEFT
            )

            setattr(self, tree_attr, tree)

        # ── Tab STT ──────────────────────────────────────────────────────────
        _build_sus_tab(
            tab_stt,
            vocab.get("sustituciones", {}),
            "_vocab_tree",
            col_origen="Palabra/s detectadas",
            col_destino="Corrección",
        )

        tab_stt.rowconfigure(2, weight=0)
        tab_stt.rowconfigure(3, weight=0)

        # ── Tab IA ───────────────────────────────────────────────────────────
        _build_sus_tab(
            tab_ia,
            vocab.get("sustituciones_ia", {}),
            "_vocab_tree_ia",
            col_origen="Palabra/s detectadas",
            col_destino="Corrección",
        )

    def _guardar_vocabulario(self):
        sustituciones = {}
        for item in self._vocab_tree.get_children():
            origen, destino = self._vocab_tree.item(item, "values")
            if origen and destino:
                sustituciones[origen] = destino

        sustituciones_ia = {}
        if hasattr(self, "_vocab_tree_ia"):
            for item in self._vocab_tree_ia.get_children():
                origen, destino = self._vocab_tree_ia.item(item, "values")
                if origen and destino:
                    sustituciones_ia[origen] = destino

        vocab = vocabulary.cargar_vocabulario()
        vocab["sustituciones"] = sustituciones
        vocab["sustituciones_ia"] = sustituciones_ia
        vocabulary._guardar(vocab)
        vocabulary._cache = vocab

    # ── PESTAÑA HISTORIAL ─────────────────────────────────────────────────────

    def _tab_historial(self, frame, _):
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        self._historial = history.cargar_historial()
        self._modos_display = {v["nombre"]: k for k, v in ai_processor.MODOS.items()}

        # ── Panel izquierdo: lista ──
        left = ttk.Frame(frame)
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        left.rowconfigure(0, weight=1)

        self._hist_listbox = tk.Listbox(
            left, width=24, activestyle="dotbox", selectmode=tk.EXTENDED
        )
        self._hist_listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(left, command=self._hist_listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._hist_listbox.config(yscrollcommand=sb.set)

        for e in self._historial:
            ts = e.get("timestamp", "")[:16].replace("T", " ")
            modo = e.get("modo", "")[:8]
            tiene_version = bool(e.get("version_usuario", "").strip())
            self._hist_listbox.insert(
                tk.END, f"{'★ ' if tiene_version else ''}{ts}  [{modo}]"
            )

        self._hist_listbox.bind("<<ListboxSelect>>", self._on_hist_select)

        btn_left = ttk.Frame(left)
        btn_left.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(btn_left, text="Eliminar", command=self._eliminar_hist_entrada).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2)
        )
        ttk.Button(
            btn_left, text="↺ Refrescar", command=self._refrescar_historial
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Panel derecho ──
        right = ttk.Frame(frame)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=0)  # LT — oculto por defecto
        right.columnconfigure(2, weight=1)

        def _text_ro(parent, height):
            t = tk.Text(
                parent,
                height=height,
                wrap=tk.WORD,
                state="disabled",
                font=("Segoe UI Variable", 11),
                background="#f5f5f5",
            )
            return t

        info_top = ttk.Frame(right)
        info_top.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 2))
        info_top.columnconfigure(0, weight=1)
        self._lbl_motor_usado = ttk.Label(
            info_top,
            text="Modelo usado: —",
            font=("Segoe UI Variable", 11),
            foreground="#666666",
        )
        self._lbl_motor_usado.pack(side=tk.LEFT)
        self._lbl_metricas = ttk.Label(
            info_top, text="", font=("Segoe UI Variable", 11), foreground="#666666"
        )
        self._lbl_metricas.pack(side=tk.RIGHT)

        _stt_header = ttk.Frame(right)
        _stt_header.grid(row=1, column=0, sticky="w", pady=(0, 2))
        ttk.Label(_stt_header, text="Transcripción original (STT):").pack(side=tk.LEFT)
        self._var_editar_stt = tk.BooleanVar(value=False)
        self._chk_editar_stt = ttk.Checkbutton(
            _stt_header,
            text="Editar",
            variable=self._var_editar_stt,
            command=self._toggle_editar_stt,
        )
        self._chk_editar_stt.pack(side=tk.LEFT, padx=(8, 0))
        self._lbl_lt_header = ttk.Label(right, text="Post-LanguageTool:")
        self._lbl_lt_header.grid(row=1, column=1, sticky="w", pady=(0, 2), padx=(4, 0))
        self._lbl_lt_header.grid_remove()
        self._lbl_corr_header = ttk.Label(right, text="Transcripción procesada (LLM):")
        self._lbl_corr_header.grid(
            row=1, column=2, sticky="w", pady=(0, 2), padx=(4, 0)
        )

        self._txt_orig_h = _text_ro(right, 7)
        self._txt_orig_h.grid(row=2, column=0, sticky="nsew", pady=(0, 3), padx=(0, 2))
        self._txt_lt_h = _text_ro(right, 7)
        self._txt_lt_h.grid(row=2, column=1, sticky="nsew", pady=(0, 3), padx=(2, 2))
        self._txt_lt_h.grid_remove()
        self._txt_corr_h = _text_ro(right, 7)
        self._txt_corr_h.grid(row=2, column=2, sticky="nsew", pady=(0, 3), padx=(2, 0))
        right.rowconfigure(2, weight=1)

        def _toggle_lt_col(mostrar):
            if mostrar:
                right.columnconfigure(1, weight=1)
                self._lbl_lt_header.grid()
                self._txt_lt_h.grid()
            else:
                right.columnconfigure(1, weight=0)
                self._lbl_lt_header.grid_remove()
                self._txt_lt_h.grid_remove()

        self._toggle_lt_col = _toggle_lt_col

        ttk.Separator(right, orient="horizontal").grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=2
        )

        ctrl_frame = ttk.Frame(right)
        ctrl_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 2))

        ttk.Label(ctrl_frame, text="Motor:").grid(row=0, column=0, padx=(0, 4))
        self._var_hist_motor = tk.StringVar(
            value=self.config.get("ia_motor", "gemini").title()
        )
        ttk.Combobox(
            ctrl_frame,
            textvariable=self._var_hist_motor,
            values=["Gemini", "Groq", "OpenAI", "Ollama"],
            state="readonly",
            width=8,
        ).grid(row=0, column=1, padx=(0, 8))

        ttk.Label(ctrl_frame, text="Modo:").grid(row=0, column=2, padx=(0, 4))
        _nombres = list(self._modos_display.keys())
        _default_nombre = (
            "Asistido"
            if "Asistido" in self._modos_display
            else (_nombres[0] if _nombres else "")
        )
        self._var_hist_modo = tk.StringVar(value=_default_nombre)
        self._cb_hist_modo = ttk.Combobox(
            ctrl_frame,
            textvariable=self._var_hist_modo,
            values=list(self._modos_display.keys()),
            state="readonly",
            width=18,
        )
        self._cb_hist_modo.grid(row=0, column=3, padx=(0, 6))
        self._var_hist_modo_cb = self._cb_hist_modo
        self._var_hist_modo_cb.bind(
            "<<ComboboxSelected>>",
            lambda e: (
                self._actualizar_prompt_desde_modo(),
                self._actualizar_temp_desde_modo(),
            ),
        )

        self._var_prompt_custom = tk.BooleanVar(value=False)
        self._chk_prompt_custom = ttk.Checkbutton(
            ctrl_frame,
            text="Editar prompt",
            variable=self._var_prompt_custom,
            command=self._on_toggle_prompt_custom,
        )
        self._chk_prompt_custom.grid(row=0, column=4, padx=(0, 8))

        ttk.Label(ctrl_frame, text="Temp:").grid(row=0, column=5, padx=(0, 4))
        self._var_hist_temp = tk.DoubleVar(value=0.2)
        ttk.Spinbox(
            ctrl_frame,
            textvariable=self._var_hist_temp,
            from_=0.0,
            to=1.0,
            increment=0.05,
            width=5,
            format="%.2f",
        ).grid(row=0, column=6, padx=(0, 6))

        self._var_comparar = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            ctrl_frame,
            text="Comparar",
            variable=self._var_comparar,
            command=self._toggle_comparar,
        ).grid(row=0, column=7, padx=(0, 0))

        # col 8 espaciadora con weight=1
        ctrl_frame.columnconfigure(8, weight=1)

        self._btn_audio = ttk.Button(
            ctrl_frame,
            text="▶ Reproducir audio",
            command=self._reproducir_audio_entrada,
        )
        self._btn_audio.grid(row=0, column=9, padx=(8, 0))

        ttk.Button(
            ctrl_frame,
            text="Reprocesar",
            style="Accent.TButton",
            command=self._reprocesar_hist,
        ).grid(row=0, column=10, padx=(4, 0))

        prompt_header = ttk.Frame(right)
        prompt_header.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        ttk.Label(prompt_header, text="Prompt:").pack(side=tk.LEFT)

        _tema = self.config.get("tema", "light")
        self._txt_prompt_custom = tk.Text(
            right,
            height=5,
            wrap=tk.WORD,
            font=("Segoe UI Variable", 11),
            foreground="gray",
            state="disabled",
            background="#2A2A2A" if _tema == "dark" else "#f5f5f5",
        )
        self._txt_prompt_custom.grid(
            row=7, column=0, columnspan=3, sticky="nsew", pady=(0, 2)
        )
        right.rowconfigure(7, weight=1)

        btn_prompt_row = ttk.Frame(right)
        btn_prompt_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        self._btn_nuevo_prompt = ttk.Button(
            btn_prompt_row,
            text="Guardar como",
            style="Accent.TButton",
            command=self._crear_modo_desde_prompt,
            state="disabled",
        )
        self._btn_nuevo_prompt.pack(side=tk.LEFT)

        def _guardar_cambios_prompt():
            nombre_visible = self._var_hist_modo.get()
            modo_key = self._modos_display.get(nombre_visible)
            if not modo_key:
                return
            modo = self._modos_data.get(modo_key, {})
            if modo.get("protegido", False):
                self._lbl_guardado_h.config(text="🔒 Modo protegido", foreground="red")
                self.win.after(2000, lambda: self._lbl_guardado_h.config(text=""))
                return
            nuevo_prompt = self._txt_prompt_custom.get("1.0", tk.END).strip()
            modo["prompt"] = nuevo_prompt
            modo["prompt_es"] = nuevo_prompt
            modo["prompt_libre"] = nuevo_prompt
            modo["modo_editor"] = "libre"
            import logging

            logging.getLogger(__name__).info(
                f"Guardando prompt en modo_key={modo_key}, modo_editor=libre"
            )
            ai_processor.MODOS[modo_key] = modo
            self._guardar_modos_json()
            self._lbl_guardado_h.config(text="✓ Guardado", foreground="green")
            self.win.after(2000, lambda: self._lbl_guardado_h.config(text=""))

        ttk.Button(
            btn_prompt_row, text="Guardar cambios", command=_guardar_cambios_prompt
        ).pack(side=tk.LEFT, padx=(4, 0))
        self._lbl_guardado_h = ttk.Label(btn_prompt_row, text="")
        self._lbl_guardado_h.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            btn_prompt_row,
            text="Copiar proceso",
            style="Accent.TButton",
            command=self._copiar_resultado_hist,
        ).pack(side=tk.RIGHT)

        _BW = 24  # ancho uniforme para botones donde se necesite

        lbl_result_row = ttk.Frame(right)
        lbl_result_row.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(0, 2))
        ttk.Label(lbl_result_row, text="Nuevo Procesado:").pack(side=tk.LEFT)

        self._txt_result_h = _text_ro(right, 7)
        self._txt_result_h.grid(
            row=10, column=0, columnspan=3, sticky="nsew", pady=(0, 4)
        )
        right.rowconfigure(2, weight=2)
        right.rowconfigure(10, weight=2)

        ttk.Separator(right, orient="horizontal").grid(
            row=11, column=0, columnspan=3, sticky="ew", pady=4
        )

        vocab_frame = ttk.LabelFrame(right, text="Añadir al vocabulario")
        vocab_frame.grid(
            row=12, column=0, columnspan=3, sticky="ew", padx=8, pady=(4, 4)
        )
        vocab_frame.columnconfigure(1, weight=1)
        vocab_frame.columnconfigure(3, weight=1)

        def _añadir_vocab(clave, var_origen, var_destino, lbl_ok):
            origen = var_origen.get().strip()
            destino = var_destino.get().strip()
            if not origen or not destino:
                return
            vocabulary._cache = None
            vocab = vocabulary.cargar_vocabulario()
            sust = vocab.get(clave, {})

            clave_existente = None
            for k, v in sust.items():
                if v.strip().lower() == destino.strip().lower():
                    clave_existente = k
                    break

            if clave_existente:
                origenes = [o.strip() for o in clave_existente.split(";")]
                if origen not in origenes:
                    origenes.append(origen)
                    nueva_clave = "; ".join(origenes)
                    sust[nueva_clave] = destino
                    del sust[clave_existente]
            else:
                sust[origen] = destino

            vocab[clave] = sust
            vocabulary._guardar(vocab)
            vocabulary._cache = vocab
            var_origen.set("")
            lbl_ok.config(text="✓ Añadido")
            self.win.after(2000, lambda: lbl_ok.config(text=""))
            self._refrescar_vocab_trees()

        # Cabeceras para las columnas de vocabulario
        ttk.Label(
            vocab_frame, text="Añadir palabra/s:", font=("Segoe UI Variable", 8, "bold")
        ).grid(row=0, column=1, sticky="w", padx=(0, 4), pady=(4, 0))
        ttk.Label(
            vocab_frame, text="Corrección:", font=("Segoe UI Variable", 8, "bold")
        ).grid(row=0, column=3, sticky="w", padx=(0, 4), pady=(4, 0))

        for row_idx, (label_txt, clave) in enumerate(
            [
                ("STT (local):", "sustituciones"),
                ("Resultado IA:", "sustituciones_ia"),
            ],
            start=1,
        ):
            var_orig = tk.StringVar()
            var_dest = tk.StringVar()
            lbl_ok = ttk.Label(vocab_frame, text="", foreground="green")

            ttk.Label(vocab_frame, text=label_txt, width=18, anchor="w").grid(
                row=row_idx, column=0, padx=(8, 4), pady=(6, 2), sticky="w"
            )
            ttk.Entry(vocab_frame, textvariable=var_orig, width=18).grid(
                row=row_idx, column=1, sticky="ew", padx=(0, 4), pady=(6, 2)
            )
            ttk.Label(vocab_frame, text=">>>").grid(row=row_idx, column=2, padx=4)
            ttk.Entry(vocab_frame, textvariable=var_dest, width=18).grid(
                row=row_idx, column=3, sticky="ew", padx=(0, 4), pady=(6, 2)
            )
            ttk.Button(
                vocab_frame,
                text="Añadir",
                style="Accent.TButton",
                command=lambda c=clave, o=var_orig, d=var_dest, l=lbl_ok: _añadir_vocab(
                    c, o, d, l
                ),
            ).grid(row=row_idx, column=4, padx=(0, 4), pady=(6, 2))
            lbl_ok.grid(row=row_idx, column=5, padx=(0, 8), pady=(6, 2), sticky="w")

        ttk.Label(
            vocab_frame,
            text="* Nivel 1 (STT): corrige lo que transcribe el motor de voz.   "
            "* Nivel 2 (post-IA): corrige el resultado tras el procesado IA.",
            foreground="gray",
            font=("Segoe UI Variable", 8),
        ).grid(row=3, column=0, columnspan=6, padx=8, pady=(0, 6), sticky="w")

    def _set_txt_ro(self, widget, texto):
        widget.config(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", texto)
        widget.config(state="disabled")

    def _calcular_max_tokens_motor(self, motor):
        historial = getattr(self, "_historial", None) or history.cargar_historial()
        reset_fecha = self.config.get(f"{motor}_tokens_reset_date", "")
        max_in = max_out = 0
        for e in historial:
            if e.get("motor", "").lower() != motor.lower():
                continue
            if reset_fecha and e.get("timestamp", "") < reset_fecha:
                continue
            max_in = max(max_in, e.get("tokens_prompt", 0))
            max_out = max(max_out, e.get("tokens_output", 0))
        return max_in, max_out

    def _refrescar_historial(self):
        self._historial = history.cargar_historial()
        self._hist_listbox.delete(0, tk.END)
        for e in self._historial:
            ts = e.get("timestamp", "")[:16].replace("T", " ")
            modo = e.get("modo", "")[:8]
            tiene_version = bool(e.get("version_usuario", "").strip())
            self._hist_listbox.insert(
                tk.END, f"{'★ ' if tiene_version else ''}{ts}  [{modo}]"
            )
        if self._historial:
            self._hist_listbox.selection_set(0)
            self._on_hist_select()

    def _actualizar_temp_desde_modo(self):
        modo = self._modos_display.get(self._var_hist_modo.get(), "")
        temp = ai_processor.MODOS.get(modo, {}).get("temperatura_es", 0.2)
        self._var_hist_temp.set(temp)

    def _on_hist_select(self, _event=None):
        sel = self._hist_listbox.curselection()
        if not sel:
            return
        self._hist_idx_seleccionado = sel[0]
        e = self._historial[sel[0]]
        self._var_editar_stt.set(False)
        self._txt_orig_h.config(state="disabled")
        self._var_comparar.set(False)
        self._set_txt_ro(self._txt_orig_h, e.get("original", ""))
        self._set_txt_ro(self._txt_corr_h, e.get("corregido", ""))
        self._set_txt_ro(self._txt_result_h, "")
        texto_lt_raw = e.get("texto_languagetool", "")
        texto_lt = "" if texto_lt_raw == "__lt_activo__" else texto_lt_raw
        if texto_lt:
            self._set_txt_ro(self._txt_lt_h, texto_lt)
            self._toggle_lt_col(True)
        elif texto_lt_raw == "__lt_activo__":
            self._set_txt_ro(self._txt_lt_h, "(LanguageTool activo — sin cambios)")
            self._toggle_lt_col(True)
        else:
            self._set_txt_ro(self._txt_lt_h, "")
            self._toggle_lt_col(False)
        motor = e.get("motor") or "—"
        modo = e.get("modo") or "normal"
        self._lbl_motor_usado.config(text=f"Modo: {modo}")

        t_stt = e.get("tiempo_stt", 0)
        t_llm = e.get("tiempo_llm", 0)
        tok_in = e.get("tokens_prompt", 0)
        tok_out = e.get("tokens_output", 0)
        pal_in = e.get("palabras_entrada", 0)
        pal_out = e.get("palabras_salida", 0)
        densidad = e.get("densidad_correccion", 0)
        duracion = e.get("duracion_audio", 0)
        stt_mod = e.get("modelo_stt", "—")
        incompleto = (
            "" if e.get("resultado_completo", True) else "  |  ⚠ Resultado incompleto"
        )

        metricas = (
            f"STT: {stt_mod}: {t_stt}s"
            f"  |  Motor IA: {motor}: {t_llm}s"
            f"  |  Tokens: {tok_in}+{tok_out}"
            f"  |  Palabras: {pal_in}>{pal_out}"
            f"  |  Audio: {duracion}s"
            f"  |  Densidad: {densidad}"
            f"{incompleto}"
        )
        try:
            self._lbl_metricas.config(text=metricas)
        except Exception:
            pass
        try:
            self._lbl_corr_header.config(
                text=f"Transcripción procesada IA:  ({motor} · {modo})"
            )
        except AttributeError:
            pass
        modo_cfg_entry = ai_processor.MODOS.get(modo, {})
        modo_nombre = modo_cfg_entry.get("nombre", modo)
        self._var_hist_modo.set(
            modo_nombre if modo_nombre in self._modos_display else modo
        )
        if not self._var_prompt_custom.get():
            self._actualizar_prompt_desde_modo()
        self._actualizar_temp_desde_modo()

    def _on_toggle_prompt_custom(self):
        activo = self._var_prompt_custom.get()
        tema = self.config.get("tema", "light")
        bg_on = "#1A1A1A" if tema == "dark" else "white"
        fg_on = "#F0F0F0" if tema == "dark" else "black"
        bg_off = "#2A2A2A" if tema == "dark" else "#f5f5f5"
        if activo:
            self._txt_prompt_custom.config(
                state="normal", foreground=fg_on, background=bg_on
            )
            self._var_hist_modo_cb.config(state="disabled")
            self._btn_nuevo_prompt.config(state="normal")
        else:
            self._txt_prompt_custom.config(
                state="disabled", foreground="gray", background=bg_off
            )
            self._var_hist_modo_cb.config(state="readonly")
            self._btn_nuevo_prompt.config(state="disabled")
            self._actualizar_prompt_desde_modo()

    def _actualizar_prompt_desde_modo(self):
        modo = self._modos_display.get(
            self._var_hist_modo.get(), self._var_hist_modo.get()
        )
        prompt = ai_processor.MODOS.get(modo, {}).get("prompt", "")
        self._txt_prompt_custom.config(state="normal")
        self._txt_prompt_custom.delete("1.0", tk.END)
        self._txt_prompt_custom.insert("1.0", prompt)
        self._txt_prompt_custom.config(state="disabled", foreground="gray")

    def _guardar_cambios_prompt(self):
        import logging

        log = logging.getLogger(__name__)
        modo = self._modos_display.get(
            self._var_hist_modo.get(), self._var_hist_modo.get()
        )
        nuevo_prompt = self._txt_prompt_custom.get("1.0", tk.END).strip()
        if modo not in ai_processor.MODOS:
            return
        ai_processor.MODOS[modo]["prompt"] = nuevo_prompt
        modos_file = os.path.join(BASE_DIR, "modos.json")
        try:
            with open(modos_file, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if modo in datos:
                datos[modo]["prompt"] = nuevo_prompt
                with open(modos_file, "w", encoding="utf-8") as f:
                    json.dump(datos, f, indent=2, ensure_ascii=False)
            log.info(f"Prompt del modo '{modo}' actualizado")
        except Exception as e:
            log.error(f"Error guardando prompt: {e}")

    def _crear_modo_desde_prompt(self):
        prompt = self._txt_prompt_custom.get("1.0", tk.END).strip()

        # ── Diálogo custom ────────────────────────────────────────────────────
        dlg = tk.Toplevel(self.win)
        dlg.title("Nuevo modo")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.attributes("-topmost", True)
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"320x180+{(sw - 320) // 2}+{(sh - 180) // 2}")

        ttk.Label(dlg, text="Nombre del modo:").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4)
        )
        var_nombre = tk.StringVar()
        ttk.Entry(dlg, textvariable=var_nombre, width=30).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8)
        )

        ttk.Label(dlg, text="Idioma del prompt:").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 4)
        )
        var_idioma = tk.StringVar(value="es")
        rf = ttk.Frame(dlg)
        rf.grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))
        ttk.Radiobutton(rf, text="Español", variable=var_idioma, value="es").pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Radiobutton(rf, text="Inglés", variable=var_idioma, value="en").pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Radiobutton(rf, text="Ambos", variable=var_idioma, value="ambos").pack(
            side=tk.LEFT
        )

        resultado = []

        def aceptar():
            n = var_nombre.get().strip()
            if n:
                resultado.append((n, var_idioma.get()))
            dlg.destroy()

        bf = ttk.Frame(dlg)
        bf.grid(row=4, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(bf, text="Aceptar", command=aceptar, style="Accent.TButton").pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(bf, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.bind("<Return>", lambda e: aceptar())
        dlg.wait_window()

        if not resultado:
            return
        nombre, idioma = resultado[0]
        # ── Crear modo ────────────────────────────────────────────────────────
        key = nombre.lower().replace(" ", "_")
        modo_base = self._modos_display.get(
            self._var_hist_modo.get(), self._var_hist_modo.get()
        )
        nuevo = dict(ai_processor.MODOS.get(modo_base, {}))
        nuevo["nombre"] = nombre
        nuevo["sistema"] = False

        nuevo["prompt"] = prompt  # campo genérico siempre actualizado
        nuevo["prompt_libre"] = prompt
        nuevo["modo_editor"] = "libre"
        if idioma == "es":
            nuevo["prompt_es"] = prompt
        elif idioma == "en":
            nuevo["prompt_en"] = prompt
        else:  # ambos
            nuevo["prompt_es"] = prompt
            nuevo["prompt_en"] = prompt

        ai_processor.MODOS[key] = nuevo

        # Guardar en modos.json con escritura atómica
        modos_file = os.path.join(BASE_DIR, "modos.json")
        try:
            with open(modos_file, "r", encoding="utf-8") as f:
                datos = json.load(f)
            datos[key] = nuevo
            tmp = modos_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, modos_file)
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Error guardando nuevo modo: {e}")
            return

        # Sincronizar con la pestaña Modos
        self._modos_data[key] = nuevo

        self._modos_keys.append(key)
        if hasattr(self, "_modos_listbox"):
            self._modos_listbox.insert(tk.END, self._nombre_lista(key))

        # Actualizar combobox del historial con el nuevo modo
        self._modos_display[nombre] = key
        nombres = list(self._modos_display.keys())
        self._cb_hist_modo.config(values=nombres)
        self._var_hist_modo.set(nombre)

        self._notify_modos_change()

    def _reprocesar_con_prompt_custom(self):
        import threading, copy

        original = self._txt_orig_h.get("1.0", tk.END).strip()
        if not original:
            return
        prompt = self._txt_prompt_custom.get("1.0", tk.END).strip()
        if not prompt:
            return
        motor = self._var_hist_motor.get().lower()
        temperatura = self._var_hist_temp.get()
        self._set_txt_ro(self._txt_result_h, "Procesando...")

        def run():
            modo_cfg_temp = copy.deepcopy(ai_processor.MODOS.get("asistida", {}))
            modo_cfg_temp["prompt"] = prompt
            modo_cfg_temp["prompt_es"] = prompt
            ai_processor.MODOS["_prompt_temp"] = modo_cfg_temp
            resultado = corregir_texto(
                original,
                modo="_prompt_temp",
                ia_motor=motor,
                groq_key=self.config.get("groq_key", ""),
                gemini_key=self.config.get("gemini_key", ""),
                openai_key=self.config.get("openai_key", ""),
                temperatura=temperatura,
                config=self.config,
            )
            ai_processor.MODOS.pop("_prompt_temp", None)
            self.win.after(0, lambda: self._set_txt_ro(self._txt_result_h, resultado))
            if getattr(self, "_var_comparar", None) and self._var_comparar.get():
                self.win.after(50, self._comparar_textos_hist)

        threading.Thread(target=run, daemon=True).start()

    def _reproducir_audio_entrada(self):
        import sounddevice as sd
        import soundfile as sf
        import threading, logging
        from pathlib import Path
        import datetime

        log = logging.getLogger(__name__)

        if getattr(self, "_reproduciendo_audio", False):
            sd.stop()
            self._reproduciendo_audio = False
            self._btn_audio.config(text="▶ Reproducir audio")
            return

        sel = self._hist_listbox.curselection()
        if not sel:
            return
        entrada = self._historial[sel[0]]
        ts = entrada.get("timestamp", "")
        if not ts:
            return
        try:
            dt = datetime.datetime.fromisoformat(ts)
            ts_unix = int(dt.timestamp())
        except Exception:
            return
        cache_dir = os.path.join(BASE_DIR, "audio_cache")
        wavs = sorted(Path(cache_dir).glob("*.wav"))
        if not wavs:
            return
        mejor = min(
            wavs, key=lambda w: abs(int(w.stem.replace("audio_", "")) - ts_unix)
        )

        self._reproduciendo_audio = True
        self._btn_audio.config(text="⏹ Detener audio")

        def _reproducir():
            try:
                data, samplerate = sf.read(str(mejor))
                sd.play(data, samplerate)
                sd.wait()
            except Exception as e:
                log.warning(f"Error reproduciendo audio: {e}")
            finally:
                self._reproduciendo_audio = False
                self.win.after(
                    0, lambda: self._btn_audio.config(text="▶ Reproducir audio")
                )

        threading.Thread(target=_reproducir, daemon=True).start()

    def _toggle_editar_stt(self):
        estado = "normal" if self._var_editar_stt.get() else "disabled"
        self._txt_orig_h.config(state=estado)

    def _procesar_texto_manual(self):
        texto = self._txt_orig_h.get("1.0", tk.END).strip()
        if not texto:
            return
        self._reprocesar_hist(texto_override=texto)

    def _reprocesar_hist(self, texto_override=None):
        import threading, logging

        log = logging.getLogger(__name__)
        original = (
            texto_override
            if texto_override is not None
            else self._txt_orig_h.get("1.0", tk.END).strip()
        )
        if not original:
            return
        modo = self._modos_display.get(
            self._var_hist_modo.get(), self._var_hist_modo.get()
        )
        motor = self._var_hist_motor.get().lower()
        temperatura = self._var_hist_temp.get()
        usar_prompt_custom = self._var_prompt_custom.get()
        prompt_custom = (
            self._txt_prompt_custom.get("1.0", tk.END).strip()
            if usar_prompt_custom
            else ""
        )
        log.info(
            f"Reprocesar | modo={modo} | motor={motor} | temp={temperatura} | prompt_custom={usar_prompt_custom}"
        )
        self._set_txt_ro(self._txt_result_h, "Procesando...")

        def run():
            texto_entrada = vocabulary.aplicar_sustituciones(original)
            if usar_prompt_custom:
                import copy

                modo_cfg_temp = copy.deepcopy(MODOS.get(modo, {}))
                modo_cfg_temp["prompt"] = prompt_custom
                modo_cfg_temp["prompt_es"] = prompt_custom
                modo_cfg_temp["temperatura"] = temperatura
                MODOS["_custom_temp"] = modo_cfg_temp
                resultado = corregir_texto(
                    texto_entrada,
                    modo="_custom_temp",
                    ia_motor=motor,
                    groq_key=self.config.get("groq_key", ""),
                    gemini_key=self.config.get("gemini_key", ""),
                    openai_key=self.config.get("openai_key", ""),
                    temperatura=temperatura,
                    config=self.config,
                )
                MODOS.pop("_custom_temp", None)
            else:
                resultado = corregir_texto(
                    texto_entrada,
                    modo=modo,
                    ia_motor=motor,
                    groq_key=self.config.get("groq_key", ""),
                    gemini_key=self.config.get("gemini_key", ""),
                    openai_key=self.config.get("openai_key", ""),
                    temperatura=temperatura,
                    config=self.config,
                )
            resultado = vocabulary.aplicar_sustituciones_ia(resultado)
            self.win.after(0, lambda: self._set_txt_ro(self._txt_result_h, resultado))
            if getattr(self, "_var_comparar", None) and self._var_comparar.get():
                self.win.after(50, self._comparar_textos_hist)

        threading.Thread(target=run, daemon=True).start()

    def _toggle_comparar(self):
        if self._var_comparar.get():
            self._comparar_textos_hist()
        else:
            for txt in (self._txt_orig_h, self._txt_corr_h, self._txt_result_h):
                txt.tag_remove("eliminado", "1.0", tk.END)
                txt.tag_remove("añadido", "1.0", tk.END)
                txt.tag_remove("añadido_resultado", "1.0", tk.END)

    def _comparar_textos_hist(self):
        import difflib

        texto_stt = self._txt_orig_h.get("1.0", tk.END).strip()
        texto_corr = self._txt_corr_h.get("1.0", tk.END).strip()
        texto_result = self._txt_result_h.get("1.0", tk.END).strip()
        if not texto_stt:
            return

        for txt in (self._txt_orig_h, self._txt_corr_h, self._txt_result_h):
            txt.tag_remove("eliminado", "1.0", tk.END)
            txt.tag_remove("añadido", "1.0", tk.END)
            txt.tag_remove("añadido_resultado", "1.0", tk.END)
        self._txt_orig_h.tag_config(
            "eliminado", background="#ff4444", foreground="white"
        )
        self._txt_corr_h.tag_config("añadido", background="#44aa44", foreground="white")
        self._txt_result_h.tag_config(
            "añadido_resultado", background="#4488ff", foreground="white"
        )

        def _marcar_palabras(widget, texto, palabras, indices_cambio, tag):
            pos = 0
            for i, palabra in enumerate(palabras):
                inicio = texto.find(palabra, pos)
                if inicio == -1:
                    continue
                fin = inicio + len(palabra)
                if i in indices_cambio:
                    widget.tag_add(tag, f"1.0+{inicio}c", f"1.0+{fin}c")
                pos = fin

        if texto_corr:
            palabras_stt = texto_stt.split()
            palabras_corr = texto_corr.split()
            cambios_stt, cambios_corr = set(), set()
            for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, palabras_stt, palabras_corr
            ).get_opcodes():
                if op in ("replace", "delete"):
                    cambios_stt.update(range(i1, i2))
                if op in ("replace", "insert"):
                    cambios_corr.update(range(j1, j2))
            _marcar_palabras(
                self._txt_orig_h, texto_stt, palabras_stt, cambios_stt, "eliminado"
            )
            _marcar_palabras(
                self._txt_corr_h, texto_corr, palabras_corr, cambios_corr, "añadido"
            )

        if texto_result:
            palabras_stt = texto_stt.split()
            palabras_result = texto_result.split()
            cambios_result = set()
            for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, palabras_stt, palabras_result
            ).get_opcodes():
                if op in ("replace", "insert"):
                    cambios_result.update(range(j1, j2))
            _marcar_palabras(
                self._txt_result_h,
                texto_result,
                palabras_result,
                cambios_result,
                "añadido_resultado",
            )

    def _exportar_hist_seleccion(self):
        import datetime
        from tkinter import filedialog

        sel = self._hist_listbox.curselection()
        if not sel:
            return
        entradas = [self._historial[i] for i in sel]
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"speakme_export_{datetime.date.today()}.json",
            parent=self.win,
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entradas, f, indent=2, ensure_ascii=False)

    def _copiar_resultado_hist(self):
        sel = self._hist_listbox.curselection()
        e = self._historial[sel[0]] if sel else {}

        orig = self._txt_orig_h.get("1.0", tk.END).strip()
        corr = self._txt_corr_h.get("1.0", tk.END).strip()
        texto_lt = e.get("texto_languagetool", "").strip()
        motor = e.get("motor", "—")
        modo = e.get("modo", "—")
        t_stt = e.get("tiempo_stt", 0)
        t_llm = e.get("tiempo_llm", 0)
        tok_in = e.get("tokens_prompt", 0)
        tok_out = e.get("tokens_output", 0)
        pal_in = e.get("palabras_entrada", 0)
        pal_out = e.get("palabras_salida", 0)
        dur = e.get("duracion_audio", 0)
        dens = e.get("densidad_correccion", 0)
        stt_mod = e.get("modelo_stt", "—")
        ts = e.get("timestamp", "")

        lt_activo = bool(
            texto_lt
        )  # activo si hay cambios O si el sentinel indica que estuvo activo
        lt_estuvo_activo = lt_activo or texto_lt == "__lt_activo__"
        lt_activo = lt_estuvo_activo
        texto_lt = (
            texto_lt if texto_lt != "__lt_activo__" else ""
        )  # limpiar sentinel del display
        motor_label = motor
        if motor == "none" and lt_activo:
            motor_label = "none + LanguageTool"
        elif lt_activo:
            motor_label = f"{motor} + LanguageTool"

        prompt_en_pantalla = self._txt_prompt_custom.get("1.0", tk.END).strip()
        if motor == "none" and lt_activo:
            prompt = "LanguageTool"
        else:
            prompt = (
                e.get("prompt_usado")
                or prompt_en_pantalla
                or ai_processor.MODOS.get(modo, {}).get("prompt", "—")
            )

        resultado_reprocesado = self._txt_result_h.get("1.0", tk.END).strip()

        lineas = [
            f"=== SPEAKME — PROCESO COMPLETO ===",
            f"Fecha: {ts}",
            f"",
            f"--- TEXTO ORIGINAL ({stt_mod}) ---",
            orig or "—",
        ]

        if texto_lt:
            lineas += [
                f"",
                f"--- POST-LANGUAGETOOL ---",
                texto_lt,
            ]

        lineas += [
            f"",
            f"--- PROCESO ORIGINAL ---",
            f"Motor IA: {motor_label}  |  Modo: {modo}",
            f"STT: {t_stt}s  |  LLM: {t_llm}s  |  Tokens: {tok_in}+{tok_out}",
            f"Palabras: {pal_in}→{pal_out}  |  Audio: {dur}s  |  Densidad: {dens}",
            f"",
            corr or "—",
        ]

        if resultado_reprocesado:
            motor_repr = (
                self._var_hist_motor.get()
            )  # display name, no necesita lowercase
            modo_repr = self._var_hist_modo.get()
            lineas += [
                f"",
                f"--- REPROCESADO ---",
                f"Motor: {motor_repr}  |  Modo: {modo_repr}",
                f"",
                resultado_reprocesado,
            ]

        lineas += [
            f"",
            f"--- PROMPT UTILIZADO ---",
            prompt,
            f"",
            f"=== FIN ===",
        ]

        contenido = "\n".join(lineas)
        self.win.clipboard_clear()
        self.win.clipboard_append(contenido)

    def _traducir_hist(self, idioma_destino: str):
        import threading, logging
        from ai_processor import traducir

        log = logging.getLogger(__name__)
        texto = self._txt_result_h.get("1.0", tk.END).strip()
        if not texto:
            texto = self._txt_corr_h.get("1.0", tk.END).strip()
        if not texto:
            return
        self._set_txt_ro(
            self._txt_result_h, f"Traduciendo → {idioma_destino.upper()}..."
        )

        def run():
            resultado = traducir(
                texto,
                idioma_destino,
                ia_motor=self.config.get("ia_motor", "ollama"),
                groq_key=self.config.get("groq_key", ""),
                gemini_key=self.config.get("gemini_key", ""),
            )
            self.win.after(0, lambda: self._set_txt_ro(self._txt_result_h, resultado))
            if getattr(self, "_var_comparar", None) and self._var_comparar.get():
                self.win.after(50, self._comparar_textos_hist)

        threading.Thread(target=run, daemon=True).start()

    def _eliminar_hist_entrada(self):
        sel = self._hist_listbox.curselection()
        if not sel:
            return
        # Borrar en orden inverso para no desplazar índices
        for idx in reversed(sel):
            self._historial.pop(idx)
            self._hist_listbox.delete(idx)
        history._escribir(list(reversed(self._historial)))
        for w in (self._txt_orig_h, self._txt_corr_h, self._txt_result_h):
            self._set_txt_ro(w, "")

    # ── GUARDAR ───────────────────────────────────────────────────────────────

    def _aplicar(self):
        self._guardar_sin_cerrar(_cerrar=False)

    def _guardar_sin_cerrar(self, _cerrar=False):
        motor_ui = self._var_motor.get() if hasattr(self, "_var_motor") else ""
        ia_activo = (
            self._var_ia_activo.get() if hasattr(self, "_var_ia_activo") else True
        )

        if ia_activo and motor_ui not in ("", "none"):
            key_var = (
                self._ia_key_vars.get(motor_ui)
                if hasattr(self, "_ia_key_vars")
                else None
            )
            key_actual = key_var.get().strip() if key_var else ""
            if motor_ui != "ollama" and not key_actual:
                if not messagebox.askyesno(
                    "Sin KEY configurada",
                    "No hay KEY válida para este motor.\n\n¿Continuar y guardar de todas formas?",
                    parent=self.win,
                ):
                    return
            elif self._motor_check_ok is None:
                messagebox.showwarning(
                    "Verificación pendiente",
                    "Verifica la conexión con el motor IA antes de aplicar.\n\n"
                    "Pulsa 'Probar conexión' o desactiva el Motor IA para continuar.",
                    parent=self.win,
                )
                return
            elif self._motor_check_ok is False:
                messagebox.showerror(
                    "Motor no disponible",
                    "Modelo no disponible. Por favor, seleccione otro modelo válido.",
                    parent=self.win,
                )
                return

        self._ejecutar_guardado(_cerrar)

    def _ejecutar_guardado(self, cerrar=False):
        # Llamado desde _guardar_sin_cerrar (sync o async vía callback del hilo)
        for key, (var, mapping) in self._vars.items():
            val = var.get()
            self.config[key] = mapping[val] if mapping else val

        for key in list(self.config):
            if key.endswith(("_rpm_limite", "_rpd_limite")):
                try:
                    self.config[key] = int(self.config[key])
                except (ValueError, TypeError):
                    pass

        if self._grab_vars:
            self.config["trigger_type"] = self._grab_vars["trigger_type"].get()
            self.config["trigger_button"] = self._grab_vars["trigger_button"].get()
            self.config["trigger_tecla"] = self._grab_vars["trigger_tecla"].get()
            self.config["modo_grabacion"] = self._grab_vars["modo_grabacion"].get()
            mic_name = self._grab_vars["mic"].get()
            self.config["mic_index"] = self._mic_map.get(
                mic_name, self.config.get("mic_index", 1)
            )

        if hasattr(self, "_atajo_vars"):
            for key, var in self._atajo_vars.items():
                self.config[key] = var.get()

        if hasattr(self, "_motores_vars"):
            for key, var in self._motores_vars.items():
                self.config[key] = var.get()
            for service, var in self._ia_key_vars.items():
                self.config[f"{service}_key"] = var.get()

        if hasattr(self, "_var_ia_activo"):
            self.config["ia_activo"] = self._var_ia_activo.get()

        if hasattr(self, "_vocab_tree"):
            self._guardar_vocabulario()

        self.on_save(self.config)

        if hasattr(self, "_actualizar_lbl_config_fn"):
            try:
                self._actualizar_lbl_config_fn()
            except Exception:
                pass

        if hasattr(self, "_toggle_ia_fn"):
            self._toggle_ia_fn(self.config.get("ia_motor", "ollama"))

        if cerrar:
            self.win.destroy()

    def _guardar(self):
        if self._hay_cambios_sin_guardar():
            respuesta = tk.messagebox.askyesnocancel(
                "Cambios sin guardar",
                "Hay cambios sin guardar en el modo actual.\n\n"
                "¿Deseas guardarlos antes de cerrar?",
                parent=self.win,
            )
            if respuesta is True:
                self._guardar_modo_actual()
            elif respuesta is None:
                return
        self._guardar_sin_cerrar(_cerrar=False)
        self.win.destroy()
