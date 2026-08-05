# EduMentor Voice 🎓

EduMentor Voice is a fully local, real-time AI voice tutor (**Edi**) for programming, computer science, and engineering disciplines (Computer Science, Mechanical, Electrical, Civil, Chemical, and Aerospace).

The platform runs entirely on your local hardware to preserve privacy — no cloud LLM API keys required. It uses **Whisper STT** for speech recognition, **llama.cpp** for low-latency LLM streaming, a custom **Multi-Agent Orchestration Layer**, and **Kokoro TTS** for natural speech synthesis.

```
                  ┌──────────────────────────────────────────────┐
                  │                 Vite React                   │
                  │   - Web Audio mic capture (Int16 @ 16kHz)     │
                  │   - VoiceOrb, 3D Mascot & live transcript     │
                  │   - Clean message display + follow-up chips   │
                  └──────┬────────────────────────────────▲──────┘
                         │                                │
         WebSocket Binary │                                │ WAV chunks + timestamps
          Audio PCM Frame │                                │ JSON events (text, followup)
                          ▼                                │
  ┌───────────────────────────────────────────────────────┴────────────────────────┐
  │                           FastAPI /ws/voice Pipeline                           │
  │                                                                                │
  │  1. STT Subsystem                                                              │
  │     - Silero VAD (Voice Activity Detection & auto-silence triggering)          │
  │     - Transcript Stabilizer & Normalizer                                       │
  │     - faster-whisper STT (transcribes PCM float32 arrays)                      │
  │                                                                                │
  │  2. EduMentor Agent Layer                                                      │
  │     - PII & Prompt Injection Safety Guardrails                                 │
  │     - 14-Intent Classifier (concept, code help, debugging, quiz, off-topic…)   │
  │     - Audio Emotion Detector (confused, frustrated, bored, happy, confident…)  │
  │     - Student Profile Manager (levels, topics, weak areas)                     │
  │     - Dialogue & Interruption Manager (barge-in bridges)                     │
  │     - RAG Knowledge Router (document retrieval check)                          │
  │     - Database Logger (PostgreSQL session history)                             │
  │                                                                                │
  │  3. LLM & TTS Synthesis Engines                                                │
  │     - llama.cpp client (OpenAI-compatible SSE token stream)                    │
  │     - Real-Time Streaming Parser (speak / show / followup decoupling)          │
  │     - Kokoro TTS (English) + optional Indic MMS-TTS path                       │
  │     - 3-Queue Pipeline with Backpressure (tts_queue → audio_queue → sender)    │
  └────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Key Features

* **Ultra-Low Latency Pipeline**: Target **2–4 seconds** for natural English conversation; pipelined sentence-level streaming for Indic languages.
* **Multilingual Support (Hindi, Kannada, Marathi)**: Local STT routing, NLLB translation bridge, and Meta MMS-TTS synthesis with overlapped streaming.
* **100% Local & Private**: No cloud LLM dependencies. Conversations, audio, and profiles stay on your machine.
* **Structured Response Format**: Edi responds using `<speak>`, `<show>`, and `<followup>` tags so spoken text, visual blocks, and follow-up questions are handled separately.
* **Always-On Follow-Up Questions**: Every assistant turn ends with exactly one context-specific follow-up question. It is shown as a clickable **Suggested Followup** chip below the message — tap it to ask that question instantly.
* **Clean Chat Display**: Raw LLM markup (XML tags, JSON blobs like `{"speech":…,"follow_up":…}`) is stripped before anything reaches the UI. Only the readable answer text is shown.
* **Thinking Indicator**: While Edi generates a response, the chat shows a horizontal **Thinking ● ● ●** animation instead of a blinking cursor.
* **Readable Line Wrapping**: Assistant and user messages wrap to a new line every **12 words** for easier reading in the chat bubble.
* **Rich Visual Blocks**: Code, roadmaps, workflows, tables, checklists, and Mermaid diagrams render in dedicated display panels via `<show>` tags.
* **Expressive 3D Mascot Avatar**: Reacts to `listening`, `thinking`, `speaking`, and `idle` states with lip-sync driven by Web Audio analysers.
* **Barge-In (Interruption) Handling**: Speaking mid-response cuts TTS, saves partial state, and transitions smoothly into the next turn.
* **Personalized Student Profile**: Tracks skill level, topics, and weak areas to tailor explanation depth.
* **Rolling Session Summarizer**: Compresses context after every 10 turns to prevent context window overflow.
* **Whisper Repetition Filter**: Blocks hallucination loops on silence or mic hum.
* **CPU Thread Optimization**: Configurable thread limits for Whisper, NLLB, and TTS to prevent core oversubscription on Windows/Linux.

---

## 💬 Response Format & Follow-Up Questions

Edi is instructed to structure every reply using three tag types:

| Tag | Purpose | Shown in chat | Spoken by TTS |
|-----|---------|---------------|---------------|
| `<speak>…</speak>` | Main explanation | ✅ Yes | ✅ Yes |
| `<show type="…">…</show>` | Code, tables, diagrams | ✅ Yes (visual panel) | ❌ No (intro only) |
| `<followup>…</followup>` | One short follow-up question | ✅ Yes (chip below bubble) | ✅ Yes |

**Follow-up rule (absolute):** Every response must end with exactly one `<followup>` question — even after code blocks, greetings, or garbled input. If the model emits JSON instead of tags, the backend parser converts payloads like:

```json
{"speech": "…", "display": null, "follow_up": "What would you like to explore next?"}
```

into the correct tag format before streaming to the client.

---

## 🖥️ Frontend Display Pipeline

| Module | Role |
|--------|------|
| `sanitizeAssistantText.js` | Strips JSON wrappers, XML tags, and metadata before display |
| `formatMessageText.js` | Wraps plain text every 12 words for readable line breaks |
| `MarkdownViewer.jsx` | Renders cleaned markdown + visual content |
| `ThinkingIndicator.jsx` | Horizontal "Thinking" + animated dots while generating |
| `MessageList.jsx` | Chat bubbles, visual strategy panels, follow-up chips |
| `useVoicePipeline.js` | WebSocket events, audio queue, sanitizes text on every delta |

---

## 📁 Repository Structure

```
EduMentor-Voice/
├── backend/
│   ├── main.py                  # FastAPI server + WebSocket /ws/voice
│   ├── config.py                # Settings driven by environment variables
│   ├── requirements.txt
│   ├── agent/                   # Multi-Agent Orchestration
│   │   ├── controller.py        # Central agent coordinator
│   │   ├── prompt_builder.py    # System prompts (speak / show / followup rules)
│   │   ├── realtime_parser.py   # Token parser; JSON → tag conversion
│   │   ├── response_planner.py  # TTS-friendly text cleaning
│   │   └── …                    # intent, memory, safety, profile, etc.
│   ├── speech/                  # Audio intelligence (alignment, emotion, Indic)
│   ├── stt/whisper_engine.py
│   ├── llm/llm_engine.py
│   ├── tts/kokoro_engine.py
│   └── tests/                   # Unit & integration test suites
│
├── frontend/
│   ├── public/audio-processor.js  # AudioWorklet mic capture
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── MarkdownViewer.jsx
│       │   ├── MessageList.jsx
│       │   ├── ThinkingIndicator.jsx
│       │   ├── UserMessageText.jsx
│       │   ├── VoiceOrb.jsx
│       │   ├── MascotOwl.jsx
│       │   └── features/chat/components/DisplayPanel/  # Code, Mermaid, etc.
│       ├── hooks/useVoicePipeline.js
│       ├── utils/
│       │   ├── sanitizeAssistantText.js
│       │   ├── formatMessageText.js
│       │   └── visualBlockExtractor.js
│       └── stores/chatStore.js
│
├── cloud/                       # Optional Hugging Face Spaces deployment
├── .env.example                 # Full environment variable reference
├── run_llm_server.bat / .sh
├── run_backend.bat / .sh
└── README.md
```

---

## ⚙️ Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | Tested on 3.11 |
| Node.js 18+ | For the React frontend |
| llama.cpp (`llama-server`) | CUDA build recommended for GPU inference |
| CUDA (optional) | GPU-accelerated Whisper + LLM |
| PostgreSQL (optional) | Session logging and student profiles |

---

## 🛠️ Setup

### 1. Place your GGUF model

```
backend/models/EduMentor-Qwen3-Q6_K.gguf
```

### 2. Configure environment

```bash
cp .env.example backend/.env
# Edit backend/.env — at minimum set LLM_BASE_URL if not using defaults
```

### 3. Install Python dependencies

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
```

> **GPU users:** Install PyTorch with CUDA first, then `pip install -r requirements.txt`.

### 4. Install frontend dependencies

```bash
cd frontend
npm install
```

### 5. (Optional) PostgreSQL

```bash
python create_db.py
# Set POSTGRES_ENABLED=true and DATABASE_URL in backend/.env
```

---

## ▶️ Running the Application

You need **three terminals** running simultaneously.

**Terminal 1 — llama.cpp**
```batch
run_llm_server.bat        # Windows
./run_llm_server.sh       # Linux / macOS
```
Wait for: `llama server listening at http://0.0.0.0:8080`

**Terminal 2 — FastAPI backend**
```batch
run_backend.bat           # Windows
# or:
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Wait for: `All engines ready — accepting connections`

**Terminal 3 — React frontend**
```bash
cd frontend && npm run dev
```
Open **http://localhost:5173**

---

## 🎙️ Using EduMentor Voice

1. Click the **microphone / VoiceOrb** to start recording.
2. **Speak your question** clearly (e.g. *"Explain recursion to me"*).
3. Click again or wait for silence detection to end the turn.
4. Watch the **Thinking** indicator, then the answer streams into the chat bubble.
5. Audio playback begins within a few seconds; word highlights sync when timestamps are available.
6. Tap the **Suggested Followup** chip below any Edi message to ask that question instantly.

---

## 🌐 Multilingual Subsystem (Indic Integration)

For Hindi, Kannada, and Marathi, the pipeline uses a **translation bridge**:

* **English route:** English STT → English LLM → Kokoro English TTS.
* **Indic routes:** Indic STT → NLLB translate to English → LLM → NLLB translate back → MMS-TTS.

**Language routing** uses Unicode script detection, Devanagari lexical analysis (Hindi vs Marathi), and romanized keyword fallbacks for Whisper spelling variations.

**Pipelined streaming** overlaps NLLB translation and MMS-TTS synthesis with LLM generation sentence-by-sentence to minimize time-to-first-audio.

**CPU partitioning** (prevent thrashing):

| Variable | Default | Purpose |
|---|---|---|
| `WHISPER_CPU_THREADS` | `4` | Faster-Whisper thread limit |
| `NLLB_INTRA_THREADS` | `2` | NLLB translation threads |
| `TTS_CPU_THREADS` | `4` | PyTorch threads for Indic TTS |

Set `MULTILINGUAL_ENABLED=false` in `.env` for English-only mode.

---

## 🔌 WebSocket Protocol (`/ws/voice`)

### Client → Server

| Frame | Meaning |
|---|---|
| Binary | Raw PCM Int16 audio @ 16 kHz mono |
| `{"type":"end_of_speech"}` | Trigger STT + LLM + TTS pipeline |
| `{"type":"ping"}` | Keepalive |

### Server → Client

| Frame | Meaning |
|---|---|
| `{"type":"state","state":"LISTENING\|THINKING\|…"}` | Conversation state change |
| `{"type":"live_transcript","text":"…","words":[…]}` | Partial user transcript |
| `{"type":"transcript","text":"…"}` | Final user speech |
| `{"type":"assistant_text_delta","text":"…"}` | Streaming assistant text chunk (display-safe) |
| `{"type":"followup","text":"…"}` | Follow-up question for the UI chip |
| `{"type":"tts_start"}` | Audio playback about to begin |
| Binary | WAV audio chunk (24 kHz PCM) + optional word timestamps |
| `{"type":"assistant_finished"}` | Generation complete (audio may still be playing) |
| `{"type":"done"}` | Turn fully complete |
| `{"type":"interrupt"}` | Barge-in detected |
| `{"type":"error","text":"…"}` | Pipeline error |

Frontend WebSocket URL (override in `frontend/.env`):

```
VITE_WS_URL=ws://localhost:8000/ws/voice
```

---

## 🔧 Configuration

Key variables in `backend/.env` (see `.env.example` for the full list):

| Variable | Default | Description |
|---|---|---|
| `WHISPER_MODEL` | `small.en` | Whisper model size |
| `LLM_BASE_URL` | `http://127.0.0.1:8080` | llama.cpp server URL |
| `LLM_MAX_TOKENS` | `512` | Max response tokens |
| `LLM_TEMPERATURE` | `0.55` | Generation temperature |
| `KOKORO_VOICE` | `af_heart` | TTS voice ID |
| `KOKORO_SPEED` | `1.0` | Speech speed multiplier |
| `AGENT_ENABLED` | `true` | Enable multi-agent orchestration layer |
| `AGENT_SAFETY_ENABLED` | `true` | Input/output safety guardrails |
| `VAD_THRESHOLD` | `0.45` | Silero VAD sensitivity |
| `VAD_SILENCE_TIMEOUT` | `0.5` | Seconds of silence before auto-stop |
| `TTS_CHUNK_CHARS` | `120` | Max chars before TTS sentence flush |
| `MULTILINGUAL_ENABLED` | `true` | Enable Hindi/Kannada/Marathi path |

---

## ⚡ Performance Tuning

| Area | Tip |
|---|---|
| **STT latency** | Use `tiny.en` or `base.en` for fastest transcription |
| **LLM speed** | Increase `-ngl` in `run_llm_server.bat` to offload more layers to GPU |
| **TTS latency** | First sentence flushes aggressively; later sentences overlap with generation |
| **Memory** | Models stay loaded between turns — no reload per query |
| **Context length** | Reduce `-c` in the llama.cpp script if GPU OOM occurs |
| **Indic latency** | Tune `WHISPER_CPU_THREADS`, `NLLB_INTRA_THREADS`, `TTS_CPU_THREADS` separately |

---

## 🧪 Testing

```bash
cd backend
pytest tests/

# Realtime parser (tag + JSON conversion)
python ../test_realtime_parser.py
```

---

## 🩺 Troubleshooting

**"Cannot connect to llama.cpp server"**
→ Ensure `run_llm_server.bat` is running and the GGUF model file exists.

**Raw JSON or XML tags visible in chat**
→ Restart backend and hard-refresh the frontend. Sanitization runs in both the parser and `sanitizeAssistantText.js`.

**Follow-up chip missing**
→ The model must emit a `<followup>` tag (or JSON `follow_up` field). Check `AGENT_ENABLED=true` and review backend logs for parser warnings.

**Kokoro download fails**
→ First run downloads ~300 MB from HuggingFace; check network access.

**Microphone not detected**
→ Allow mic access in the browser; use `localhost` or HTTPS.

**Out of GPU memory**
→ Reduce `-ngl` in the llama.cpp launch script or use a smaller GGUF quantization.

---

## 📄 Related Docs

* [CHANGELOG.md](./CHANGELOG.md) — release history
* [SECURITY.md](./SECURITY.md) — OWASP guardrails and safety architecture
* [.env.example](./.env.example) — complete environment reference

---

## 📜 License

MIT — local use, no cloud APIs required, fully private.
