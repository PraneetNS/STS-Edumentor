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

