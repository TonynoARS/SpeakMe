**SpeakMe!** convierte tu voz en texto en dos capas, que pueden funcionar por separado. La capa 1 es una transcripción básica 100% local y opcionalmente hay una capa 2 que procesa el resultado con IA.
Tienes control total sobre ambas capas, tanto en resultado, como en equilibrio entre coste, velocidad y calidad.


**CONFIGURACIÓN RAPIDA RECOMENDADA: ──────────────────────────────**

**Solo transcripción (STT):**
  • 1ª opción: Parakeet TDT v3
  • 2ª opción: Whisper — CPU: base/medium | GPU: Large v3-Turbo

**Transcripción + IA (STT + LLM):**
  • STT: Parakeet TDT v3 (recomendado) o Whisper según hardware
  • IA: Gemini 3.1 Flash-lite (gratuito) o GPT-4.1 mini

──────────────────────────────

### Capa 1 - MOTORES STT:

**Parakeet TDT v3**
  Optimizado para CPU. Latencia muy baja, sin GPU necesaria.
  Precisión comparable a modelos grandes de Whisper.

**Whisper — modelos disponibles:**
  Tiny    (~75M)   — Muy rápido, precisión limitada
  Base    (~145M)  — Rápido, precisión media. Recomendado sin GPU.
  Small   (~470M)  — Buena velocidad, mejor puntuación
  Medium  (~1500M) — Comprensión de contexto mejorada
  Large v2/v3/Turbo — Máxima precisión. Requiere GPU (5-6 GB VRAM / Turbo: ~2 GB)


### Capa 2 - MOTORES IA (LLM):

**- Ollama (local)**
  100% local y gratuito. Requiere instalación (~3 GB).
  Modelos pequeños (2-3B): viable en CPU | Modelos medianos (7B): requiere GPU.

**- Groq** — Llama 3.1 8B Instant
  $0.05/1M tokens entrada | $0.08/1M tokens salida
  ~$0.033 por 1000 dictados
  Muy baja latencia. Calidad suficiente para uso general.

**- OpenAI** — GPT-4.1 mini
  $0.40/1M tokens entrada | $1.60/1M tokens salida
  ~$0.36 por 1000 dictados
  Buen equilibrio coste/calidad. Sin tier gratuito.

**- Google** — Gemini 3.1 Flash-lite
  $0.25/1M tokens entrada | $1.50/1M tokens salida
  ~$0.275 por 1000 dictados
  Tier gratuito disponible. Recomendado para empezar.


 ⚠️**NOTAS Y PROBLEMAS CONOCIDOS:**
- Si hay problemas de latencia, reduce el modelo Whisper.
- Si la precisión es insuficiente, aumenta el tamaño del modelo STT.
- Ajusta los prompts para mejorar el resultado del LLM.
- Usa la opción Fallback para combinar varios LLM gratuitos.
- En ocasiones el texto transcrito puede aparecer como una respuesta
      de IA en lugar de texto limpio. Es un comportamiento conocido por
      el entrenamiento de los modelos. Solución: refuerza en el prompt
      la instrucción de no responder como asistente.

‼️ Precios actualizados a junio de 2026.