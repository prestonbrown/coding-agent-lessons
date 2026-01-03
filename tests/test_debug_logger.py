#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Test suite for debug logger.

Run with: pytest tests/test_debug_logger.py -v
"""

import json
import os
import pytest
from pathlib import Path

from core.debug_logger import (
    DebugLogger,
    get_logger,
    reset_logger,
    _get_debug_level,
    _get_session_id,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_lessons_base(tmp_path: Path) -> Path:
    """Create a temporary lessons base directory."""
    lessons_base = tmp_path / ".config" / "claude-recall"
    lessons_base.mkdir(parents=True)
    return lessons_base


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory for logs."""
    state_dir = tmp_path / ".local" / "state" / "claude-recall"
    state_dir.mkdir(parents=True)
    return state_dir


@pytest.fixture(autouse=True)
def reset_logger_state():
    """Reset the global logger before each test."""
    reset_logger()
    yield
    reset_logger()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Clean up environment variables after each test."""
    monkeypatch.delenv("CLAUDE_RECALL_DEBUG", raising=False)
    monkeypatch.delenv("CLAUDE_RECALL_BASE", raising=False)
    monkeypatch.delenv("CLAUDE_RECALL_STATE", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    # Also clean legacy env vars for backward compat
    monkeypatch.delenv("LESSONS_DEBUG", raising=False)
    monkeypatch.delenv("LESSONS_BASE", raising=False)


# =============================================================================
# Tests: Level Configuration
# =============================================================================


class TestDebugLevel:
    """Test debug level parsing."""

    def test_disabled_by_default(self, monkeypatch):
        """Logger should be disabled when CLAUDE_RECALL_DEBUG is not set."""
        monkeypatch.delenv("CLAUDE_RECALL_DEBUG", raising=False)
        monkeypatch.delenv("LESSONS_DEBUG", raising=False)
        assert _get_debug_level() == 0

    def test_level_0_disabled(self, monkeypatch):
        """Level 0 should disable logging."""
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "0")
        assert _get_debug_level() == 0

    def test_level_1_info(self, monkeypatch):
        """Level 1 should enable info logging."""
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")
        assert _get_debug_level() == 1

    def test_level_2_debug(self, monkeypatch):
        """Level 2 should enable debug logging."""
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "2")
        assert _get_debug_level() == 2

    def test_level_3_trace(self, monkeypatch):
        """Level 3 should enable trace logging."""
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "3")
        assert _get_debug_level() == 3

    def test_truthy_values(self, monkeypatch):
        """Truthy string values should enable level 1."""
        for value in ["true", "True", "TRUE", "yes", "on"]:
            monkeypatch.setenv("CLAUDE_RECALL_DEBUG", value)
            assert _get_debug_level() == 1

    def test_invalid_values(self, monkeypatch):
        """Invalid values should disable logging."""
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "invalid")
        assert _get_debug_level() == 0


# =============================================================================
# Tests: Logger Instance
# =============================================================================


class TestDebugLogger:
    """Test DebugLogger class."""

    def test_enabled_property(self, monkeypatch, temp_state_dir):
        """Enabled property should reflect level."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))

        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "0")
        logger = DebugLogger()
        assert not logger.enabled

        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")
        logger = DebugLogger()
        assert logger.enabled

    def test_level_property(self, monkeypatch, temp_state_dir):
        """Level property should return configured level."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "2")
        logger = DebugLogger()
        assert logger.level == 2

    def test_no_write_when_disabled(self, monkeypatch, temp_state_dir):
        """No log file should be created when disabled."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "0")

        logger = DebugLogger()
        logger.session_start(
            project_root="/test",
            lessons_base="/base",
            total_lessons=5,
            system_count=2,
            project_count=3,
            top_lessons=[],
            total_tokens=100,
        )

        log_file = temp_state_dir / "debug.log"
        assert not log_file.exists()


# =============================================================================
# Tests: JSON Lines Output
# =============================================================================


class TestJsonLinesOutput:
    """Test JSON lines format output."""

    def test_writes_json_lines(self, monkeypatch, temp_state_dir):
        """Should write valid JSON lines to log file."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")

        logger = DebugLogger()
        logger.lesson_added(
            lesson_id="L001",
            level="project",
            category="pattern",
            source="human",
            title_length=10,
            content_length=50,
        )

        log_file = temp_state_dir / "debug.log"
        assert log_file.exists()

        content = log_file.read_text().strip()
        entry = json.loads(content)

        assert entry["event"] == "lesson_added"
        assert entry["lesson_id"] == "L001"
        assert entry["level"] == "info"
        assert "timestamp" in entry
        assert "session_id" in entry
        assert "pid" in entry

    def test_session_start_event(self, monkeypatch, temp_state_dir):
        """Should log session_start with correct fields."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")

        logger = DebugLogger()
        logger.session_start(
            project_root="/test/project",
            lessons_base="/test/base",
            total_lessons=10,
            system_count=3,
            project_count=7,
            top_lessons=[{"id": "L001", "uses": 5}],
            total_tokens=500,
        )

        log_file = temp_state_dir / "debug.log"
        entry = json.loads(log_file.read_text().strip())

        assert entry["event"] == "session_start"
        assert entry["project_root"] == "/test/project"
        assert entry["total_lessons"] == 10
        assert entry["total_tokens"] == 500
        assert len(entry["top_lessons"]) == 1

    def test_citation_event(self, monkeypatch, temp_state_dir):
        """Should log citation with before/after values."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")

        logger = DebugLogger()
        logger.citation(
            lesson_id="L003",
            uses_before=5,
            uses_after=6,
            velocity_before=2.0,
            velocity_after=3.0,
            promotion_ready=False,
        )

        log_file = temp_state_dir / "debug.log"
        entry = json.loads(log_file.read_text().strip())

        assert entry["event"] == "citation"
        assert entry["lesson_id"] == "L003"
        assert entry["uses_before"] == 5
        assert entry["uses_after"] == 6
        assert entry["velocity_before"] == 2.0
        assert entry["velocity_after"] == 3.0
        assert entry["promotion_ready"] is False

    def test_approach_events(self, monkeypatch, temp_state_dir):
        """Should log handoff lifecycle events (backward compat: approach_* aliases)."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")

        logger = DebugLogger()

        # Created event (using backward compat alias)
        logger.approach_created(
            approach_id="A001",
            title="Test approach",
            phase="research",
            agent="user",
        )

        # Change event (using backward compat alias)
        logger.approach_change(
            approach_id="A001",
            action="phase_change",
            old_value="research",
            new_value="implementing",
        )

        # Completed event (using backward compat alias)
        logger.approach_completed(
            approach_id="A001",
            tried_count=3,
            duration_days=5,
        )

        log_file = temp_state_dir / "debug.log"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

        created = json.loads(lines[0])
        # New event name is handoff_created (approach_created is backward compat alias)
        assert created["event"] == "handoff_created"
        assert created["handoff_id"] == "A001"

        changed = json.loads(lines[1])
        assert changed["event"] == "handoff_change"
        assert changed["action"] == "phase_change"

        completed = json.loads(lines[2])
        assert completed["event"] == "handoff_completed"
        assert completed["tried_count"] == 3


# =============================================================================
# Tests: Level Gating
# =============================================================================


class TestLevelGating:
    """Test that events are gated by debug level."""

    def test_info_events_at_level_1(self, monkeypatch, temp_state_dir):
        """Info events should log at level 1."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")

        logger = DebugLogger()
        logger.lesson_added("L001", "project", "pattern", "human", 10, 50)

        log_file = temp_state_dir / "debug.log"
        assert log_file.exists()

    def test_debug_events_not_at_level_1(self, monkeypatch, temp_state_dir):
        """Debug events should not log at level 1."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")

        logger = DebugLogger()
        logger.injection_generated(
            token_budget=1000,
            lessons_included=5,
            lessons_excluded=10,
            included_ids=["L001", "L002"],
        )

        log_file = temp_state_dir / "debug.log"
        # Should not exist because injection_generated is level 2
        assert not log_file.exists()

    def test_debug_events_at_level_2(self, monkeypatch, temp_state_dir):
        """Debug events should log at level 2."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "2")

        logger = DebugLogger()
        logger.injection_generated(
            token_budget=1000,
            lessons_included=5,
            lessons_excluded=10,
            included_ids=["L001", "L002"],
        )

        log_file = temp_state_dir / "debug.log"
        assert log_file.exists()

        entry = json.loads(log_file.read_text().strip())
        assert entry["event"] == "injection_generated"
        assert entry["level"] == "debug"

    def test_trace_events_at_level_3(self, monkeypatch, temp_state_dir):
        """Trace events should log at level 3."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "3")

        logger = DebugLogger()
        with logger.trace_file_io("read", "/test/file.md"):
            pass  # Simulate file operation

        log_file = temp_state_dir / "debug.log"
        assert log_file.exists()

        entry = json.loads(log_file.read_text().strip())
        assert entry["event"] == "file_io"
        assert entry["level"] == "trace"
        assert "duration_ms" in entry


# =============================================================================
# Tests: Session ID
# =============================================================================


class TestSessionId:
    """Test session ID generation."""

    def test_session_id_consistent(self):
        """Session ID should be consistent within a process."""
        id1 = _get_session_id()
        id2 = _get_session_id()
        assert id1 == id2

    def test_session_id_format(self):
        """Session ID should be 12 hex characters."""
        session_id = _get_session_id()
        assert len(session_id) == 12
        assert all(c in "0123456789abcdef" for c in session_id)


# =============================================================================
# Tests: Global Logger
# =============================================================================


class TestGlobalLogger:
    """Test global logger singleton."""

    def test_get_logger_returns_same_instance(self, monkeypatch, temp_state_dir):
        """get_logger should return the same instance."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")

        logger1 = get_logger()
        logger2 = get_logger()
        assert logger1 is logger2

    def test_reset_logger_clears_instance(self, monkeypatch, temp_state_dir):
        """reset_logger should clear the global instance."""
        monkeypatch.setenv("CLAUDE_RECALL_STATE", str(temp_state_dir))
        monkeypatch.setenv("CLAUDE_RECALL_DEBUG", "1")

        logger1 = get_logger()
        reset_logger()
        logger2 = get_logger()
        assert logger1 is not logger2
