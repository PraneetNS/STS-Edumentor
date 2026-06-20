# EduMentor Voice 🎓

> A fully local, real-time AI voice tutor for programming and computer science.  
> **Student speaks → Whisper STT → llama.cpp LLM → Kokoro TTS → audio streams back. Target latency: 2–4 s.**

---

## Architecture

```
Browser Mic (PCM Int16 @ 16kHz via AudioWorklet)
        │ WebSocket binary frames
        ▼
FastAPI  /ws/voice
        │
        ├─► faster-whisper ──────────────► {type:"transcript"}
        │
        ├─► llama.cpp (OpenAI SSE stream) ► {type:"assistant_token"} × N
        │
        └─► Kokoro TTS (per sentence) ───► binary WAV chunks → browser playback
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | Tested on 3.11 |
| Node.js 18+ | For the React frontend |
| llama.cpp (`llama-server`) | Compiled with CUDA for GPU inference |
| CUDA (optional) | For GPU-accelerated Whisper + LLM |
| `espeak-ng` (optional) | Only needed for non-English Kokoro voices |

---

## Setup

### 1. Place your GGUF model

Copy your fine-tuned model to:

```
backend/models/EduMentor-Qwen3-Q6_K.gguf
```

### 2. Install Python dependencies

```bash
cd EduMentor-Voice/backend

# (Recommended) Create a virtual environment first
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# Install dependencies
pip install -r requirements.txt
```

> **GPU users:** Install PyTorch with CUDA support first:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cu121
> ```
> Then install the rest: `pip install -r requirements.txt`

### 3. Install frontend dependencies

```bash
cd EduMentor-Voice/frontend
npm install
```

---

## Running the Application

You need **three terminal windows** running simultaneously.

### Terminal 1 — llama.cpp Server

**Windows:**
```batch
cd EduMentor-Voice
run_llm_server.bat
```

**Linux / macOS:**
```bash
cd EduMentor-Voice
chmod +x run_llm_server.sh
./run_llm_server.sh
```

Wait until you see: `llama server listening at http://0.0.0.0:8080`

### Terminal 2 — FastAPI Backend

```bash
cd EduMentor-Voice/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Wait until you see: `All engines ready — accepting connections`

> **Note:** The first startup downloads Kokoro model weights from HuggingFace (~300 MB). Subsequent starts are instant.

### Terminal 3 — React Frontend

```bash
cd EduMentor-Voice/frontend
npm run dev
```

Open your browser at: **http://localhost:5173**

---

## Using EduMentor Voice

1. Click the **microphone button** (blue circle) — it turns red with pulsing rings
2. **Speak your question** clearly, e.g. *"Explain recursion to me"*
3. Click the **stop button** (red square)
4. Watch your transcript appear, then the assistant's answer streams in token by token
5. Audio playback begins within 2–4 seconds of stopping

---

## Configuration

Edit `backend/.env` to customise behaviour:

| Variable | Default | Description |
|---|---|---|
| `WHISPER_MODEL` | `base.en` | Whisper model size (`tiny.en`, `base.en`, `small.en`, `medium.en`) |
| `LLM_BASE_URL` | `http://localhost:8080` | llama.cpp server URL |
| `LLM_MAX_TOKENS` | `512` | Maximum LLM response tokens |
| `LLM_TEMPERATURE` | `0.7` | LLM creativity (0 = deterministic) |
| `KOKORO_VOICE` | `af_heart` | TTS voice (`af_heart`, `af_bella`, `am_adam`, `bf_emma`) |
| `KOKORO_SPEED` | `1.0` | Speech speed multiplier |

Edit `frontend/.env` to change the WebSocket URL:

```
VITE_WS_URL=ws://localhost:8000/ws/voice
```

---

## WebSocket Protocol

### Client → Server

| Frame | Meaning |
|---|---|
| Binary | Raw PCM Int16 audio @ 16 kHz mono |
| `{"type":"end_of_speech"}` | Trigger STT + LLM + TTS pipeline |
| `{"type":"ping"}` | Keepalive |

### Server → Client

| Frame | Meaning |
|---|---|
| `{"type":"transcript","text":"..."}` | User's transcribed speech |
| `{"type":"assistant_token","text":"..."}` | One LLM token |
| `{"type":"tts_start"}` | Audio is about to stream |
| Binary | WAV audio chunk (24 kHz, PCM_16) |
| `{"type":"done"}` | Turn complete |
| `{"type":"error","text":"..."}` | Pipeline error |

---

## Performance Tuning

| Area | Tip |
|---|---|
| **STT latency** | Use `tiny.en` for fastest transcription (~0.5s) |
| **LLM speed** | Increase `-ngl` in `run_llm_server.bat` to offload more layers to GPU |
| **TTS latency** | First sentence is synthesised after ~5 tokens; subsequent sentences overlap |
| **Memory** | All models stay in RAM — never reloaded between queries |
| **Context length** | Reduce `-c 4096` in the server script if GPU OOM occurs |

---

## Project Structure

```
EduMentor-Voice/
├── backend/
│   ├── main.py                  # FastAPI app + WebSocket pipeline
│   ├── config.py                # All settings via env vars
│   ├── requirements.txt
│   ├── .env                     # Local configuration
│   ├── stt/
│   │   └── whisper_engine.py    # faster-whisper STT
│   ├── llm/
│   │   └── llm_engine.py        # llama.cpp SSE streaming client
│   ├── tts/
│   │   └── kokoro_engine.py     # Kokoro sentence TTS
│   ├── utils/
│   │   └── audio.py             # PCM conversion + sentence splitting
│   └── models/
│       └── EduMentor-Qwen3-Q6_K.gguf  # ← place your model here
│
├── frontend/
│   ├── public/
│   │   └── audio-processor.js   # AudioWorklet (mic PCM → WebSocket)
│   └── src/
│       ├── hooks/
│       │   └── useVoicePipeline.js  # Core WebSocket + audio hook
│       ├── components/
│       │   ├── VoiceButton.jsx      # Animated mic button
│       │   ├── TranscriptPanel.jsx  # Conversation bubbles
│       │   └── StatusBar.jsx        # Connection indicator
│       ├── App.jsx
│       └── App.css
│
├── run_llm_server.bat           # Start llama.cpp (Windows)
├── run_llm_server.sh            # Start llama.cpp (Linux/macOS)
└── README.md
```

---

## Troubleshooting

**"Cannot connect to llama.cpp server"**
→ Make sure `run_llm_server.bat` is running and model file exists.

**Kokoro download fails**
→ Check your internet connection; Kokoro downloads weights from HuggingFace on first run.

**Microphone not detected**
→ Allow microphone access in your browser. Use HTTPS or `localhost` (both are allowed).

**Audio cuts out / gaps**
→ This is the AudioBuffer queue filling up. If sentences are very short, increase `MIN_TTS_CHARS` in `backend/utils/audio.py`.

**Out of GPU memory**
→ Reduce `-ngl` in `run_llm_server.bat` (e.g., `-ngl 20`) or use a smaller GGUF quantization.

---

## License

MIT — local use, no cloud APIs, fully private.
