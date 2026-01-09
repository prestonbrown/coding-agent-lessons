#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Tests for TUI State dashboard functionality.

These tests verify the State tab shows:
- Lessons section with counts and top lessons
- Handoffs section with stats and active list
- Age statistics (oldest, newest, average, stale count)
- Decay state information
"""

import pytest
from datetime import date, timedelta
from pathlib import Path

pytest.importorskip("textual")

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

from textual.widgets import Static


# Import app with fallback for installed vs dev paths
try:
    from core.tui.app import RecallMonitorApp
    from core.tui.state_reader import StateReader
except ImportError:
    from .app import RecallMonitorApp
    from .state_reader import StateReader


# --- Fixtures ---


@pytest.fixture
def mock_state_with_data(tmp_path: Path, monkeypatch) -> Path:
    """Create a mock state directory with lessons and a project with handoffs."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Create debug.log
    (state_dir / "debug.log").write_text("")

    # Create system lessons
    lessons_content = """# LESSONS.md

### [S001] Always run tests
- **Level**: system
- **Category**: pattern
- **Uses**: 45 | **Velocity**: 2.5

Check tests before committing changes.

### [S002] Use conventional commits
- **Level**: system
- **Category**: pattern
- **Uses**: 30 | **Velocity**: 1.8

Format: type(scope): description
"""
    (state_dir / "LESSONS.md").write_text(lessons_content)

    # Create decay state
    (state_dir / "decay_state").write_text("2026-01-07")

    # Create project directory with handoffs
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    recall_dir = project_dir / ".claude-recall"
    recall_dir.mkdir()

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    two_weeks_ago = (date.today() - timedelta(days=14)).isoformat()

    # Create project lessons
    project_lessons = f"""# LESSONS.md

### [L001] Project-specific pattern
- **Level**: project
- **Category**: pattern
- **Uses**: 10 | **Velocity**: 1.0

A local lesson.
"""
    (recall_dir / "LESSONS.md").write_text(project_lessons)

    # Create handoffs with varying ages
    handoffs_content = f"""# HANDOFFS.md

### [hf-active01] Active Task One
- **Status**: in_progress | **Phase**: implementing | **Agent**: user
- **Created**: {yesterday} | **Updated**: {today}

**Description**: Working on feature A.

**Tried** (1 steps):
  1. [success] Initial setup

**Next**:
  - Continue implementation

**Checkpoint**: 50% complete

### [hf-blocked1] Blocked Task
- **Status**: blocked | **Phase**: research | **Agent**: explore
- **Created**: {week_ago} | **Updated**: {yesterday}

**Description**: Waiting for resources.

**Checkpoint**: Blocked on dependencies

### [hf-stale001] Stale Task
- **Status**: in_progress | **Phase**: planning | **Agent**: user
- **Created**: {two_weeks_ago} | **Updated**: {two_weeks_ago}

**Description**: Old task that needs attention.

**Checkpoint**: Stale

### [hf-done0001] Completed Task
- **Status**: completed | **Phase**: review | **Agent**: general-purpose
- **Created**: {week_ago} | **Updated**: {yesterday}

**Description**: Done.
"""
    (recall_dir / "HANDOFFS.md").write_text(handoffs_content)

    monkeypatch.setenv("CLAUDE_RECALL_STATE", str(state_dir))
    monkeypatch.setenv("PROJECT_DIR", str(project_dir))
    return state_dir


# --- Tests for State Tab Content ---


class TestStateTabLessons:
    """Tests for lessons section in State tab."""

    @pytest.mark.asyncio
    async def test_state_tab_shows_lessons_section(self, mock_state_with_data):
        """State tab should display a Lessons section."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f3")  # Switch to State tab
            await pilot.pause()

            state_widget = app.query_one("#state-overview", Static)
            content = str(state_widget.render())

            assert "Lessons" in content, (
                f"State tab should show 'Lessons' section. Got: {content[:200]}..."
            )

    @pytest.mark.asyncio
    async def test_state_tab_shows_lesson_counts(self, mock_state_with_data):
        """State tab should display lesson counts."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f3")
            await pilot.pause()

            state_widget = app.query_one("#state-overview", Static)
            content = str(state_widget.render())

            assert "System" in content, f"Should show system count. Got: {content[:300]}..."
            assert "Project" in content, f"Should show project count. Got: {content[:300]}..."


class TestStateTabHandoffs:
    """Tests for handoffs section in State tab."""

    @pytest.mark.asyncio
    async def test_state_tab_shows_handoffs_section(self, mock_state_with_data):
        """State tab should display a Handoffs section."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f3")
            await pilot.pause()

            state_widget = app.query_one("#state-overview", Static)
            content = str(state_widget.render())

            assert "Handoffs" in content, (
                f"State tab should show 'Handoffs' section. Got: {content[:200]}..."
            )

    @pytest.mark.asyncio
    async def test_state_tab_shows_active_count(self, mock_state_with_data):
        """State tab should show count of active handoffs."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f3")
            await pilot.pause()

            state_widget = app.query_one("#state-overview", Static)
            content = str(state_widget.render())

            assert "Active" in content, (
                f"State tab should show 'Active' handoff count. Got: {content[:300]}..."
            )

    @pytest.mark.asyncio
    async def test_state_tab_shows_active_handoffs(self, mock_state_with_data):
        """State tab should list active handoffs."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f3")
            await pilot.pause()

            state_widget = app.query_one("#state-overview", Static)
            content = str(state_widget.render())

            # Should show handoff IDs
            assert "hf-" in content, (
                f"State tab should show handoff IDs. Got: {content[:400]}..."
            )


class TestStateTabDecay:
    """Tests for decay info in State tab."""

    @pytest.mark.asyncio
    async def test_state_tab_shows_decay_section(self, mock_state_with_data):
        """State tab should display Decay State section."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f3")
            await pilot.pause()

            state_widget = app.query_one("#state-overview", Static)
            content = str(state_widget.render())

            assert "Decay" in content, (
                f"State tab should show 'Decay' section. Got: {content[:200]}..."
            )


class TestHandoffStats:
    """Tests for handoff statistics computation."""

    def test_get_handoff_stats_returns_expected_keys(self, mock_state_with_data, tmp_path):
        """get_handoff_stats should return dict with expected keys."""
        state_dir = tmp_path / "state"
        reader = StateReader(state_dir=state_dir)

        handoffs = reader.get_handoffs(tmp_path / "test-project")
        stats = reader.get_handoff_stats(handoffs)

        expected_keys = [
            "total_count", "active_count", "blocked_count",
            "stale_count", "by_status", "by_phase", "age_stats"
        ]
        for key in expected_keys:
            assert key in stats, f"Stats should have '{key}' key"

    def test_get_handoff_stats_counts_active(self, mock_state_with_data, tmp_path):
        """get_handoff_stats should count active handoffs correctly."""
        state_dir = tmp_path / "state"
        reader = StateReader(state_dir=state_dir)

        handoffs = reader.get_handoffs(tmp_path / "test-project")
        stats = reader.get_handoff_stats(handoffs)

        # 3 active (in_progress, blocked, in_progress), 1 completed
        assert stats["active_count"] == 3, (
            f"Expected 3 active handoffs, got {stats['active_count']}"
        )

    def test_get_handoff_stats_counts_blocked(self, mock_state_with_data, tmp_path):
        """get_handoff_stats should count blocked handoffs."""
        state_dir = tmp_path / "state"
        reader = StateReader(state_dir=state_dir)

        handoffs = reader.get_handoffs(tmp_path / "test-project")
        stats = reader.get_handoff_stats(handoffs)

        assert stats["blocked_count"] == 1, (
            f"Expected 1 blocked handoff, got {stats['blocked_count']}"
        )

    def test_get_handoff_stats_age_stats(self, mock_state_with_data, tmp_path):
        """get_handoff_stats should compute age statistics."""
        state_dir = tmp_path / "state"
        reader = StateReader(state_dir=state_dir)

        handoffs = reader.get_handoffs(tmp_path / "test-project")
        stats = reader.get_handoff_stats(handoffs)

        age_stats = stats["age_stats"]
        assert "min_age_days" in age_stats
        assert "max_age_days" in age_stats
        assert "avg_age_days" in age_stats

        # Oldest is 14 days (two_weeks_ago), newest is 1 day (yesterday)
        assert age_stats["max_age_days"] == 14, (
            f"Expected max age 14 days, got {age_stats['max_age_days']}"
        )
        assert age_stats["min_age_days"] == 1, (
            f"Expected min age 1 day, got {age_stats['min_age_days']}"
        )
