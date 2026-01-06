#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Tests for the TUI stats aggregator module."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.tui.log_reader import LogReader
from core.tui.stats import StatsAggregator
from core.tui.models import SystemStats


# --- Fixtures ---


@pytest.fixture
def temp_log_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for log files."""
    return tmp_path


def make_timestamp(hours_ago: int = 0, minutes_ago: int = 0) -> str:
    """Generate an ISO timestamp for N hours/minutes ago."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago, minutes=minutes_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_timestamp_today(offset_minutes: int = 0) -> str:
    """Generate a timestamp guaranteed to be today UTC (at midnight + offset)."""
    today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    dt = today_utc + timedelta(minutes=offset_minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def create_log_file(log_path: Path, events: list) -> None:
    """Create a log file with the given events."""
    lines = [json.dumps(e) for e in events]
    log_path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def log_with_sessions_today(temp_log_dir: Path) -> Path:
    """Create a log file with session_start events from today."""
    log_path = temp_log_dir / "debug.log"
    events = [
        {
            "event": "session_start",
            "level": "info",
            "timestamp": make_timestamp_today(60),  # Today at 01:00 UTC
            "session_id": "sess-1",
            "pid": 1,
            "project": "proj-a",
            "total_lessons": 5,
            "system_count": 2,
            "project_count": 3,
        },
        {
            "event": "session_start",
            "level": "info",
            "timestamp": make_timestamp_today(120),  # Today at 02:00 UTC
            "session_id": "sess-2",
            "pid": 2,
            "project": "proj-b",
            "total_lessons": 10,
            "system_count": 5,
            "project_count": 5,
        },
        {
            "event": "citation",
            "level": "info",
            "timestamp": make_timestamp_today(60),  # Today at 01:00 UTC
            "session_id": "sess-1",
            "pid": 1,
            "project": "proj-a",
            "lesson_id": "L001",
            "uses_before": 3,
            "uses_after": 4,
        },
    ]
    create_log_file(log_path, events)
    return log_path


@pytest.fixture
def log_with_timing_events(temp_log_dir: Path) -> Path:
    """Create a log file with hook timing events."""
    log_path = temp_log_dir / "debug.log"
    events = [
        {
            "event": "hook_end",
            "level": "info",
            "timestamp": make_timestamp(0),
            "session_id": "sess-1",
            "pid": 1,
            "project": "proj-a",
            "hook": "SessionStart",
            "total_ms": 50.0,
        },
        {
            "event": "hook_end",
            "level": "info",
            "timestamp": make_timestamp(0),
            "session_id": "sess-1",
            "pid": 1,
            "project": "proj-a",
            "hook": "SessionStart",
            "total_ms": 100.0,
        },
        {
            "event": "hook_end",
            "level": "info",
            "timestamp": make_timestamp(0),
            "session_id": "sess-1",
            "pid": 1,
            "project": "proj-a",
            "hook": "Stop",
            "total_ms": 30.0,
        },
        {
            "event": "hook_end",
            "level": "info",
            "timestamp": make_timestamp(0),
            "session_id": "sess-1",
            "pid": 1,
            "project": "proj-a",
            "hook": "SessionStart",
            "total_ms": 200.0,
        },
    ]
    create_log_file(log_path, events)
    return log_path


@pytest.fixture
def log_with_errors(temp_log_dir: Path) -> Path:
    """Create a log file with error events."""
    log_path = temp_log_dir / "debug.log"
    events = [
        {
            "event": "error",
            "level": "error",
            "timestamp": make_timestamp(0),
            "session_id": "sess-1",
            "pid": 1,
            "project": "proj-a",
            "op": "parse_lesson",
            "err": "Invalid format",
        },
        {
            "event": "error",
            "level": "error",
            "timestamp": make_timestamp(0),
            "session_id": "sess-1",
            "pid": 1,
            "project": "proj-a",
            "op": "cite",
            "err": "Lesson not found",
        },
        {
            "event": "citation",
            "level": "info",
            "timestamp": make_timestamp(0),
            "session_id": "sess-1",
            "pid": 1,
            "project": "proj-a",
            "lesson_id": "L002",
            "uses_before": 1,
            "uses_after": 2,
        },
    ]
    create_log_file(log_path, events)
    return log_path


# --- Tests for compute ---


class TestComputeBasicStats:
    """Tests for basic stats computation."""

    def test_compute_basic_stats(self, log_with_sessions_today: Path):
        """Compute stats from test events."""
        reader = LogReader(log_path=log_with_sessions_today)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        assert isinstance(stats, SystemStats)
        assert stats.sessions_today == 2
        assert stats.citations_today == 1
        assert stats.log_line_count == 3

    def test_compute_events_by_type(self, log_with_sessions_today: Path):
        """Compute event counts by type."""
        reader = LogReader(log_path=log_with_sessions_today)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        assert stats.events_by_type["session_start"] == 2
        assert stats.events_by_type["citation"] == 1

    def test_compute_events_by_project(self, log_with_sessions_today: Path):
        """Compute event counts by project."""
        reader = LogReader(log_path=log_with_sessions_today)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        assert stats.events_by_project["proj-a"] == 2
        assert stats.events_by_project["proj-b"] == 1


class TestComputeSessionsToday:
    """Tests for counting today's sessions."""

    def test_compute_sessions_today(self, log_with_sessions_today: Path):
        """Count today's sessions."""
        reader = LogReader(log_path=log_with_sessions_today)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        assert stats.sessions_today == 2

    def test_compute_sessions_excludes_old(self, temp_log_dir: Path):
        """Old sessions are not counted in today's count."""
        log_path = temp_log_dir / "debug.log"
        events = [
            {
                "event": "session_start",
                "level": "info",
                "timestamp": make_timestamp(0),  # Today
                "session_id": "sess-1",
                "pid": 1,
                "project": "proj",
            },
            {
                "event": "session_start",
                "level": "info",
                "timestamp": make_timestamp(48),  # 2 days ago
                "session_id": "sess-2",
                "pid": 2,
                "project": "proj",
            },
        ]
        create_log_file(log_path, events)

        reader = LogReader(log_path=log_path)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        assert stats.sessions_today == 1


class TestComputeEmptyEvents:
    """Tests for handling empty event buffer."""

    def test_compute_empty_events(self, temp_log_dir: Path):
        """Handle empty event buffer."""
        log_path = temp_log_dir / "debug.log"
        log_path.write_text("")

        reader = LogReader(log_path=log_path)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        assert stats.sessions_today == 0
        assert stats.citations_today == 0
        assert stats.errors_today == 0
        assert stats.avg_hook_ms == 0.0
        assert stats.p95_hook_ms == 0.0
        assert stats.max_hook_ms == 0.0
        assert stats.log_line_count == 0

    def test_compute_nonexistent_file(self, temp_log_dir: Path):
        """Handle nonexistent log file."""
        log_path = temp_log_dir / "nonexistent.log"

        reader = LogReader(log_path=log_path)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        assert stats.sessions_today == 0
        assert stats.log_line_count == 0


class TestTimingPercentiles:
    """Tests for timing percentile calculations."""

    def test_timing_percentiles(self, log_with_timing_events: Path):
        """Calculate timing percentiles."""
        reader = LogReader(log_path=log_with_timing_events)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        # 4 timing events: 50, 100, 30, 200
        # Avg = 95
        assert stats.avg_hook_ms == 95.0

        # Max = 200
        assert stats.max_hook_ms == 200.0

        # P95 should be close to max for small datasets
        assert stats.p95_hook_ms >= 180.0

    def test_timing_by_hook(self, log_with_timing_events: Path):
        """Group timing data by hook name."""
        reader = LogReader(log_path=log_with_timing_events)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        # SessionStart has 3 events: 50, 100, 200
        assert "SessionStart" in stats.hook_timings
        assert len(stats.hook_timings["SessionStart"]) == 3

        # Stop has 1 event: 30
        assert "Stop" in stats.hook_timings
        assert len(stats.hook_timings["Stop"]) == 1

    def test_get_timing_summary(self, log_with_timing_events: Path):
        """Get timing summary with avg, p95, max per hook."""
        reader = LogReader(log_path=log_with_timing_events)
        stats_agg = StatsAggregator(reader)
        summary = stats_agg.get_timing_summary()

        assert "SessionStart" in summary
        sess_timing = summary["SessionStart"]
        assert sess_timing["count"] == 3
        # Avg of 50, 100, 200 = 116.67
        assert 116 <= sess_timing["avg_ms"] <= 117
        assert sess_timing["max_ms"] == 200.0


class TestComputeErrors:
    """Tests for counting errors."""

    def test_compute_errors_today(self, log_with_errors: Path):
        """Count today's errors."""
        reader = LogReader(log_path=log_with_errors)
        stats_agg = StatsAggregator(reader)
        stats = stats_agg.compute()

        assert stats.errors_today == 2

    def test_get_recent_errors(self, log_with_errors: Path):
        """Get most recent error events."""
        reader = LogReader(log_path=log_with_errors)
        stats_agg = StatsAggregator(reader)
        errors = stats_agg.get_recent_errors(limit=10)

        assert len(errors) == 2
        # Most recent first
        assert errors[0].raw.get("op") == "cite"
        assert errors[1].raw.get("op") == "parse_lesson"


# --- Tests for format_summary ---


class TestFormatSummary:
    """Tests for text summary generation."""

    def test_format_summary(self, log_with_sessions_today: Path):
        """Generate text summary."""
        reader = LogReader(log_path=log_with_sessions_today)
        stats_agg = StatsAggregator(reader)
        summary = stats_agg.format_summary()

        assert "Claude Recall Status" in summary
        assert "Sessions today:" in summary
        assert "Citations:" in summary
        assert "Errors:" in summary
        assert "HEALTH:" in summary

    def test_format_summary_with_project_filter(self, log_with_sessions_today: Path):
        """Generate summary filtered by project."""
        reader = LogReader(log_path=log_with_sessions_today)
        stats_agg = StatsAggregator(reader)
        summary = stats_agg.format_summary(project="proj-a")

        # Summary should be generated without errors
        assert "Claude Recall Status" in summary

    def test_format_summary_health_ok(self, log_with_sessions_today: Path):
        """Summary shows OK health when no errors and fast hooks."""
        reader = LogReader(log_path=log_with_sessions_today)
        stats_agg = StatsAggregator(reader)
        summary = stats_agg.format_summary()

        # No errors, no timing events = OK health
        assert "HEALTH: OK" in summary

    def test_format_summary_health_warning(self, log_with_errors: Path):
        """Summary shows WARNING health when errors present."""
        reader = LogReader(log_path=log_with_errors)
        stats_agg = StatsAggregator(reader)
        summary = stats_agg.format_summary()

        assert "HEALTH: WARNING" in summary


# --- Tests for session/project stats ---


class TestSessionStats:
    """Tests for session-specific statistics."""

    def test_compute_session_stats(self, temp_log_dir: Path):
        """Compute stats for a specific session."""
        log_path = temp_log_dir / "debug.log"
        events = [
            {"event": "session_start", "level": "info", "timestamp": make_timestamp(0), "session_id": "sess-1", "pid": 1, "project": "proj"},
            {"event": "citation", "level": "info", "timestamp": make_timestamp(0), "session_id": "sess-1", "pid": 1, "project": "proj", "lesson_id": "L001"},
            {"event": "citation", "level": "info", "timestamp": make_timestamp(0), "session_id": "sess-1", "pid": 1, "project": "proj", "lesson_id": "L002"},
            {"event": "error", "level": "error", "timestamp": make_timestamp(0), "session_id": "sess-1", "pid": 1, "project": "proj", "op": "test", "err": "oops"},
            {"event": "citation", "level": "info", "timestamp": make_timestamp(0), "session_id": "sess-2", "pid": 2, "project": "proj", "lesson_id": "L001"},
        ]
        create_log_file(log_path, events)

        reader = LogReader(log_path=log_path)
        stats_agg = StatsAggregator(reader)
        sess_stats = stats_agg.compute_session_stats("sess-1")

        assert sess_stats["session_id"] == "sess-1"
        assert sess_stats["event_count"] == 4
        assert sess_stats["citations"] == 2
        assert sess_stats["errors"] == 1
        assert sess_stats["project"] == "proj"

    def test_compute_session_stats_unknown(self, temp_log_dir: Path):
        """Compute stats for unknown session returns empty."""
        log_path = temp_log_dir / "debug.log"
        log_path.write_text("")

        reader = LogReader(log_path=log_path)
        stats_agg = StatsAggregator(reader)
        sess_stats = stats_agg.compute_session_stats("unknown-session")

        assert sess_stats["session_id"] == "unknown-session"
        assert sess_stats["event_count"] == 0
        assert sess_stats["citations"] == 0
        assert sess_stats["errors"] == 0


class TestProjectStats:
    """Tests for project-specific statistics."""

    def test_compute_project_stats(self, temp_log_dir: Path):
        """Compute stats for a specific project."""
        log_path = temp_log_dir / "debug.log"
        events = [
            {"event": "session_start", "level": "info", "timestamp": make_timestamp(0), "session_id": "sess-1", "pid": 1, "project": "my-project"},
            {"event": "citation", "level": "info", "timestamp": make_timestamp(0), "session_id": "sess-1", "pid": 1, "project": "my-project", "lesson_id": "L001"},
            {"event": "session_start", "level": "info", "timestamp": make_timestamp(0), "session_id": "sess-2", "pid": 2, "project": "my-project"},
            {"event": "error", "level": "error", "timestamp": make_timestamp(0), "session_id": "sess-2", "pid": 2, "project": "my-project", "op": "test", "err": "oops"},
            {"event": "citation", "level": "info", "timestamp": make_timestamp(0), "session_id": "sess-3", "pid": 3, "project": "other-project", "lesson_id": "L001"},
        ]
        create_log_file(log_path, events)

        reader = LogReader(log_path=log_path)
        stats_agg = StatsAggregator(reader)
        proj_stats = stats_agg.compute_project_stats("my-project")

        assert proj_stats["project"] == "my-project"
        assert proj_stats["event_count"] == 4
        assert proj_stats["citations"] == 1
        assert proj_stats["errors"] == 1
        assert proj_stats["sessions"] == 2

    def test_compute_project_stats_unknown(self, temp_log_dir: Path):
        """Compute stats for unknown project returns empty."""
        log_path = temp_log_dir / "debug.log"
        log_path.write_text("")

        reader = LogReader(log_path=log_path)
        stats_agg = StatsAggregator(reader)
        proj_stats = stats_agg.compute_project_stats("unknown-project")

        assert proj_stats["project"] == "unknown-project"
        assert proj_stats["event_count"] == 0
        assert proj_stats["sessions"] == 0
