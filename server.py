import os
import io
import json
from typing import Optional, List

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from kokoro import KPipeline

# -------- Config via env --------
LANG_CODE = os.getenv("LANG_CODE", "a")  # 'a' => American English
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "af_heart")
DEFAULT_SPEED = float(os.getenv("DEFAULT_SPEED", "1.0"))
SPLIT_PATTERN = os.getenv("SPLIT_PATTERN", r"\n+")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "24000"))
# optional: extend voices via VOICES_EXTRA="v1,v2"
VOICES_EXTRA = [v.strip() for v in os.getenv("VOICES_EXTRA", "").split(",") if v.strip()]

# Minimal safe defaults — guaranteed common voice in Kokoro examples
# You can extend this at runtime with VOICES_EXTRA.
DEFAULT_VOICES = sorted(set(["af_heart"] + VOICES_EXTRA))

app = FastAPI(title="Kokoro TTS API", version="1.0")

# Lazy-load the pipeline once
pipeline: Optional[KPipeline] = None

@app.on_event("startup")
def _startup():
    global pipeline
    try:
        # Initialize once; Kokoro caches assets after first run
        pipeline = KPipeline(lang_code=LANG_CODE)
    except Exception as e:
        # Fail fast on startup if model can't load
        raise RuntimeError(f"Failed to initialize Kokoro pipeline: {e}") from e


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: Optional[float] = None
    split_pattern: Optional[str] = None
    sample_rate: Optional[int] = None


@app.get("/", response_class=HTMLResponse)
def index():
    html = f"""
    <html>
      <head>
        <title>Kokoro TTS API</title>
        <style>
          body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; padding: 2rem; }}
          code {{ background:#f2f2f2; padding:2px 4px; border-radius:4px; }}
          .card {{ border:1px solid #eee; border-radius:8px; padding:1rem; margin:1rem 0; }}
          h1, h2 {{ margin: 0.2rem 0 0.6rem 0; }}
          ul {{ margin: 0.2rem 0 0.6rem 1.2rem; }}
        </style>
      </head>
      <body>
        <h1>🗣️ Kokoro TTS API</h1>
        <div class="card">
          <h2>Endpoints</h2>
          <ul>
            <li><code>GET /</code> → this page</li>
            <li><code>GET /health</code> → health and config</li>
            <li><code>GET /voices</code> → available voices</li>
            <li><code>POST /tts</code> → synthesize speech (WAV)</li>
            <li><code>GET /docs</code> → interactive OpenAPI docs</li>
            <li><code>GET /openapi.json</code> → OpenAPI schema</li>
          </ul>
        </div>
        <div class="card">
          <h2>Quick start</h2>
          <p>Example request:</p>
          <pre><code>curl -sS -X POST http://localhost:8080/tts \\
  -H "Content-Type: application/json" \\
  -d '{{"text":"Hello from Kokoro!", "voice":"af_heart"}}' \\
  --output out.wav</code></pre>
        </div>
        <div class="card">
          <h2>Defaults</h2>
          <ul>
            <li>LANG_CODE: <code>{LANG_CODE}</code></li>
            <li>DEFAULT_VOICE: <code>{DEFAULT_VOICE}</code></li>
            <li>DEFAULT_SPEED: <code>{DEFAULT_SPEED}</code></li>
            <li>SAMPLE_RATE: <code>{SAMPLE_RATE}</code></li>
            <li>Voices: <code>{", ".join(DEFAULT_VOICES)}</code></li>
          </ul>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=200)


@app.get("/health")
def health():
    ok = pipeline is not None
    return {"status": "ok" if ok else "error", "model": "kokoro", "lang_code": LANG_CODE, "ready": ok}


@app.get("/voices")
def list_voices():
    # If Kokoro exposes a voice registry in future, add it here.
    # For now we return configured defaults.
    return {"voices": DEFAULT_VOICES}


@app.post("/tts")
def tts(req: TTSRequest):
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")

    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Field 'text' is required and must be non-empty")

    voice = req.voice or DEFAULT_VOICE
    speed = float(req.speed) if req.speed is not None else DEFAULT_SPEED
    split_pattern = req.split_pattern or SPLIT_PATTERN
    sample_rate = int(req.sample_rate) if req.sample_rate is not None else SAMPLE_RATE

    try:
        # Generate all chunks, then concatenate into a single WAV
        audio_chunks: List[np.ndarray] = []
        for _, _, audio in pipeline(text, voice=voice, speed=speed, split_pattern=split_pattern):
            audio_chunks.append(audio)

        if not audio_chunks:
            raise RuntimeError("No audio produced")

        audio_all = np.concatenate(audio_chunks, axis=0)

        buf = io.BytesIO()
        sf.write(buf, audio_all, samplerate=sample_rate, format="WAV")
        buf.seek(0)
        return StreamingResponse(buf, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {e}")
