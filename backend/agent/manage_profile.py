#!/usr/bin/env python
"""
EduMentor — Student Profile Management CLI

A developer/admin command-line tool for viewing, editing, exporting, and
resetting student profiles stored in data/student_profile.json.

Usage:
    python -m agent.manage_profile show
    python -m agent.manage_profile reset
    python -m agent.manage_profile set-level <beginner|intermediate|advanced>
    python -m agent.manage_profile add-topic <TopicName>
    python -m agent.manage_profile remove-topic <TopicName>
    python -m agent.manage_profile add-weak-area <area>
    python -m agent.manage_profile remove-weak-area <area>
    python -m agent.manage_profile export --out profile_backup.json
    python -m agent.manage_profile import-profile --file profile_backup.json
    python -m agent.manage_profile stats

Run ``python -m agent.manage_profile --help`` for a full option reference.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from typing import Optional

# ── Path helpers ──────────────────────────────────────────────────────────────

_DEFAULT_PROFILE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "student_profile.json"
)


def _resolve_path(path: Optional[str]) -> str:
    return os.path.abspath(path or _DEFAULT_PROFILE_PATH)


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load(path: str) -> dict:
    """Load and return profile JSON, or empty dict if file not found."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data: dict) -> None:
    """Write profile JSON atomically (write to temp then rename)."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_show(args: argparse.Namespace) -> None:
    path = _resolve_path(args.profile)
    profile = _load(path)
    if not profile:
        print(f"[INFO] No profile found at: {path}")
        return
    print(f"Profile: {path}")
    print(json.dumps(profile, indent=2, ensure_ascii=False))


def cmd_stats(args: argparse.Namespace) -> None:
    path = _resolve_path(args.profile)
    profile = _load(path)
    if not profile:
        print("[INFO] No profile found.")
        return
    name = profile.get("name", "Unknown")
    level = profile.get("level", "unknown")
    topics = profile.get("topics", [])
    weak = profile.get("weak_areas", [])
    sessions = profile.get("session_count", 0)
    print("=" * 48)
    print(f"  EduMentor Student Profile Stats")
    print("=" * 48)
    print(f"  Name            : {name}")
    print(f"  Level           : {level}")
    print(f"  Sessions        : {sessions}")
    print(f"  Active Topics   : {len(topics)}  — {', '.join(topics) if topics else 'none'}")
    print(f"  Weak Areas      : {len(weak)}   — {', '.join(weak) if weak else 'none'}")
    print("=" * 48)


def cmd_reset(args: argparse.Namespace) -> None:
    path = _resolve_path(args.profile)
    if os.path.exists(path) and not args.yes:
        answer = input(f"Reset profile at '{path}'? This cannot be undone. [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return
    _save(path, {})
    print(f"[OK] Profile reset: {path}")


def cmd_set_level(args: argparse.Namespace) -> None:
    valid = {"beginner", "intermediate", "advanced"}
    level = args.level.lower()
    if level not in valid:
        print(f"[ERROR] Invalid level '{args.level}'. Choose: {', '.join(sorted(valid))}")
        sys.exit(1)
    path = _resolve_path(args.profile)
    profile = _load(path)
    profile["level"] = level
    _save(path, profile)
    print(f"[OK] Level set to '{level}'.")


def cmd_add_topic(args: argparse.Namespace) -> None:
    path = _resolve_path(args.profile)
    profile = _load(path)
    topics: list = profile.get("topics", [])
    topic = args.topic.strip()
    if topic in topics:
        print(f"[INFO] Topic '{topic}' is already in the profile.")
        return
    topics.append(topic)
    profile["topics"] = topics
    _save(path, profile)
    print(f"[OK] Topic '{topic}' added.")


def cmd_remove_topic(args: argparse.Namespace) -> None:
    path = _resolve_path(args.profile)
    profile = _load(path)
    topics: list = profile.get("topics", [])
    topic = args.topic.strip()
    if topic not in topics:
        print(f"[INFO] Topic '{topic}' not found in profile.")
        return
    topics.remove(topic)
    profile["topics"] = topics
    _save(path, profile)
    print(f"[OK] Topic '{topic}' removed.")


def cmd_add_weak_area(args: argparse.Namespace) -> None:
    path = _resolve_path(args.profile)
    profile = _load(path)
    areas: list = profile.get("weak_areas", [])
    area = args.area.strip()
    if area in areas:
        print(f"[INFO] Weak area '{area}' already recorded.")
        return
    areas.append(area)
    profile["weak_areas"] = areas
    _save(path, profile)
    print(f"[OK] Weak area '{area}' added.")


def cmd_remove_weak_area(args: argparse.Namespace) -> None:
    path = _resolve_path(args.profile)
    profile = _load(path)
    areas: list = profile.get("weak_areas", [])
    area = args.area.strip()
    if area not in areas:
        print(f"[INFO] Weak area '{area}' not found in profile.")
        return
    areas.remove(area)
    profile["weak_areas"] = areas
    _save(path, profile)
    print(f"[OK] Weak area '{area}' removed.")


def cmd_export(args: argparse.Namespace) -> None:
    path = _resolve_path(args.profile)
    profile = _load(path)
    if not profile:
        print("[INFO] No profile data to export.")
        return
    out = args.out or f"profile_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    print(f"[OK] Profile exported to: {out}")


def cmd_import_profile(args: argparse.Namespace) -> None:
    src = args.file
    if not os.path.exists(src):
        print(f"[ERROR] File not found: {src}")
        sys.exit(1)
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    path = _resolve_path(args.profile)
    if os.path.exists(path) and not args.yes:
        answer = input(f"Overwrite existing profile at '{path}'? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return
    _save(path, data)
    print(f"[OK] Profile imported from '{src}' to '{path}'.")


# ── CLI wiring ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agent.manage_profile",
        description="EduMentor Student Profile Management CLI",
    )
    parser.add_argument(
        "--profile", "-p",
        metavar="PATH",
        default=None,
        help="Path to student_profile.json (defaults to data/student_profile.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # show
    sub.add_parser("show", help="Print the full profile as JSON")

    # stats
    sub.add_parser("stats", help="Print a compact stats summary")

    # reset
    p_reset = sub.add_parser("reset", help="Erase all profile data")
    p_reset.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # set-level
    p_level = sub.add_parser("set-level", help="Set the student's skill level")
    p_level.add_argument("level", choices=["beginner", "intermediate", "advanced"])

    # add-topic / remove-topic
    p_add_t = sub.add_parser("add-topic", help="Add a learning topic")
    p_add_t.add_argument("topic", metavar="TOPIC")
    p_rm_t = sub.add_parser("remove-topic", help="Remove a learning topic")
    p_rm_t.add_argument("topic", metavar="TOPIC")

    # add-weak-area / remove-weak-area
    p_add_w = sub.add_parser("add-weak-area", help="Mark a weak area")
    p_add_w.add_argument("area", metavar="AREA")
    p_rm_w = sub.add_parser("remove-weak-area", help="Remove a weak area")
    p_rm_w.add_argument("area", metavar="AREA")

    # export
    p_exp = sub.add_parser("export", help="Export profile to a JSON file")
    p_exp.add_argument("--out", "-o", metavar="FILE", default=None)

    # import-profile
    p_imp = sub.add_parser("import-profile", help="Import profile from a JSON file")
    p_imp.add_argument("--file", "-f", required=True, metavar="FILE")
    p_imp.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    return parser


_COMMAND_MAP = {
    "show":           cmd_show,
    "stats":          cmd_stats,
    "reset":          cmd_reset,
    "set-level":      cmd_set_level,
    "add-topic":      cmd_add_topic,
    "remove-topic":   cmd_remove_topic,
    "add-weak-area":  cmd_add_weak_area,
    "remove-weak-area": cmd_remove_weak_area,
    "export":         cmd_export,
    "import-profile": cmd_import_profile,
}


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = _COMMAND_MAP.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    handler(args)


if __name__ == "__main__":
    main()
