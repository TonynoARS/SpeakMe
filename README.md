<div align="center">

<img src="assets/SpeakMe_logo.png" alt="SpeakMe!" width="150">

# SpeakMe!
🚀v0.9.5 (pre-release) 

**Voz a Texto con IA para Windows — gratis y de código abierto.**

**P**ulsa ⏩ **H**abla ⏩ **S**peakMe! lo convierte en texto.
Transforma, resume, limpia, traduce, etc. Todo depende del prompt que diseñes. SpeakMe! está pensado para experimentar. 

SpeakMe! te da control total, de forma directa y sin magia negra.

<img src="assets/Widget.gif" alt="Widget de SpeakMe! en acción" width="420">

</div>

---

## ✨ Capturas

<table>
<tr>
<td><img src="assets/Modos.png" width="400"><br><sub>**Editor de modos:** Configura prompts modulares a tu medida.</sub></td>
<td><img src="assets/Motores.png" width="400"><br><sub>**Motores STT/IA:** Soporte para modelos locales gratuitos o APIs de pago.</sub></td>
</tr>
<tr>
<td><img src="assets/Historial.png" width="400"><br><sub>**Historial:** Reprocesado de audio, herramientas de prompt y copia rápida.</sub></td>
<td><img src="assets/Vocabulario.png" width="400"><br><sub>**Vocabulario:** Añade y corrige palabras para futuros dictados.</sub></td>
</tr>
</table>

<div align="center">
<img src="assets/Notas.gif" alt="Widget de SpeakMe! en acción" width="420">

💡 Crea notas rápidas y accede a ellas cuando quieras.
</div>

---

## 🚀 Características

- 🎙️ **STT local** — Whisper o Parakeet TDT v3, 100% local, no envías audio a ningún servidor, puedes usarlo sin conexión.
- 🤖 **Modos de IA configurables** — Desde limpieza básica hasta reescritura formal. 100% configurable.
- 🔌 **Motores IA disponibles** — Gemini, Groq, OpenAI u Ollama (local).
- 📝 **Editor de Prompts modular** — Pensado para facilitar la creación de tus propios prompts BASE+INSTRUCCIONES + EJEMPLOS y prueba el resultado.
- 📚 **Vocabulario personalizado** — Añade palabras, nombres propios y términos técnicos que se corregirán automáticamente en el futuro.
- 🕘👷‍♂️ **Historial & laboratorio** — Escucha el dictado, reprocesa, experimenta, edita y compara resultados.
- 🪟 **100% Windows nativo** — Portable, sin instalación.

## 📦 Descarga

👉 [**Última versión**](https://github.com/TonynoARS/SpeakMe/releases)

1. Descarga el `.zip`
2. Descomprime
3. Ejecuta `SpeakMe.exe`

Sin instalador, sin dependencias, sin telemetría.

## 📖 Documentación

Guía completa de motores y configuración: [`assets/guia_motores.md`](assets/guia_motores.md)

## 🛠️ Motores compatibles

Elige el motor de voz que mejor se adapte a tu hardware y combínalo libremente con el proveedor de IA que prefieras. Son procesos totalmente independientes.

### Capa 1. Transcripción (STT 100% Local)

| Motor | Hardware recomendado | Especialidad / Notas |
|---|---|---|
| **Whisper (Large-v3 / Turbo)** | GPU (NVIDIA CUDA) | Máxima precisión posible. |
| **Whisper (Tiny / Base)** | CPU | Uso básico para PCs sin gráfica dedicada. |
| **Parakeet TDT v3** | CPU (Optimizado ONNX) | Ultra rápido en CPU con consumo mínimo. |

### Capa 2. Optimización y Edición (IA)

| Proveedor | Tipo | Requisitos / Notas |
|---|---|---|
| **Gemini** | API Cloud | Excelente ventana de contexto (dispone de tier gratis). 👍🏻2.5 Flash-lite. |
| **Groq** | API Cloud | Velocidad de respuesta instantánea (dispone de tier gratis). 👍🏻Llama 3.1 8B. |
| **OpenAI** | API Cloud | Estándar de la industria (pago por uso).  👍🏻GPT 4.1 mini. |
| **Ollama** | 100% Local | Privacidad absoluta (se recomienda GPU para los LLM). 👍🏻Qwen 2.5 7B. |
* Cualquier modelo de estos TIER lo puedes usar. La lista es solo una referencia de uso actual.
## ⚠️ Problemas conocidos
- El actual estado es de pre-release y pueden producirse errores indeseados. 
- Los resultados procesados con IA pueden variar según el proveedor seleccionado.
- El texto resultante puede responder con saludos o muletillas como un chatbot. Los modos por defecto incluyen instrucciones severas para evitarlo, pero no se garantiza al 100% debido a la naturaleza conversacional de los LLM.
- La primera grabación tras iniciar la app puede demorarse unos segundos adicionales mientras se carga el modelo en memoria.
- En dictados muy extensos el procesado IA puede fallar o truncarse, especialmente en planes gratuitos por limitaciones de tokens por minuto (TPM).

📒 Se agradece el Feedback!

## 🛠️ Actualizaciones futuras
- Traducción integrada al inglés.
- Soporte GPU (CUDA) para Parakeet V3.
- Mejoras de diseño en la interfaz de usuario.

## 📄 Licencia

MIT — usa, modifica y distribuye libremente.

## 🙌 Créditos y Agradecimientos

- **Tecnología STT:** OpenAI (Whisper), NVIDIA (CUDA y Parakeet TDT) y Systran (faster-whisper / CTranslate2).
- **Modelos y APIs de IA:** Google (Gemini), Meta (Llama), Ollama y Hugging Face.
- **Componentes de software:** LanguageTool GmbH y rdbende (sv_ttk).
- **Soporte de desarrollo:** Bob, Gemi y Claudia (mis asistentes de IA). 🤖

## ☕ Apoya el proyecto

Si SpeakMe! te ahorra tiempo: [ko-fi.com/speakme](https://ko-fi.com/speakme)