# Changelog

All notable changes to **EduMentor Voice** are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- `GET /api/sessions` and `GET /api/sessions/heatmap` FastAPI endpoints for historical voice session retrieval and activity heatmap counts.
- `useProfileStats` React custom hook for centralized profile data fetching, caching, and state management.
- `HeatmapCalendar` component for 90-day GitHub-style continuous contribution tracking.
- `SessionSummaryCard` component for detailed voice interaction turn, latency, and token metrics.
- `sanitise_for_tts()` helper in `utils/text_cleaner.py` to strip markdown, code fences, and URLs before TTS synthesis.
- Named metric shortcut instances (`ws_sessions`, `llm_requests`, `llm_errors`, `tts_requests`, `stt_requests`, and latency histograms) in `utils/metrics.py`.
- `max_delay` cap and optional `on_retry` async callback to `async_retry` decorator in `utils/retry.py`.
- TCP WebSocket port probe (`check_ws_port`) and `APP_VERSION` field to health reports in `utils/health.py`.
- `WARN` and `RATE_LIMITED` event constants to `WSEvent` in `constants.py`.
- `DIAGRAM` as an additional `ShowType` alias for Mermaid-rendered diagram blocks.
- Cloud LLM engine (`cloud/cloud_llm_engine.py`) now reads `CLOUD_MODEL_ID` and `CLOUD_MAX_TOKENS` from environment variables, removing hardcoded defaults.
- This `CHANGELOG.md` file.

### Changed
- `utils/metrics.reset()` now emits a `WARNING`-level log entry before clearing all metrics.
- Cloud LLM streaming adapter uses `_MAX_TOKENS` env-derived constant instead of the magic number `250`.

---

## [1.0.0] — Initial Release

### Added
- Real-time voice pipeline: Silero VAD → faster-whisper STT → LLM → Kokoro TTS.
- 14-intent classifier, emotion-aware response adaptation, and barge-in interruption handling.
- Multi-agent orchestration layer: `AgentController`, `MemoryManager`, `SessionSummarizer`, `StudentProfileManager`, `InterruptManager`.
- Structured LLM output tags (`<speak>`, `<show>`, `<followup>`) with React front-end rendering.
- Cloud deployment path via Hugging Face Spaces (ZeroGPU) with Gradio UI.
- PostgreSQL (Neon) session logging and student profile persistence.
- SECURITY.md, README.md, and full repository documentation.

---

[Unreleased]: https://github.com/PraneetNS/lakshai/compare/HEAD...HEAD
