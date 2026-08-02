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

*   **Ultra-Low Latency Pipeline**: Achieves a target response time of **2–4 seconds** for natural English conversation flow, and optimized pipelined streaming for Indic turns.
*   **Multilingual Pipeline (Hindi, Kannada, Marathi)**: Full local speech-to-text, script-based language routing, CTranslate2 NLLB translation, and natural Indic speech synthesis via `indic-parler-tts`.
*   **Pipelined Multilingual Streaming**: Real-time sentence-level streaming that translates and synthesizes sentence-by-sentence concurrently, overlapping TTS synthesis with LLM generation to minimize time-to-first-audio.
*   **100% Local & Private**: No cloud dependencies or API keys required. Your conversations, audio, database logs, and student profiles remain on your physical machine.
*   **Expressive 3D Mascot Avatar**: Interactive React 3D mascot that reacts in real time to the conversation states (`listening`, `thinking`, `speaking`, `idle`) with lip-sync animation driven by Web Audio API analysers. Renders fully transparent without box container boundaries.
*   **Expressive Speech & Dynamic Prosody**: Detects student emotion (frustration, confusion, boredom, etc.) from the audio stream and alters speech parameters (speed, tone, and guidance style) in real time.
*   **Barge-In (Interruption) Handling**: Automatically detects when you speak mid-response, immediately cuts the TTS audio playback, saves the interrupted response snapshot, and transitions smoothly into the next turn with a personalized conversational bridge instruction.
*   **Personalized Student Profile**: Tracks student name, skill level (beginner, intermediate, advanced), active learning topics, and weak areas. Tailors explanation depth and style on the fly.
*   **Rolling Session Summarizer**: Summarizes context logs after every 10 turns and feeds condensed information back to the prompt, preventing context window overflow.
*   **Interactive Visuals**: Renders structured code blocks step-by-step, checklists, roadmaps, and workflows inside clean React components via `<show>` HTML tags while TTS speaks the introductory descriptions.
*   **Automatic Self-Healing Stats**: Automatically reconstructs daily usage and focus stats on-demand from raw historical logs if database gaps are detected, creating missing student records dynamically to preserve constraints.
*   **Bulk Guest-to-User Log Migration**: When a guest registers or logs in, the backend scans the database and moves all past guest session logs and speech corrections to their registered account in bulk, instantly recalculating and updating their lifetime metrics.
*   **Access Control Bypass**: Prevents active guest tabs and cached local-storage conversations from getting locked out after migration by immediately allowing guest session requests when the connection's session ID matches the claimed student ID.
*   **Whisper Repetition loop filter**: Automatically detects and blocks Whisper hallucination loops (e.g. repeated "Hello"s on silence or mic hum) to allow the silence detection timer to trigger naturally.
*   **CPU Thread Optimization & Contention Tuning**: Avoids internal Math-library conflicts (like `libblis: Aborting`) on Windows systems by forcing single-thread execution settings for BLIS, OpenBLAS, OpenMP, and MKL. Additionally exposes configurable CPU thread allocation counts (`WHISPER_CPU_THREADS`, `NLLB_INTRA_THREADS`, `TTS_CPU_THREADS`) to prevent CPU core oversubscription and pipeline thrashing.

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
│   │   ├── access_control.py    # Session isolation (mismatch guard & guest bypass)
│   │   ├── controller.py        # Central agent coordinator (Single Entry Point)
│   │   ├── database.py          # PostgreSQL pool, stats backfiller, & guest migrator
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
│   ├── speech/                  # Low-Level Audio & Speech Intelligence Subsystem
│   │   ├── alignment.py         # Estimates word timestamps for visual text highlights
│   │   ├── emotion.py           # Audio pitch/intensity analysis for prosody
│   │   ├── language_router.py   # Unicode checks & Romanized Indic keyword router
│   │   ├── mms_tts.py           # Local IndicParlerTTS speech synthesis (Hindi, Kannada, Marathi)
│   │   ├── multilingual_pipeline.py # Orchestrates Indic STT, routing, NLLB, and MMS-TTS
│   │   ├── nllb_translator.py   # English <-> Indic translations using CTranslate2
│   │   ├── normalizer.py        # Fixes transcript disfluencies and repetitions
│   │   └── stabilizer.py        # Identifies confirmed vs temporary transcription words
│   │
│   ├── stt/
│   │   └── whisper_engine.py    # Local Speech-to-Text via faster-whisper + repetition checks
│   ├── llm/
│   │   └── llm_engine.py        # OpenAI-compatible llama.cpp HTTP client
│   ├── tts/
│   │   └── kokoro_engine.py     # Local Text-to-Speech via Kokoro
│   ├── request_queue/           # Redis request queue logic (consumer/producer)
│   │   ├── __init__.py
│   │   └── llm_queue.py         # Streams request broker implementation
│   ├── loadtest/                # Redis request queue load test suite
│   │   └── load_test.py         # Load-test harness (Poisson arrivals, chaos, percentiles)
│   ├── utils/
│   │   └── audio.py             # PCM conversion utilities and VAD sentence splitters
│   ├── data/                    # JSON data storage (Student Profile, Summaries)
│   ├── logs/                    # Local file logs
│   └── tests/                   # 15+ comprehensive unit and integration test suites
│       ├── test_multilingual_acceptance.py # Acceptance testing scenario runner
│       └── test_concurrent_load.py         # Simulates concurrent multi-student turns
│
├── cloud/                       # ZeroGPU-backed Gradio UI deployment
│   ├── app.py                   # Gradio web interface entry point
│   ├── cloud_llm_engine.py      # Transformers LLM execution utilizing @spaces.GPU
│   ├── cloud_whisper.py         # Whisper model wrapper for cloud STT
│   └── requirements.txt         # Dependencies for HF Spaces / ZeroGPU
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

## 🌐 Multilingual & Performance Subsystem (Indic Integration)

To support students who express technical programming questions using mixed vernaculars, the pipeline incorporates a local multilingual processing path.

### 1. Unified Translation Bridge Design
The system implements a unified architecture for all Indic languages (**Hindi, Kannada, Marathi**) to optimize latency and output quality:
*   **English Route (Native):** Fully native processing (English input -> English LLM response -> Kokoro English TTS).
*   **Indic Routes (Translation Bridge):** Incoming Indic speech is transcribed, routed, and translated into English for the LLM. The LLM generates the response in English, which is then translated back to the target Indic language for MMS-TTS synthesis.
*   **Benefits:** Unifying Hindi under this bridge achieves a **40% total latency reduction** compared to native Devanagari generation and provides significantly higher grammatical correctness and phrasing quality.

### 2. Script & Lexical Language Router
The system routes incoming speech transcripts dynamically using:
*   **Unicode script checks**: Text containing Kannada characters block-routes to the Kannada path.
*   **Devanagari lexical analysis**: Differentiates Hindi from Marathi (such as checking for the Marathi-specific character `ळ`).
*   **Romanized Indic Fallbacks**: Keywords matching romanized Hindi, Kannada, or Marathi trigger NLLB translation. Includes robust phonetic mappings (e.g. `"enu"`, `"mahansh"`, `"rekharshan"`) to resolve Whisper speech-to-text spelling variations.

### 3. Pipelined Sentence-Level Streaming
To keep response times low, the Indic path overlaps NLLB translation and MMS-TTS synthesis with LLM generation:
*   **Sentence-Boundary Detection**: Analyzes LLM streaming token outputs and immediately dispatches completed sentences to NLLB translator queues.
*   **Length-based Fallback**: If a sentence has no ending punctuation (e.g. missing periods/commas), it triggers a fallback split when the token buffer length reaches `Config.TTS_CHUNK_CHARS`.
*   **Overlapped TTS Synthesis**: The translated sentences are queued for synthesis immediately, meaning speech generation for sentence 1 runs in the background while the LLM is still generating sentence 3.

### 4. CPU Core Contention Prevention
Running multiple neural models concurrently on local CPU cores (Whisper, NLLB, MMS-TTS decoder) can cause CPU starvation, BLIS conflicts, and context thrashing. We prevent this via explicit core partitioning:
*   `WHISPER_CPU_THREADS` (default `4`): Thread limit for Faster-Whisper transcription.
*   `NLLB_INTRA_THREADS` (default `2`): Thread limit for NLLB translation.
*   `TTS_CPU_THREADS` (default `4`): PyTorch thread limit (`torch.set_num_threads`) for Indic synthesis.
*   **Performance Impact**: Eliminating CPU oversubscription reduces total Indic pipeline response latencies by **over 50%** (e.g., Hindi response generation dropped from 149s to 68s). It guarantees stable concurrent sessions under multi-student load without crashing or degrading responsiveness.

