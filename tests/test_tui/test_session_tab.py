#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Tests for TUI Session tab functionality.

These tests verify the Session tab works correctly with TranscriptReader:
- Session list populates from Claude transcript files
- Column sorting works (header clicks trigger sort)
- Session events display shows transcript timeline
- Topic column shows first user prompt
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

pytest.importorskip("textual")

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

from textual.widgets import DataTable, RichLog


# Import app with fallback for installed vs dev paths
try:
    from core.tui.app import RecallMonitorApp, _format_session_time, _format_tokens
    from core.tui.transcript_reader import TranscriptReader, TranscriptSummary
except ImportError:
    from .app import RecallMonitorApp, _format_session_time, _format_tokens
    from .transcript_reader import TranscriptReader, TranscriptSummary


# --- Helper Functions ---


def make_timestamp(seconds_ago: int = 0) -> str:
    """Generate an ISO timestamp for N seconds ago."""
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def create_transcript(
    path: Path,
    first_prompt: str,
    tools: list,
    tokens: int,
    start_time: str,
    end_time: str,
) -> None:
    """Create a mock transcript JSONL file."""
    messages = []

    # User message
    messages.append(
        {
            "type": "user",
            "timestamp": start_time,
            "sessionId": path.stem,
            "message": {"role": "user", "content": first_prompt},
        }
    )

    # Assistant message with tools
    tool_uses = [{"type": "tool_use", "name": t, "input": {}} for t in tools]
    content = tool_uses if tools else [{"type": "text", "text": "Done"}]
    messages.append(
        {
            "type": "assistant",
            "timestamp": end_time,
            "sessionId": path.stem,
            "message": {
                "role": "assistant",
                "usage": {"input_tokens": 100, "output_tokens": tokens},
                "content": content,
            },
        }
    )

    with open(path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")


# --- Fixtures ---


@pytest.fixture
def mock_claude_home(tmp_path: Path, monkeypatch) -> Path:
    """Create a mock ~/.claude directory with transcript files."""
    claude_home = tmp_path / ".claude"
    projects_dir = claude_home / "projects"

    # Create project directory (URL-encoded current working dir)
    # For testing, use a simple project path matching PROJECT_DIR
    project_dir = projects_dir / "-Users-test-code-project-a"
    project_dir.mkdir(parents=True)

    # Session 1: older session
    create_transcript(
        project_dir / "sess-older.jsonl",
        first_prompt="Help me fix something old",
        tools=["Read", "Bash"],
        tokens=1234,
        start_time=make_timestamp(60),
        end_time=make_timestamp(50),
    )

    # Session 2: middle session (no tokens - edge case)
    create_transcript(
        project_dir / "sess-middle.jsonl",
        first_prompt="Middle session task",
        tools=["Edit"],
        tokens=0,
        start_time=make_timestamp(40),
        end_time=make_timestamp(20),
    )

    # Session 3: recent session
    create_transcript(
        project_dir / "sess-recent.jsonl",
        first_prompt="Recent task with many tools",
        tools=["Read", "Grep", "Edit", "Bash"],
        tokens=5000,
        start_time=make_timestamp(10),
        end_time=make_timestamp(5),
    )

    # Session 4: session with very long topic (> 100 chars)
    # This long prompt tests that the full topic is displayed without truncation
    long_topic = (
        "Implement a comprehensive authentication system with OAuth2 support, "
        "including Google and GitHub providers, session management with Redis, "
        "and JWT token refresh mechanisms for the new microservices architecture"
    )
    assert len(long_topic) > 100, f"Long topic should be > 100 chars, got {len(long_topic)}"
    create_transcript(
        project_dir / "sess-long-topic.jsonl",
        first_prompt=long_topic,
        tools=["Read", "Edit"],
        tokens=2500,
        start_time=make_timestamp(30),
        end_time=make_timestamp(25),
    )

    # Monkeypatch to use our mock Claude home and project dir
    monkeypatch.setenv("PROJECT_DIR", "/Users/test/code/project-a")

    # Monkeypatch Path.home() to return our tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    return claude_home


@pytest.fixture
def temp_state_dir(tmp_path: Path, monkeypatch) -> Path:
    """Create temp state dir with empty debug.log for LogReader."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Create minimal debug.log so LogReader doesn't fail
    log_path = state_dir / "debug.log"
    log_path.write_text("")

    monkeypatch.setenv("CLAUDE_RECALL_STATE", str(state_dir))
    return state_dir


# --- Tests for TranscriptReader ---


class TestTranscriptReader:
    """Tests for TranscriptReader reading transcript files."""

    def test_list_sessions_finds_transcripts(self, mock_claude_home: Path):
        """TranscriptReader should find transcript files in project directory."""
        reader = TranscriptReader(claude_home=mock_claude_home)
        sessions = reader.list_sessions("/Users/test/code/project-a")

        assert len(sessions) == 4, (
            f"Expected 4 sessions from transcript files, got {len(sessions)}"
        )

    def test_list_sessions_sorted_by_recency(self, mock_claude_home: Path):
        """Sessions should be sorted by last_activity, most recent first."""
        reader = TranscriptReader(claude_home=mock_claude_home)
        sessions = reader.list_sessions("/Users/test/code/project-a")

        # Recent (5s ago) should be first, older (50s ago) should be last
        assert sessions[0].session_id == "sess-recent", (
            f"Expected sess-recent first (most recent), got {sessions[0].session_id}"
        )
        assert sessions[-1].session_id == "sess-older", (
            f"Expected sess-older last (oldest), got {sessions[-1].session_id}"
        )

    def test_session_summary_extracts_first_prompt(self, mock_claude_home: Path):
        """TranscriptSummary should capture first user message as first_prompt."""
        reader = TranscriptReader(claude_home=mock_claude_home)
        sessions = reader.list_sessions("/Users/test/code/project-a")

        # Find sess-recent
        recent = next(s for s in sessions if s.session_id == "sess-recent")
        assert recent.first_prompt == "Recent task with many tools", (
            f"Expected first_prompt from user message, got '{recent.first_prompt}'"
        )

    def test_session_summary_extracts_tool_breakdown(self, mock_claude_home: Path):
        """TranscriptSummary should count tool usage from assistant messages."""
        reader = TranscriptReader(claude_home=mock_claude_home)
        sessions = reader.list_sessions("/Users/test/code/project-a")

        # Find sess-recent (has 4 tools)
        recent = next(s for s in sessions if s.session_id == "sess-recent")

        total_tools = sum(recent.tool_breakdown.values())
        assert total_tools == 4, (
            f"Expected 4 total tools, got {total_tools}. "
            f"Tool breakdown: {recent.tool_breakdown}"
        )

    def test_session_summary_extracts_tokens(self, mock_claude_home: Path):
        """TranscriptSummary should sum output_tokens from assistant messages."""
        reader = TranscriptReader(claude_home=mock_claude_home)
        sessions = reader.list_sessions("/Users/test/code/project-a")

        # Find sess-recent (5000 tokens)
        recent = next(s for s in sessions if s.session_id == "sess-recent")
        assert recent.total_tokens == 5000, (
            f"Expected 5000 tokens, got {recent.total_tokens}"
        )

        # Find sess-middle (0 tokens)
        middle = next(s for s in sessions if s.session_id == "sess-middle")
        assert middle.total_tokens == 0, (
            f"Expected 0 tokens for middle session, got {middle.total_tokens}"
        )

    def test_load_session_returns_messages(self, mock_claude_home: Path):
        """load_session should return TranscriptMessage list."""
        reader = TranscriptReader(claude_home=mock_claude_home)
        sessions = reader.list_sessions("/Users/test/code/project-a")

        recent = next(s for s in sessions if s.session_id == "sess-recent")
        messages = reader.load_session(recent.path)

        # Should have 2 messages: user and assistant
        assert len(messages) == 2, (
            f"Expected 2 messages (user + assistant), got {len(messages)}"
        )
        assert messages[0].type == "user", "First message should be user"
        assert messages[1].type == "assistant", "Second message should be assistant"

    def test_load_session_extracts_tools(self, mock_claude_home: Path):
        """Assistant messages should have tools_used populated."""
        reader = TranscriptReader(claude_home=mock_claude_home)
        sessions = reader.list_sessions("/Users/test/code/project-a")

        recent = next(s for s in sessions if s.session_id == "sess-recent")
        messages = reader.load_session(recent.path)

        assistant_msg = messages[1]
        assert assistant_msg.tools_used == ["Read", "Grep", "Edit", "Bash"], (
            f"Expected tools from assistant message, got {assistant_msg.tools_used}"
        )


# --- Tests for Display Formatting ---


class TestDisplayFormatting:
    """Tests for session display formatting functions."""

    def test_format_tokens_shows_k_suffix(self):
        """Tokens >= 1000 should display with k suffix."""
        assert _format_tokens(1234) == "1.2k", (
            f"Expected '1.2k' for 1234 tokens, got '{_format_tokens(1234)}'"
        )
        assert _format_tokens(5000) == "5.0k", (
            f"Expected '5.0k' for 5000 tokens, got '{_format_tokens(5000)}'"
        )

    def test_format_tokens_zero_shows_dash(self):
        """Zero tokens should display as '--'."""
        assert _format_tokens(0) == "--", (
            f"Expected '--' for 0 tokens, got '{_format_tokens(0)}'"
        )

    def test_format_tokens_small_shows_number(self):
        """Tokens < 1000 should display as number."""
        assert _format_tokens(500) == "500", (
            f"Expected '500' for 500 tokens, got '{_format_tokens(500)}'"
        )

    def test_format_session_time_distinct(self, mock_claude_home: Path):
        """Start and last times should be different when events are apart."""
        reader = TranscriptReader(claude_home=mock_claude_home)
        sessions = reader.list_sessions("/Users/test/code/project-a")

        older = next(s for s in sessions if s.session_id == "sess-older")

        start_display = _format_session_time(older.start_time)
        last_display = _format_session_time(older.last_activity)

        assert start_display != last_display, (
            f"Start and Last display should differ but both show '{start_display}'. "
            "Session has events 10 seconds apart."
        )


# --- Tests for Session Sorting ---


class TestSessionSorting:
    """Tests for session table sorting functionality."""

    @pytest.mark.asyncio
    async def test_sort_by_tokens_orders_correctly(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Sorting by tokens column puts rows in correct order."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_table = app.query_one("#session-list", DataTable)

            # Should have 4 sessions
            assert session_table.row_count == 4, (
                f"Expected 4 sessions in table, got {session_table.row_count}"
            )

            # Call the internal method to sort by tokens descending
            app._sort_session_table("tokens", reverse=True)
            await pilot.pause()

            # Get sorted order
            sorted_order = [str(row_key.value) for row_key in session_table.rows.keys()]

            # After sorting by tokens descending:
            # sess-recent (5000) > sess-older (1234) > sess-middle (0)
            assert sorted_order[0] == "sess-recent", (
                f"After sorting by tokens desc, expected sess-recent first, "
                f"but got {sorted_order[0]}. Order: {sorted_order}"
            )
            assert sorted_order[-1] == "sess-middle", (
                f"After sorting by tokens desc, expected sess-middle last, "
                f"but got {sorted_order[-1]}. Order: {sorted_order}"
            )

    @pytest.mark.asyncio
    async def test_sort_by_tools_orders_correctly(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Sorting by tools column puts rows in correct order."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_table = app.query_one("#session-list", DataTable)

            # Sort by tools descending
            app._sort_session_table("tools", reverse=True)
            await pilot.pause()

            sorted_order = [str(row_key.value) for row_key in session_table.rows.keys()]

            # Tool counts: sess-recent (4) > sess-older (2) > sess-middle (1)
            assert sorted_order[0] == "sess-recent", (
                f"Expected sess-recent first (4 tools), got {sorted_order[0]}"
            )
            assert sorted_order[-1] == "sess-middle", (
                f"Expected sess-middle last (1 tool), got {sorted_order[-1]}"
            )

    @pytest.mark.asyncio
    async def test_header_click_toggles_sort_direction(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Clicking same header should toggle ascending/descending."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_table = app.query_one("#session-list", DataTable)

            # First sort: ascending (reverse=False)
            app._sort_session_table("tokens", reverse=False)
            await pilot.pause()

            first_order = [str(row_key.value) for row_key in session_table.rows.keys()]

            # Ascending: sess-middle (0) < sess-older (1234) < sess-recent (5000)
            assert first_order[0] == "sess-middle", (
                f"In ascending order, sess-middle should be first, got {first_order[0]}"
            )

            # Second sort: descending (reverse=True)
            app._sort_session_table("tokens", reverse=True)
            await pilot.pause()

            second_order = [str(row_key.value) for row_key in session_table.rows.keys()]

            # Descending: sess-recent (5000) > sess-older (1234) > sess-middle (0)
            assert second_order[0] == "sess-recent", (
                f"In descending order, sess-recent should be first, got {second_order[0]}"
            )

            # Orders should be reversed
            assert first_order != second_order, (
                "Toggling sort direction should change order."
            )


# --- Tests for Session Events Display ---


class TestSessionEvents:
    """Tests for session event display functionality."""

    @pytest.mark.asyncio
    async def test_row_highlight_shows_events(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Arrow key navigation should show transcript in detail panel."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_table = app.query_one("#session-list", DataTable)
            session_events = app.query_one("#session-events", RichLog)

            # Focus the session table
            session_table.focus()
            await pilot.pause()

            # Navigate with arrow keys to trigger highlight event
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("up")
            await pilot.pause()

            # Session events panel should now have content
            event_count = len(session_events.lines)

            assert event_count > 0, (
                f"Session events panel should have transcript entries, "
                f"but has {event_count} lines. "
                "Row highlighting may not be triggering _show_session_events."
            )

    @pytest.mark.asyncio
    async def test_show_session_events_displays_transcript(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """_show_session_events should populate panel with transcript timeline."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_events = app.query_one("#session-events", RichLog)

            # Call _show_session_events directly to show a specific session
            app._show_session_events("sess-older")
            await pilot.pause()

            # Should have content for sess-older
            line_count = len(session_events.lines)

            assert line_count > 0, (
                f"_show_session_events should populate panel with transcript. "
                f"Got {line_count} lines."
            )

            # Verify it shows the correct session's content
            lines_text = str(session_events.lines)
            assert "Help me fix something old" in lines_text, (
                f"Panel should show sess-older's topic. Lines: {lines_text[:200]}..."
            )

    @pytest.mark.asyncio
    async def test_show_session_events_shows_topic(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Session events panel should show the topic (first prompt)."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_events = app.query_one("#session-events", RichLog)

            # Call _show_session_events
            app._show_session_events("sess-recent")
            await pilot.pause()

            # Get the rendered text content
            # RichLog.lines contains the actual text
            lines_text = str(session_events.lines)

            assert "Recent task with many tools" in lines_text, (
                f"Session events should show the topic (first prompt). "
                f"Lines: {lines_text[:200]}..."
            )

    @pytest.mark.asyncio
    async def test_show_session_events_shows_tools(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Session events panel should show tool breakdown."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_events = app.query_one("#session-events", RichLog)

            # Call _show_session_events
            app._show_session_events("sess-recent")
            await pilot.pause()

            # Get the rendered text content
            lines_text = str(session_events.lines)

            # Should show tool names
            assert "Read" in lines_text or "TOOL" in lines_text, (
                f"Session events should show tool usage. "
                f"Lines: {lines_text[:300]}..."
            )


# --- Tests for Session Table Integration ---


class TestSessionTableIntegration:
    """Integration tests for the session table."""

    @pytest.mark.asyncio
    async def test_session_table_shows_correct_data(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Session table displays correct values from transcripts."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_table = app.query_one("#session-list", DataTable)

            # Verify we have 4 sessions
            row_count = session_table.row_count
            assert row_count == 4, f"Expected 4 sessions in table, got {row_count}"

            # Find the row for sess-recent and check its data
            for row_key in session_table.rows.keys():
                if str(row_key.value) == "sess-recent":
                    # Get row data - columns are in order:
                    # Session ID, Project, Topic, Started, Last, Tools, Tokens, Msgs
                    row_data = session_table.get_row(row_key)

                    # Topic column (index 2) should show first prompt
                    topic_value = str(row_data[2])
                    assert "Recent task" in topic_value, (
                        f"Topic column should show first prompt, "
                        f"got '{topic_value}'"
                    )

                    # Tools column (index 5) should show "4"
                    tools_value = str(row_data[5])
                    assert tools_value == "4", (
                        f"Tools column should show '4' for 4 tools, "
                        f"got '{tools_value}'"
                    )

                    # Tokens column (index 6) should show "5.0k" for 5000
                    tokens_value = str(row_data[6])
                    assert tokens_value == "5.0k", (
                        f"Tokens column should show '5.0k' for 5000 tokens, "
                        f"got '{tokens_value}'"
                    )

                    # Messages column (index 7) should show "2"
                    msgs_value = str(row_data[7])
                    assert msgs_value == "2", (
                        f"Messages column should show '2', got '{msgs_value}'"
                    )

                    break
            else:
                pytest.fail("Could not find sess-recent row in table")

    @pytest.mark.asyncio
    async def test_session_selection_scrolls_to_top(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Selecting a session should scroll the events panel to the top.

        Currently the RichLog auto-scrolls to end as content is written.
        After populating events, scroll_home() should be called to show
        the beginning (topic line) instead of the end.

        This test verifies by checking if scroll_home() is called, or
        by mocking the RichLog to track scroll behavior.
        """
        from unittest.mock import patch, MagicMock

        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_events = app.query_one("#session-events", RichLog)

            # Track if scroll_home was called by patching
            scroll_home_called = False
            original_scroll_home = session_events.scroll_home

            def tracking_scroll_home(*args, **kwargs):
                nonlocal scroll_home_called
                scroll_home_called = True
                return original_scroll_home(*args, **kwargs)

            session_events.scroll_home = tracking_scroll_home

            # Call _show_session_events to populate the panel
            app._show_session_events("sess-recent")
            await pilot.pause()

            # Verify scroll_home was called after populating events
            # Currently it's NOT called, so this test should FAIL
            assert scroll_home_called, (
                "After populating session events, scroll_home() should be called "
                "to scroll to the top and show the topic line first. "
                "The fix is to add session_log.scroll_home() at the end of "
                "_show_session_events() in core/tui/app.py"
            )

    @pytest.mark.asyncio
    async def test_events_panel_shows_full_topic(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Events panel should display the full topic without truncation.

        Currently truncates to 100 chars: topic = summary.first_prompt[:100]
        Should show the full first_prompt without truncation.
        Location: core/tui/app.py:781-785 in _show_session_events
        """
        app = RecallMonitorApp()

        # Use wider terminal to fit full topic (217 chars)
        async with app.run_test(size=(250, 24)) as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_events = app.query_one("#session-events", RichLog)

            # Call _show_session_events for the long-topic session
            app._show_session_events("sess-long-topic")
            await pilot.pause()

            # Get the rendered text content
            lines_text = str(session_events.lines)

            # The full topic is 210 chars, but TranscriptSummary.first_prompt
            # truncates to 200 chars. Verify we're not adding a second truncation at 100.
            # Current buggy code: topic = summary.first_prompt[:100]
            full_topic = (
                "Implement a comprehensive authentication system with OAuth2 support, "
                "including Google and GitHub providers, session management with Redis, "
                "and JWT token refresh mechanisms for the new microservices architecture"
            )

            # Check that text AFTER the 100-char mark appears (proves no 100-char truncation)
            # "session management" starts at char ~110, so it would be cut by [:100]
            # but should appear since first_prompt stores up to 200 chars
            assert "session management" in lines_text, (
                f"Events panel should show full first_prompt (up to 200 chars). "
                f"Text after char 100 ('session management') should appear. "
                f"Fix: Remove the [:100] truncation in _show_session_events. "
                f"Lines: {lines_text[:300]}..."
            )

            # Also verify ellipsis is NOT present (since we're not truncating)
            # The current buggy code adds "..." after truncation
            # NOTE: Only check for the specific truncation pattern, not all ellipsis
            # (user content in timeline may have ellipsis)
            topic_line = [line for line in str(session_events.lines).split("\\n")
                          if "Topic:" in str(line)]
            if topic_line:
                topic_text = str(topic_line[0])
                # If truncated at 100 chars, it would end with "..." after ~100 chars of topic
                truncated_end = full_topic[:100] + "..."
                assert truncated_end not in topic_text, (
                    f"Topic should NOT be truncated with '...' at 100 chars. "
                    f"Found truncated pattern in topic line: {topic_text}"
                )

    @pytest.mark.asyncio
    async def test_session_table_project_column(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Project column shows correct project name."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_table = app.query_one("#session-list", DataTable)

            # Find any row and check project column
            for row_key in session_table.rows.keys():
                row_data = session_table.get_row(row_key)
                project_value = str(row_data[1])
                assert "project-a" in project_value or project_value == "a", (
                    f"Project column should show project name, got '{project_value}'"
                )
                break

    @pytest.mark.asyncio
    async def test_session_data_cached(
        self, mock_claude_home: Path, temp_state_dir: Path
    ):
        """Session data should be cached in _session_data dict."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            # Check that session data is cached
            assert len(app._session_data) == 4, (
                f"Expected 4 sessions in _session_data cache, "
                f"got {len(app._session_data)}"
            )

            # Verify cached data is TranscriptSummary
            for session_id, summary in app._session_data.items():
                assert isinstance(summary, TranscriptSummary), (
                    f"Cached data for {session_id} should be TranscriptSummary, "
                    f"got {type(summary)}"
                )


# --- Tests for Lesson Citations Display ---


def create_transcript_with_citations(
    path: Path,
    first_prompt: str,
    tools: list,
    tokens: int,
    start_time: str,
    end_time: str,
    assistant_text: str,
) -> None:
    """Create a mock transcript JSONL file with assistant text containing citations."""
    messages = []

    # User message
    messages.append(
        {
            "type": "user",
            "timestamp": start_time,
            "sessionId": path.stem,
            "message": {"role": "user", "content": first_prompt},
        }
    )

    # Assistant message with tools and text content (including citations)
    content = []
    for t in tools:
        content.append({"type": "tool_use", "name": t, "input": {}})
    if assistant_text:
        content.append({"type": "text", "text": assistant_text})

    messages.append(
        {
            "type": "assistant",
            "timestamp": end_time,
            "sessionId": path.stem,
            "message": {
                "role": "assistant",
                "usage": {"input_tokens": 100, "output_tokens": tokens},
                "content": content,
            },
        }
    )

    with open(path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")


@pytest.fixture
def mock_claude_home_with_citations(tmp_path: Path, monkeypatch) -> Path:
    """Create a mock ~/.claude directory with transcript files including citations."""
    claude_home = tmp_path / ".claude"
    projects_dir = claude_home / "projects"

    # Create project directory
    project_dir = projects_dir / "-Users-test-code-project-b"
    project_dir.mkdir(parents=True)

    # Session with citations
    create_transcript_with_citations(
        project_dir / "sess-with-citations.jsonl",
        first_prompt="Help me with authentication",
        tools=["Read", "Edit"],
        tokens=1500,
        start_time=make_timestamp(30),
        end_time=make_timestamp(20),
        assistant_text="Based on [L001]: Security patterns, I recommend using [S002]: OAuth best practices.",
    )

    # Session without citations
    create_transcript(
        project_dir / "sess-no-citations.jsonl",
        first_prompt="Simple task without lessons",
        tools=["Bash"],
        tokens=500,
        start_time=make_timestamp(15),
        end_time=make_timestamp(10),
    )

    # Monkeypatch to use our mock Claude home and project dir
    monkeypatch.setenv("PROJECT_DIR", "/Users/test/code/project-b")

    # Monkeypatch Path.home() to return our tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    return claude_home


class TestLessonCitationsDisplay:
    """Tests for lesson citations display in session events panel."""

    @pytest.mark.asyncio
    async def test_events_panel_shows_lesson_citations(
        self, mock_claude_home_with_citations: Path, temp_state_dir: Path
    ):
        """Verify 'Lessons cited: L001, S002' appears when session has citations."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_events = app.query_one("#session-events", RichLog)

            # Call _show_session_events for the session with citations
            app._show_session_events("sess-with-citations")
            await pilot.pause()

            # Get the rendered text content
            lines_text = str(session_events.lines)

            # Should show "Lessons cited:" line
            assert "Lessons cited:" in lines_text, (
                f"Session events panel should show 'Lessons cited:' for sessions with citations. "
                f"Lines: {lines_text[:300]}..."
            )

            # Should show the actual citation IDs
            assert "L001" in lines_text, (
                f"Session events should show L001 citation. Lines: {lines_text[:300]}..."
            )
            assert "S002" in lines_text, (
                f"Session events should show S002 citation. Lines: {lines_text[:300]}..."
            )

    @pytest.mark.asyncio
    async def test_events_panel_no_citations_line_when_empty(
        self, mock_claude_home_with_citations: Path, temp_state_dir: Path
    ):
        """Verify no 'Lessons cited' line when session has no citations."""
        app = RecallMonitorApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to Session tab
            await pilot.press("f4")
            await pilot.pause()

            session_events = app.query_one("#session-events", RichLog)

            # Call _show_session_events for the session WITHOUT citations
            app._show_session_events("sess-no-citations")
            await pilot.pause()

            # Get the rendered text content
            lines_text = str(session_events.lines)

            # Should NOT show "Lessons cited:" line
            assert "Lessons cited:" not in lines_text, (
                f"Session events panel should NOT show 'Lessons cited:' line when "
                f"session has no citations. Lines: {lines_text[:300]}..."
            )

    def test_transcript_summary_extracts_citations(
        self, mock_claude_home_with_citations: Path
    ):
        """TranscriptSummary should extract lesson citations from assistant messages."""
        reader = TranscriptReader(claude_home=mock_claude_home_with_citations)
        sessions = reader.list_sessions("/Users/test/code/project-b")

        # Find the session with citations
        with_citations = next(
            s for s in sessions if s.session_id == "sess-with-citations"
        )

        assert len(with_citations.lesson_citations) == 2, (
            f"Expected 2 lesson citations, got {len(with_citations.lesson_citations)}. "
            f"Citations: {with_citations.lesson_citations}"
        )
        assert "L001" in with_citations.lesson_citations, (
            f"Expected L001 in citations, got {with_citations.lesson_citations}"
        )
        assert "S002" in with_citations.lesson_citations, (
            f"Expected S002 in citations, got {with_citations.lesson_citations}"
        )

    def test_transcript_summary_empty_citations_for_no_lessons(
        self, mock_claude_home_with_citations: Path
    ):
        """TranscriptSummary should have empty citations list when no lessons cited."""
        reader = TranscriptReader(claude_home=mock_claude_home_with_citations)
        sessions = reader.list_sessions("/Users/test/code/project-b")

        # Find the session without citations
        no_citations = next(
            s for s in sessions if s.session_id == "sess-no-citations"
        )

        assert len(no_citations.lesson_citations) == 0, (
            f"Expected 0 lesson citations for session without lessons, "
            f"got {len(no_citations.lesson_citations)}. "
            f"Citations: {no_citations.lesson_citations}"
        )
