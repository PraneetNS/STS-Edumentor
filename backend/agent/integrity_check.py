"""
EduMentor Agent Layer — Model & Supply Chain Integrity (LLM03/LLM04)

Provides startup verification of model file hashes and dependency pin
warnings to defend against:
  - Tampered GGUF or Kokoro weight files (model poisoning)
  - Compromised PyPI packages via unpinned dependency ranges (supply chain)

Design:
  - verify_model_integrity() runs ONCE at startup, before any model is loaded
    into memory. A SHA256 mismatch aborts startup — refusing to run on
    a potentially tampered model is the correct failure mode.

  - EXPECTED_HASHES is intentionally empty (no placeholder strings) until
    you compute and pin real hashes at release time. When a key is absent,
    the check passes with a WARNING — this allows the integrity check to be
    wired into startup before hashes are pinned, without blocking development.

  - verify_requirements_pinned() scans requirements.txt for unpinned
    dependencies (>=, >, ~=, no version specifier). It logs warnings but
    does NOT raise — unpinned deps are a supply-chain risk to document and
    remediate, not a startup-abort condition.

How to compute and pin a hash:
    python -c "
    import hashlib, sys
    sha256 = hashlib.sha256()
    with open(sys.argv[1], 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    print('sha256:' + sha256.hexdigest())
    " path/to/EduMentor-Qwen3-Q6_K.gguf

    Then add the result to EXPECTED_HASHES below.

Pipeline position:
  main.py lifespan() → verify_model_integrity() → LLMEngine() / KokoroEngine()
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import List, Optional

logger = logging.getLogger("edumentor.agent.integrity_check")


# ─────────────────────────────────────────────────────────────────────────────
# Expected file hashes (pin on release)
# ─────────────────────────────────────────────────────────────────────────────
# Format: { "filename_key": "sha256:<hex_digest>" }
#
# HOW TO PIN:
#   1. Download / build the model file once and verify it from a trusted source.
#   2. Run the hash command shown in the module docstring.
#   3. Replace the empty string with "sha256:<64-char hex>".
#   4. Commit the updated hash to the repo and treat it as part of the release.
#
# When a key maps to an empty string or is absent, the check logs a WARNING
# and returns True (allows startup to continue). This is intentional for the
# development phase — flip to a hard abort by changing the logic in
# verify_model_integrity() if you want zero-tolerance in production.

EXPECTED_HASHES: dict[str, str] = {
    "EduMentor-Qwen3-Q6_K.gguf": "",  # TODO: compute and pin before release
    "kokoro-v1_0.pth": "",            # TODO: compute and pin before release
}


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class IntegrityError(RuntimeError):
    """
    Raised when a model file's SHA256 hash does not match the expected value.

    Catching this exception in main.py and continuing startup would silently
    load a potentially tampered model — DO NOT catch and continue.
    Let it propagate to abort the process.
    """
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Model File Integrity Verification
# ─────────────────────────────────────────────────────────────────────────────


def verify_model_integrity(model_path: str, expected_key: str) -> bool:
    """
    Verify a model file's SHA256 hash before loading it into an engine.

    Run once at startup for every model file (GGUF, Kokoro weights).
    Computing SHA256 of a multi-GB file takes a few seconds — acceptable
    one-time startup cost compared to the risk of running a tampered model.

    Args:
        model_path:   Absolute path to the model file.
        expected_key: Key into EXPECTED_HASHES (typically the filename).

    Returns:
        True if the hash matches or no expected hash is pinned yet.

    Raises:
        IntegrityError: If the computed hash does not match the expected hash.
                        Do not catch this — let it abort startup.
        FileNotFoundError: If model_path does not exist. Callers should check
                           path existence before calling if the model is optional.
    """
    expected = EXPECTED_HASHES.get(expected_key, "")

    if not expected:
        logger.warning(
            "[INTEGRITY] No expected hash pinned for %r (key=%r). "
            "Skipping verification — pin this hash before production release. "
            "See module docstring for instructions.",
            os.path.basename(model_path), expected_key
        )
        return True

    if not os.path.isfile(model_path):
        raise FileNotFoundError(
            f"Model file not found for integrity check: {model_path}"
        )

    logger.info(
        "[INTEGRITY] Computing SHA256 for %r ...",
        os.path.basename(model_path)
    )

    sha256 = hashlib.sha256()
    file_size = 0
    try:
        with open(model_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
                file_size += len(chunk)
    except OSError as exc:
        raise IntegrityError(
            f"Failed to read model file for integrity check: {model_path}: {exc}"
        ) from exc

    computed = f"sha256:{sha256.hexdigest()}"
    logger.info(
        "[INTEGRITY] %r: computed=%s size=%d bytes",
        os.path.basename(model_path), computed, file_size
    )

    if computed != expected:
        raise IntegrityError(
            f"Model file hash mismatch for {os.path.basename(model_path)}.\n"
            f"  Expected: {expected}\n"
            f"  Computed: {computed}\n"
            f"Refusing to start — possible tampering or incomplete download."
        )

    logger.info(
        "[INTEGRITY] [OK] Hash verified for %r.",
        os.path.basename(model_path)
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Dependency Pin Verification
# ─────────────────────────────────────────────────────────────────────────────

# Patterns that indicate an unpinned or loosely pinned dependency
_UNPINNED_PATTERNS = re.compile(
    r"^([A-Za-z0-9_\-\.\[]+)\s*"   # package name (optional extras)
    r"(>=|>|~=|!=|$)",              # unpinned specifier or no specifier at all
    re.MULTILINE
)


def verify_requirements_pinned(requirements_path: str) -> List[str]:
    """
    Scan requirements.txt for unpinned or loosely pinned dependencies.

    Unpinned deps (>=, >, ~=, or no version) are a supply-chain risk: a
    compromised PyPI package release could be automatically installed on the
    next deployment. This function logs each warning and returns the list —
    it does NOT raise.

    Args:
        requirements_path: Path to requirements.txt.

    Returns:
        List of warning strings for unpinned dependencies (empty if all pinned).
    """
    if not os.path.isfile(requirements_path):
        logger.warning(
            "[INTEGRITY] requirements.txt not found at %r. Skipping pin check.",
            requirements_path
        )
        return []

    warnings: List[str] = []
    try:
        with open(requirements_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        logger.error("[INTEGRITY] Failed to read requirements.txt: %s", exc)
        return []

    for line in content.splitlines():
        stripped = line.strip()
        # Skip comments, blank lines, index URL directives, and options
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue

        # Check for loose specifiers
        if ">=" in stripped or stripped.startswith(">") or "~=" in stripped:
            pkg = stripped.split(">=")[0].split(">")[0].split("~=")[0].strip()
            msg = (
                f"[INTEGRITY] Unpinned dependency: {stripped!r} — "
                f"use == for supply-chain safety (e.g., {pkg}==<version>)"
            )
            logger.warning(msg)
            warnings.append(msg)
        elif "==" not in stripped and "!=" not in stripped:
            # No version specifier at all (package name only)
            pkg = stripped.split("[")[0].strip()
            if pkg and re.match(r"^[A-Za-z0-9_\-\.]+$", pkg):
                msg = (
                    f"[INTEGRITY] No version specifier for: {stripped!r} — "
                    f"pin to an exact version for supply-chain safety."
                )
                logger.warning(msg)
                warnings.append(msg)

    if not warnings:
        logger.info("[INTEGRITY] [OK] All requirements.txt entries appear pinned.")
    else:
        logger.warning(
            "[INTEGRITY] %d unpinned dependencies found in requirements.txt. "
            "Run 'pip-audit' and pin exact versions before production deploy.",
            len(warnings)
        )

    return warnings
