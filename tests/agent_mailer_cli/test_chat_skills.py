"""Tests for realtime-chat skill scaffolding into agent workdirs."""
from __future__ import annotations

from pathlib import Path

from agent_mailer_cli import team_setup


def test_load_chat_skill_resolves_from_source_tree() -> None:
    for name in team_setup.CHAT_SKILLS:
        text = team_setup._load_chat_skill(name)
        assert text, f"{name} template not found"
        assert f"name: {name}" in text


def test_write_chat_skills_claude_writes_both(tmp_path: Path) -> None:
    team_setup.write_chat_skills(tmp_path, "dev", "claude")
    base = tmp_path / "dev" / ".claude" / "skills"
    for name in team_setup.CHAT_SKILLS:
        skill = base / name / "SKILL.md"
        assert skill.is_file()
        assert f"name: {name}" in skill.read_text(encoding="utf-8")


def test_write_chat_skills_noop_for_codex(tmp_path: Path) -> None:
    team_setup.write_chat_skills(tmp_path, "runner", "codex")
    assert not (tmp_path / "runner" / ".claude" / "skills").exists()
