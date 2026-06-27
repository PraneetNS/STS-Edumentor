# EduMentor Voice — Security Threat Model

This document records the OWASP LLM Top 10 threat model for EduMentor Voice,
the mitigations in place, and the pre-launch security gate that must pass before
any production deployment.

---

## Attack Surface

EduMentor Voice accepts input from three sources:
1. **Student microphone** — PCM audio transcribed by faster-whisper (STT)
2. **WebSocket text frames** — student_id, session_id, and transcribed text
3. **RAG retrieval** — documents returned by the ChromaDB backend

Any of these three paths can carry malicious input. The security pipeline
must intercept all three before they influence the LLM.

---

## OWASP LLM Top 10 Coverage

| ID | Category | Mitigation | Status |
|---|---|---|---|
| LLM01 | Prompt Injection | `sanitize_rag_content()` two-stage pipeline; hardened RAG context wrapper in `prompt_builder.py`; `_PROMPT_INJECTION_CHECKER` on all live input | ✅ Implemented |
| LLM02 | Sensitive Information Disclosure | `redact_pii()` on all output; no student data cross-leakage via session isolation | ✅ Implemented |
| LLM03 | Supply Chain Risks | `verify_requirements_pinned()` at startup; all deps pinned to `==`; `pip-audit` in deployment checklist | ✅ Implemented |
| LLM04 | Data and Model Poisoning | `verify_model_integrity()` SHA256 check before any model loads; `EXPECTED_HASHES` dict for release pinning | ✅ Implemented |
| LLM05 | Improper Output Handling | All LLM output passes `check_output()` before being yielded to the WebSocket | ✅ Implemented |
| LLM06 | Excessive Agency | Model has no tool-use or function-calling capability; no code execution path | ✅ By design |
| LLM07 | System Prompt Leakage | `ROLEPLAY_JAILBREAK_PATTERNS` (input); `check_output_for_system_leak()` (output); identity redirect response | ✅ Implemented |
| LLM08 | Excessive Permissions / Session Isolation | `AccessControl.verify_session_ownership()` as Step 0; in-memory fallback (not permissive); `scope_chromadb_query()` mandatory filter | ✅ Implemented |
| LLM09 | Misinformation | `check_hedging()` detects low-confidence hedging in output; logged for review | ✅ Implemented |
| LLM10 | Unbounded Consumption | `RateLimiter`, `TokenBudget`, `CircuitBreaker`, `TTSQuota` in pipeline; violation tracking with strict-mode escalation | ✅ Implemented |

---

## Pipeline Security Order

Every request through `AgentController.stream()` processes in this order:

```
Step 0:  AccessControl.verify_session_ownership()      — LLM08
Step 1:  RateLimiter.check_rate_limit()                — LLM10
Step 2:  TokenBudget.check_daily_budget()              — LLM10
Step 3:  SafetyGuard.check_input()                     — LLM01, LLM07
         ├── _PROMPT_INJECTION_CHECKER
         ├── _JAILBREAK_CHECKER
         ├── _ROLEPLAY_JAILBREAK_CHECKER                (LLM07 new)
         └── ... (10 total checker categories)
Step 4:  IntentClassifier.classify()
Step 5:  KnowledgeRouter.retrieve()
         └── sanitize_rag_content()                    — LLM01 new
Step 6:  PromptBuilder.build() with hardened RAG wrapper — LLM01 new
Step 7:  LLMEngine.stream()
Step 8:  check_output()                                — LLM05
Step 9:  check_hedging()                               — LLM09
Step 9b: check_output_for_system_leak()                — LLM07 new
Step 10: redact_pii()                                  — LLM02
```

---

## Deployment Checklist (Pre-Launch Gate)

Before any production deployment, the following must all pass:

### 1. Tier 1 unit tests (CI, runs on every PR)
```bash
pytest tests/ -m "not integration" -v
# Must show 0 failures
```

### 2. Tier 2 integration tests (pre-launch only, requires live staging)
```bash
pytest tests/test_adversarial_owasp.py -m integration -v
# Must show 0 failures against the live staging server
```

### 3. Supply chain audit
```bash
pip install pip-audit
pip-audit -r backend/requirements.txt
# Must show 0 known vulnerabilities
```

### 4. Model file hash pinning
```bash
python -c "
import hashlib, sys
sha256 = hashlib.sha256()
with open(sys.argv[1], 'rb') as f:
    for chunk in iter(lambda: f.read(8192), b''):
        sha256.update(chunk)
print('sha256:' + sha256.hexdigest())
" path/to/EduMentor-Qwen3-Q6_K.gguf
```
Update `EXPECTED_HASHES` in `backend/agent/integrity_check.py` with the result.
Repeat for `kokoro-v1_0.pth`.

---

## Known Limitations and Future Work

- **In-memory session map**: `_session_owner_map` in `access_control.py` is
  process-local. In a multi-worker deployment (e.g., `uvicorn --workers 4`),
  sessions registered in worker A are not visible to worker B. Replace with
  Redis SETNX for horizontal scaling.

- **Base64 and leetspeak injection**: The current injection scanner relies on
  pattern matching against the decoded text. A sufficiently obfuscated payload
  that the safety guard does not normalise before checking may slip through
  at the input stage. The output-stage `check_output_for_system_leak()` provides
  a second line of defence.

- **Novel jailbreak techniques**: The adversarial test suite covers documented
  OWASP LLM Top 10 attack patterns as of this release. New jailbreak techniques
  published after this date are not covered. Expand the test suite when new
  techniques are documented.

- **EXPECTED_HASHES**: All entries are empty strings until model hashes are
  computed and pinned at release. Until hashes are pinned, `verify_model_integrity()`
  logs a WARNING but does not abort startup.
