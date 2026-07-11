"""
Unit tests for agent.manage_profile — Student Profile Management CLI.

All tests use a tmp_path fixture so no real student_profile.json is modified.
"""

from __future__ import annotations

import json
import os
import pytest

from agent.manage_profile import (
    _load,
    _save,
    build_parser,
    cmd_show,
    cmd_stats,
    cmd_reset,
    cmd_set_level,
    cmd_add_topic,
    cmd_remove_topic,
    cmd_add_weak_area,
    cmd_remove_weak_area,
    cmd_export,
    cmd_import_profile,
    main,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def profile_path(tmp_path):
    """Return path to a fresh temp profile JSON file."""
    return str(tmp_path / "student_profile.json")


@pytest.fixture()
def sample_profile(profile_path):
    """Write a typical profile and return its path."""
    data = {
        "name": "Alice",
        "level": "intermediate",
        "topics": ["Python", "Algorithms"],
        "weak_areas": ["Recursion"],
        "session_count": 5,
    }
    _save(profile_path, data)
    return profile_path


def make_args(profile: str, **kwargs):
    """Construct a minimal argparse.Namespace."""
    import argparse
    ns = argparse.Namespace(profile=profile, yes=True)
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


# ── _load / _save ─────────────────────────────────────────────────────────────

class TestLoadSave:
    def test_load_missing_file_returns_empty_dict(self, profile_path):
        assert _load(profile_path) == {}

    def test_save_and_load_round_trip(self, profile_path):
        data = {"name": "Bob", "level": "beginner"}
        _save(profile_path, data)
        assert _load(profile_path) == data

    def test_save_creates_parent_directories(self, tmp_path):
        deep = str(tmp_path / "a" / "b" / "c" / "profile.json")
        _save(deep, {"x": 1})
        assert os.path.exists(deep)


# ── cmd_show ──────────────────────────────────────────────────────────────────

class TestCmdShow:
    def test_show_prints_profile(self, sample_profile, capsys):
        cmd_show(make_args(sample_profile))
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "intermediate" in out

    def test_show_empty_profile_prints_info(self, profile_path, capsys):
        cmd_show(make_args(profile_path))
        out = capsys.readouterr().out
        assert "No profile" in out


# ── cmd_stats ─────────────────────────────────────────────────────────────────

class TestCmdStats:
    def test_stats_shows_name_and_level(self, sample_profile, capsys):
        cmd_stats(make_args(sample_profile))
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "intermediate" in out

    def test_stats_shows_topic_count(self, sample_profile, capsys):
        cmd_stats(make_args(sample_profile))
        out = capsys.readouterr().out
        assert "2" in out  # 2 topics

    def test_stats_no_profile_prints_info(self, profile_path, capsys):
        cmd_stats(make_args(profile_path))
        out = capsys.readouterr().out
        assert "No profile" in out


# ── cmd_reset ─────────────────────────────────────────────────────────────────

class TestCmdReset:
    def test_reset_clears_profile(self, sample_profile):
        cmd_reset(make_args(sample_profile))
        assert _load(sample_profile) == {}

    def test_reset_on_missing_file_is_safe(self, profile_path):
        cmd_reset(make_args(profile_path))  # should not raise
        assert _load(profile_path) == {}


# ── cmd_set_level ─────────────────────────────────────────────────────────────

class TestCmdSetLevel:
    def test_set_level_beginner(self, profile_path):
        cmd_set_level(make_args(profile_path, level="beginner"))
        assert _load(profile_path)["level"] == "beginner"

    def test_set_level_advanced(self, profile_path):
        cmd_set_level(make_args(profile_path, level="advanced"))
        assert _load(profile_path)["level"] == "advanced"

    def test_set_level_invalid_exits(self, profile_path):
        with pytest.raises(SystemExit):
            cmd_set_level(make_args(profile_path, level="expert"))

    def test_set_level_preserves_other_fields(self, sample_profile):
        cmd_set_level(make_args(sample_profile, level="beginner"))
        profile = _load(sample_profile)
        assert profile["name"] == "Alice"
        assert profile["level"] == "beginner"


# ── cmd_add_topic / cmd_remove_topic ─────────────────────────────────────────

class TestTopicManagement:
    def test_add_topic_appends(self, sample_profile):
        cmd_add_topic(make_args(sample_profile, topic="Machine Learning"))
        assert "Machine Learning" in _load(sample_profile)["topics"]

    def test_add_topic_duplicate_is_noop(self, sample_profile, capsys):
        cmd_add_topic(make_args(sample_profile, topic="Python"))
        out = capsys.readouterr().out
        assert "already" in out
        assert _load(sample_profile)["topics"].count("Python") == 1

    def test_remove_topic_removes_it(self, sample_profile):
        cmd_remove_topic(make_args(sample_profile, topic="Python"))
        assert "Python" not in _load(sample_profile)["topics"]

    def test_remove_topic_missing_prints_info(self, sample_profile, capsys):
        cmd_remove_topic(make_args(sample_profile, topic="Nonexistent Topic"))
        out = capsys.readouterr().out
        assert "not found" in out

    def test_add_topic_to_profile_with_no_topics_key(self, profile_path):
        _save(profile_path, {"name": "Bob"})
        cmd_add_topic(make_args(profile_path, topic="Java"))
        assert _load(profile_path)["topics"] == ["Java"]


# ── cmd_add_weak_area / cmd_remove_weak_area ─────────────────────────────────

class TestWeakAreaManagement:
    def test_add_weak_area(self, sample_profile):
        cmd_add_weak_area(make_args(sample_profile, area="Dynamic Programming"))
        assert "Dynamic Programming" in _load(sample_profile)["weak_areas"]

    def test_add_duplicate_weak_area_is_noop(self, sample_profile, capsys):
        cmd_add_weak_area(make_args(sample_profile, area="Recursion"))
        out = capsys.readouterr().out
        assert "already" in out

    def test_remove_weak_area(self, sample_profile):
        cmd_remove_weak_area(make_args(sample_profile, area="Recursion"))
        assert "Recursion" not in _load(sample_profile)["weak_areas"]

    def test_remove_missing_weak_area_prints_info(self, sample_profile, capsys):
        cmd_remove_weak_area(make_args(sample_profile, area="Nonexistent"))
        out = capsys.readouterr().out
        assert "not found" in out


# ── cmd_export / cmd_import_profile ──────────────────────────────────────────

class TestExportImport:
    def test_export_creates_json_file(self, sample_profile, tmp_path):
        out_path = str(tmp_path / "exported.json")
        cmd_export(make_args(sample_profile, out=out_path))
        assert os.path.exists(out_path)
        data = json.loads(open(out_path).read())
        assert data["name"] == "Alice"

    def test_export_empty_profile_prints_info(self, profile_path, capsys):
        cmd_export(make_args(profile_path, out=None))
        out = capsys.readouterr().out
        assert "No profile" in out

    def test_import_profile_loads_data(self, profile_path, tmp_path):
        src = str(tmp_path / "src.json")
        _save(src, {"name": "Charlie", "level": "advanced"})
        cmd_import_profile(make_args(profile_path, file=src))
        assert _load(profile_path)["name"] == "Charlie"

    def test_import_profile_missing_file_exits(self, profile_path):
        with pytest.raises(SystemExit):
            cmd_import_profile(make_args(profile_path, file="/nonexistent/path.json"))


# ── CLI main() entry point ────────────────────────────────────────────────────

class TestMainEntryPoint:
    def test_show_via_main(self, sample_profile, capsys):
        main(["--profile", sample_profile, "show"])
        out = capsys.readouterr().out
        assert "Alice" in out

    def test_set_level_via_main(self, sample_profile):
        main(["--profile", sample_profile, "set-level", "beginner"])
        assert _load(sample_profile)["level"] == "beginner"

    def test_add_topic_via_main(self, sample_profile):
        main(["--profile", sample_profile, "add-topic", "Rust"])
        assert "Rust" in _load(sample_profile)["topics"]

    def test_unknown_level_via_main_exits(self, profile_path):
        with pytest.raises(SystemExit):
            main(["--profile", profile_path, "set-level", "guru"])
