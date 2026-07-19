# Contributing to EduMentor Voice

Thank you for your interest in contributing! This document explains the workflow, standards, and conventions used in this project.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Branch Strategy](#branch-strategy)
3. [Commit Style](#commit-style)
4. [Code Standards](#code-standards)
5. [Testing](#testing)
6. [Pull Request Process](#pull-request-process)

---

## Getting Started

```bash
# 1. Fork the repository and clone your fork
git clone https://github.com/<your-username>/EduMentor-Voice.git
cd EduMentor-Voice

# 2. Set upstream remote
git remote add upstream https://github.com/PraneetNS/lakshai.git

# 3. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 4. Install backend dependencies
pip install -r backend/requirements.txt

# 5. Install frontend dependencies
cd frontend && npm install && cd ..

# 6. Copy environment template and fill in your settings
cp .env.example .env
```

---

## Contributing Avatar Assets & Animations

If you are proposing new animations, assets, or keyframes for EDI (the bird avatar), place new assets directly under `frontend/public/` and reference them cleanly inside the `MentorCharacter.jsx` component.

---

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, production-ready code |
| `space-deploy` | Hugging Face Spaces cloud deployment |
| `feature/<name>` | New features |
| `fix/<name>` | Bug fixes |
| `docs/<name>` | Documentation-only changes |
| `refactor/<name>` | Internal refactoring with no behaviour change |

Create a branch from `main`:

```bash
git switch main
git pull upstream main
git switch -c feature/my-feature
```

---

## Commit Style

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <short summary>
```

**Types**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`

**Examples**:
```
feat(agent): add multi-turn jailbreak detection window
fix(tts): prevent double-playback on rapid barge-in
docs(readme): update cloud deployment instructions
refactor(metrics): extract named metric helpers
```

- Use the **imperative mood** ("add", "fix", not "added", "fixing").
- Keep the summary under **72 characters**.
- Add a blank line + body for non-trivial changes.

---

## Code Standards

### Python (backend)

- **Formatter**: `black` (line length 100).
- **Linter**: `ruff` with default configuration.
- **Type hints**: required on all public functions.
- **Docstrings**: Google-style for public APIs.
- Import order: stdlib → third-party → local (enforced by `ruff`).

### JavaScript / React (frontend)

- **Formatter**: Prettier with the project's `.prettierrc`.
- **Linter**: ESLint with the project's `eslint.config.js`.
- Prefer named exports; avoid default exports for components.

### General

- Do **not** commit secrets, API keys, or credentials.
- Do **not** commit generated build artefacts (`dist/`, `__pycache__/`).
- Keep PRs focused — one logical change per PR.

---

## Testing

```bash
# Backend unit tests
cd backend
pytest -v

# Run a single test file
pytest tests/test_text_cleaner.py -v
```

All new utility functions should include at least one unit test in `backend/tests/`.

---

## Pull Request Process

1. Ensure all tests pass locally before opening a PR.
2. Fill in the PR template (auto-populated by GitHub).
3. Request review from at least one maintainer.
4. Squash-merge is preferred to keep `main` history clean.
5. Delete your branch after merge.

---

## Code of Conduct

Be kind, respectful, and constructive. We follow the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
