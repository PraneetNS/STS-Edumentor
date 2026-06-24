# EduMentor Voice 🎓

EduMentor Voice is a fully local, real-time AI voice tutor ("Edi") for programming, computer science, and engineering disciplines (Computer Science, Mechanical, Electrical, Civil, Chemical, and Aerospace). 

The platform runs entirely offline on your local hardware to preserve privacy, using high-performance components: **Whisper STT** for speech recognition, **llama.cpp** for low-latency LLM streaming, a custom **Multi-Agent Orchestration Layer**, and **Kokoro TTS** for realistic, expressive speech synthesis.

```
                  ┌──────────────────────────────────────────────┐
                  │                 Vite React                   │
                  │   - Web Audio mic capture (Int16 @ 16kHz)     │
                  │   - Glowing VoiceOrb & 3D Mascot Avatar      │
                  │   - Waveform Visualizer & Spoken word sync   │
                  └──────┬────────────────────────────────▲──────┘
                         │                                │
        WebSocket Binary │                                │ WebSocket Binary
         Audio PCM Frame │                                │ WAV chunks + Timestamps
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
  │     - 14-Intent Classifier (concept, code help, debugging, quiz, off-topic...)  │
  │     - Audio Emotion Detector (confused, frustrated, bored, happy, confident...)│
  │     - Student Profile Manager (persisted levels, learning topics, weak areas)  │
  │     - Dialogue & Interruption Manager (saves partial speech; generates bridges)│
  │     - RAG Knowledge Router (rule-based document retrieval check)              │
  │     - Database Logger (stores history/logs in PostgreSQL pool)                 │
  │                                                                                │
  │  3. LLM & TTS Synthesis Engines                                                │
  │     - llama.cpp client (streams OpenAI-compatible SSE tokens)                  │
  │     - Real-Time Streaming Parser (decouples visual tags from spoken text)      │
  │     - Kokoro TTS synthesis (American/British english voice parameters)         │
  │     - 3-Queue Pipeline with Backpressure (tts_queue -> audio_queue -> sender)  │
  └────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Key Features

*   **Ultra-Low Latency Pipeline**: Achieves a target response time of **2–4 seconds** for natural conversation flow.
*   **100% Local & Private**: No cloud dependencies or API keys required. Your conversations, audio, database logs, and student profiles remain on your physical machine.
*   **Expressive 3D Mascot Avatar**: Interactive React 3D mascot that reacts in real time to the conversation states (`listening`, `thinking`, `speaking`, `idle`) with lip-sync animation driven by Web Audio API analysers.
*   **Expressive Speech & Dynamic Prosody**: Detects student emotion (frustration, confusion, boredom, etc.) from the audio stream and alters speech parameters (speed, tone, and guidance style) in real time.
*   **Barge-In (Interruption) Handling**: Automatically detects when you speak mid-response, immediately cuts the TTS audio playback, saves the interrupted response snapshot, and transitions smoothly into the next turn with a personalized conversational bridge instruction.
*   **Personalized Student Profile**: Persistently tracks your name, skill level (beginner, intermediate, advanced), active learning topics, and weak areas. Tailors explanation depth and style on the fly.
*   **Rolling Session Summarizer**: Summarizes context logs after every 10 turns and feeds condensed information back to the prompt, preventing context window overflow.
*   **Interactive Visuals**: Renders structured code blocks step-by-step, checklists, roadmaps, and workflows inside clean React components via `<show>` HTML tags while TTS speaks the introductory descriptions.

---

## 📁 Repository Structure

```
EduMentor-Voice/
├── backend/
│   ├── main.py                  # FastAPI server + WebSocket endpoint /ws/voice
│   ├── config.py                # System settings driven by environment variables
│   ├── requirements.txt         # Backend Python packages (Whisper, Torch, Kokoro)
│   ├── .env                     # Local configuration variables
│   │
│   ├── agent/                   # Multi-Agent Orchestration Subsystem
│   │   ├── __init__.py
│   │   ├── controller.py        # Central agent coordinator (Single Entry Point)
│   │   ├── database.py          # PostgreSQL async connection pool & queries (asyncpg)
│   │   ├── dialogue_manager.py  # Assembles dialogue contexts & interruption bridges
│   │   ├── emotion_detector.py  # Text sentiment-based emotion classification
│   │   ├── intent_classifier.py # Classifies user input into 14 intents
│   │   ├── interrupt_manager.py # Handles barge-in state, character limits, & logs
│   │   ├── knowledge_router.py  # Logic gates for RAG retrieval (PDF, Notes, etc.)
│   │   ├── memory_manager.py    # Manages short-term conversation context window
│   │   ├── models.py            # Dataclasses & Enums (Intent, Emotion, State)
│   │   ├── prompt_builder.py    # System prompt builder (tags: speak, show, followup)
│   │   ├── realtime_parser.py   # Token parser that strips tags from spoken streams
│   │   ├── response_planner.py  # Cleans outputs to filter out diagrams from TTS
│   │   ├── safety_guard.py      # Input/Output validation (checks cheating, harm, injections)
│   │   ├── session_summarizer.py# Periodically compresses conversation history
│   │   └── student_profile.py   # Persists & auto-infers student statistics
│   │
│   ├── speech/                  # Low-Level Audio Intelligence Subsystem
│   │   ├── alignment.py         # Estimates word timestamps for visual text highlights
│   │   ├── emotion.py           # Audio pitch/intensity analysis for prosody
│   │   ├── normalizer.py        # Fixes transcript disfluencies and repetitions
│   │   └── stabilizer.py        # Identifies confirmed vs temporary transcription words
│   │
│   ├── stt/
│   │   └── whisper_engine.py    # Local Speech-to-Text via faster-whisper
│   ├── llm/
│   │   └── llm_engine.py        # OpenAI-compatible llama.cpp HTTP client
│   ├── tts/
│   │   └── kokoro_engine.py     # Local Text-to-Speech via Kokoro
│   ├── utils/
│   │   └── audio.py             # PCM conversion utilities and VAD sentence splitters
│   ├── data/                    # JSON data storage (Student Profile, Summaries)
│   ├── logs/                    # Local file logs
│   └── tests/                   # 15+ comprehensive unit test suites
│
├── frontend/
│   ├── public/
│   │   ├── audio-processor.js   # Web Audio API AudioWorklet (mic stream capture)
│   │   └── mascot.png           # EduMentor application mascot logo
│   │
│   ├── src/
│   │   ├── App.jsx              # Landing nav + Chat View wrapper
│   │   ├── index.css            # Custom CSS system (ambient blobs, glassmorphism)
│   │   ├── main.jsx             # React DOM entry point
│   │   │
│   │   ├── components/          # Reusable React components
│   │   │   ├── BirdAvatar.js    # 3D Avatar coordinates mapping
│   │   │   ├── ContextCards.jsx # Side UI statistics for profile metrics
│   │   │   ├── LiveTranscript.jsx # Bottom VAD text stream
│   │   │   ├── MarkdownViewer.jsx # Renders markdown and cleans XML tags
│   │   │   ├── MentorCharacter.jsx # 3D Canvas element animating the avatar
│   │   │   ├── MessageList.jsx  # Bubbles timeline with text/visual segment splits
│   │   │   ├── MicButton.jsx    # Pulsing microphone button
│   │   │   ├── Sidebar.jsx      # Navigation drawer for previous conversation threads
│   │   │   ├── SpeakingText.jsx # Highlight sync container for spoken words
│   │   │   ├── StatusBar.jsx    # Connectivity state dashboard
│   │   │   ├── ToastContainer.jsx # Floating alerts
│   │   │   ├── VoiceOrb.jsx     # Animated main voice controller
│   │   │   └── Waveform.jsx     # Live audio frequency visualizer
│   │   │
│   │   └── hooks/
│   │       ├── useConversationStore.js # Conversation history state store
│   │       └── useVoicePipeline.js     # WebSocket connection, audio queues, mic worklet
│   │
│   ├── package.json
│   ├── tailwind.config.js       # Styling configuration
│   └── vite.config.js
│
├── create_db.py                 # Setup script to create the PostgreSQL database
├── run_llm_server.bat           # Executable script for llama.cpp server (Windows)
├── run_llm_server.sh            # Executable script for llama.cpp server (Bash)
├── run_backend.bat              # Executable script for FastAPI backend (Windows)
├── run_backend.sh               # Executable script for FastAPI backend (Bash)
└── README.md
```

---

## 🛠️ Prerequisites

Ensure you have the following installed on your machine:

| Requirement | Supported Version | Notes |
|---|---|---|
| **Python** | `3.10` or `3.11` | Required. (Kokoro and faster-whisper do not support Python 3.12+). |
| **Node.js** | `18+` | Required for building and running the Vite + React frontend. |
| **PostgreSQL** | `14+` | Required for session persistence and database logging. |
| **llama.cpp** | Latest (`llama-server`) | Compiled with CUDA support if offloading to GPU. |
| **CUDA Toolkit** | `12.1+` (Optional) | Recommended for GPU acceleration of LLM, STT, and VAD. |

---

## 📦 Setup & Installation

### Step 1: Place your GGUF model

1. Download a fine-tuned GGUF model optimized for educational instructions (e.g., `Qwen2.5-Coder` or `Qwen2.5-Math` quantizations).
2. Create the directory `backend/models/`.
3. Copy the GGUF model file and rename it to:
   ```
   backend/models/EduMentor-Qwen3-Q6_K.gguf
   ```

### Step 2: Configure Environment Variables

1. Copy `backend/.env.example` to `backend/.env`.
2. Open `backend/.env` and update the settings (especially database credentials, default voices, and GPU parameters). Example database connection setup:
   ```ini
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=yourpassword
   POSTGRES_DB=edumentor
   POSTGRES_ENABLED=true
   ```

### Step 3: Run Database Setup

EduMentor Voice logs sessions into PostgreSQL. Run the database creation script from the root folder to create the database if it doesn't exist:
```bash
python create_db.py
```

### Step 4: Install Backend Dependencies

1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```
2. Create a Python virtual environment:
   ```bash
   python -m venv .venv310
   ```
3. Activate the virtual environment:
   * **Windows:**
     ```cmd
     .venv310\Scripts\activate
     ```
   * **Linux/macOS:**
     ```bash
     source .venv310/bin/activate
     ```
4. Install PyTorch with GPU support (Highly recommended for CUDA speedup):
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   ```
5. Install the remaining requirements:
   ```bash
   pip install -r requirements.txt
   ```

### Step 5: Install Frontend Dependencies

1. Navigate to the `frontend/` directory:
   ```bash
   cd ../frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```

---
