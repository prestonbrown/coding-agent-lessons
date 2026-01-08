#!/usr/bin/env python3
"""Tests for transcript_reader module - reads Claude session transcripts."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest


# Sample transcript data matching Claude's actual format
SAMPLE_USER_MESSAGE = {
    "type": "user",
    "uuid": "msg-user-001",
    "parentUuid": None,
    "timestamp": "2026-01-07T10:15:23.000Z",
    "sessionId": "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd",
    "cwd": "/Users/test/code/myproject",
    "message": {
        "role": "user",
        "content": "Help me fix the session panel display in the TUI. It's not showing sessions properly."
    },
    "userType": "external"
}

SAMPLE_ASSISTANT_MESSAGE_WITH_TOOLS = {
    "type": "assistant",
    "uuid": "msg-asst-001",
    "parentUuid": "msg-user-001",
    "timestamp": "2026-01-07T10:15:25.000Z",
    "sessionId": "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd",
    "message": {
        "role": "assistant",
        "id": "msg_01ABC123",
        "model": "claude-opus-4-5-20251101",
        "stop_reason": "tool_use",
        "usage": {
            "input_tokens": 1500,
            "output_tokens": 250,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 1000
        },
        "content": [
            {"type": "text", "text": "Let me look at the TUI code."},
            {
                "type": "tool_use",
                "id": "toolu_001",
                "name": "Read",
                "input": {"file_path": "/Users/test/code/myproject/core/tui/app.py"}
            }
        ]
    }
}

SAMPLE_ASSISTANT_MESSAGE_TEXT_ONLY = {
    "type": "assistant",
    "uuid": "msg-asst-002",
    "parentUuid": "msg-asst-001",
    "timestamp": "2026-01-07T10:15:30.000Z",
    "sessionId": "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd",
    "message": {
        "role": "assistant",
        "id": "msg_01ABC124",
        "model": "claude-opus-4-5-20251101",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 2000,
            "output_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 1500
        },
        "content": [
            {"type": "text", "text": "I found the issue. The session tab is reading from the wrong source."}
        ]
    }
}

SAMPLE_FILE_HISTORY = {
    "type": "file-history-snapshot",
    "timestamp": "2026-01-07T10:15:20.000Z",
    "sessionId": "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd"
}


@pytest.fixture
def temp_claude_home(tmp_path):
    """Create a temporary ~/.claude structure with sample transcripts."""
    claude_home = tmp_path / ".claude"
    projects_dir = claude_home / "projects"

    # Create project directory with URL-encoded path
    # /Users/test/code/myproject -> -Users-test-code-myproject
    project_dir = projects_dir / "-Users-test-code-myproject"
    project_dir.mkdir(parents=True)

    # Create a sample transcript
    transcript_path = project_dir / "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd.jsonl"
    with open(transcript_path, "w") as f:
        f.write(json.dumps(SAMPLE_FILE_HISTORY) + "\n")
        f.write(json.dumps(SAMPLE_USER_MESSAGE) + "\n")
        f.write(json.dumps(SAMPLE_ASSISTANT_MESSAGE_WITH_TOOLS) + "\n")
        f.write(json.dumps(SAMPLE_ASSISTANT_MESSAGE_TEXT_ONLY) + "\n")

    # Create another transcript (older)
    older_transcript = project_dir / "older-session-id.jsonl"
    older_msg = SAMPLE_USER_MESSAGE.copy()
    older_msg["timestamp"] = "2026-01-06T09:00:00.000Z"
    older_msg["message"] = {"role": "user", "content": "This is an older session about something else."}
    with open(older_transcript, "w") as f:
        f.write(json.dumps(older_msg) + "\n")

    # Create a second project
    project2_dir = projects_dir / "-Users-test-code-other-project"
    project2_dir.mkdir(parents=True)

    transcript2 = project2_dir / "other-session.jsonl"
    other_msg = SAMPLE_USER_MESSAGE.copy()
    other_msg["sessionId"] = "other-session"
    other_msg["message"] = {"role": "user", "content": "Working on a different project."}
    with open(transcript2, "w") as f:
        f.write(json.dumps(other_msg) + "\n")

    return claude_home


class TestTranscriptReaderImport:
    """Test that transcript_reader module exists and is importable."""

    def test_module_importable(self):
        """TranscriptReader should be importable from core.tui."""
        from core.tui.transcript_reader import TranscriptReader
        assert TranscriptReader is not None

    def test_dataclasses_importable(self):
        """TranscriptMessage and TranscriptSummary should be importable."""
        from core.tui.transcript_reader import TranscriptMessage, TranscriptSummary
        assert TranscriptMessage is not None
        assert TranscriptSummary is not None


class TestProjectPathEncoding:
    """Test URL-encoding of project paths to match Claude's directory naming."""

    def test_encode_simple_path(self, temp_claude_home):
        """Simple path should be encoded with leading dash and slashes replaced."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        encoded = reader.encode_project_path("/Users/test/code/myproject")
        assert encoded == "-Users-test-code-myproject"

    def test_encode_path_with_dots(self, temp_claude_home):
        """Path with dots should encode dots as dashes."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        # Claude encodes .local as --local (double dash for dot)
        encoded = reader.encode_project_path("/Users/test/.local/state")
        assert encoded == "-Users-test--local-state"

    def test_get_project_dir(self, temp_claude_home):
        """get_project_dir should return correct path for project."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        project_dir = reader.get_project_dir("/Users/test/code/myproject")

        assert project_dir.exists()
        assert project_dir.name == "-Users-test-code-myproject"


class TestListSessions:
    """Test listing sessions from a project directory."""

    def test_list_sessions_returns_summaries(self, temp_claude_home):
        """list_sessions should return TranscriptSummary objects."""
        from core.tui.transcript_reader import TranscriptReader, TranscriptSummary

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        assert len(sessions) == 2
        assert all(isinstance(s, TranscriptSummary) for s in sessions)

    def test_list_sessions_sorted_by_time(self, temp_claude_home):
        """Sessions should be sorted by most recent first."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        # First session should be the more recent one
        assert sessions[0].session_id == "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd"
        assert sessions[1].session_id == "older-session-id"

    def test_list_sessions_respects_limit(self, temp_claude_home):
        """list_sessions should respect the limit parameter."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject", limit=1)

        assert len(sessions) == 1

    def test_list_sessions_extracts_first_prompt(self, temp_claude_home):
        """Each session should have first_prompt populated."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        # Find the session with the known prompt
        session = next(s for s in sessions if s.session_id == "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd")
        assert "session panel" in session.first_prompt.lower()

    def test_list_sessions_counts_tools(self, temp_claude_home):
        """Session summary should include tool breakdown."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        session = next(s for s in sessions if s.session_id == "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd")
        assert "Read" in session.tool_breakdown
        assert session.tool_breakdown["Read"] == 1

    def test_list_sessions_nonexistent_project(self, temp_claude_home):
        """Nonexistent project should return empty list."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/nonexistent/project")

        assert sessions == []


class TestListAllSessions:
    """Test listing sessions from all projects."""

    def test_list_all_sessions(self, temp_claude_home):
        """list_all_sessions should return sessions from all projects."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_all_sessions()

        # Should have sessions from both projects
        assert len(sessions) == 3

    def test_list_all_sessions_sorted_by_time(self, temp_claude_home):
        """All sessions should be sorted by most recent first."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_all_sessions()

        # Should be in descending time order
        times = [s.last_activity for s in sessions]
        assert times == sorted(times, reverse=True)

    def test_list_all_sessions_includes_project(self, temp_claude_home):
        """Each session should have project field populated."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_all_sessions()

        projects = {s.project for s in sessions}
        assert "myproject" in projects or "-Users-test-code-myproject" in projects


class TestLoadSession:
    """Test loading full session transcript."""

    def test_load_session_returns_messages(self, temp_claude_home):
        """load_session should return list of TranscriptMessage."""
        from core.tui.transcript_reader import TranscriptReader, TranscriptMessage

        reader = TranscriptReader(claude_home=temp_claude_home)
        project_dir = reader.get_project_dir("/Users/test/code/myproject")
        session_path = project_dir / "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd.jsonl"

        messages = reader.load_session(session_path)

        assert len(messages) >= 2  # At least user + assistant
        assert all(isinstance(m, TranscriptMessage) for m in messages)

    def test_load_session_includes_user_messages(self, temp_claude_home):
        """User messages should be parsed with content."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        project_dir = reader.get_project_dir("/Users/test/code/myproject")
        session_path = project_dir / "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd.jsonl"

        messages = reader.load_session(session_path)
        user_msgs = [m for m in messages if m.type == "user"]

        assert len(user_msgs) >= 1
        assert "session panel" in user_msgs[0].content.lower()

    def test_load_session_includes_tool_usage(self, temp_claude_home):
        """Assistant messages should have tools_used populated."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        project_dir = reader.get_project_dir("/Users/test/code/myproject")
        session_path = project_dir / "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd.jsonl"

        messages = reader.load_session(session_path)
        tool_msgs = [m for m in messages if m.tools_used]

        assert len(tool_msgs) >= 1
        assert "Read" in tool_msgs[0].tools_used

    def test_load_session_skips_file_history(self, temp_claude_home):
        """file-history-snapshot messages should be skipped."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        project_dir = reader.get_project_dir("/Users/test/code/myproject")
        session_path = project_dir / "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd.jsonl"

        messages = reader.load_session(session_path)
        types = {m.type for m in messages}

        assert "file-history-snapshot" not in types


class TestTranscriptSummaryFields:
    """Test that TranscriptSummary has all required fields."""

    def test_summary_has_session_id(self, temp_claude_home):
        """Summary should have session_id field."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        assert all(hasattr(s, "session_id") for s in sessions)
        assert all(s.session_id for s in sessions)

    def test_summary_has_path(self, temp_claude_home):
        """Summary should have path to transcript file."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        assert all(hasattr(s, "path") for s in sessions)
        assert all(s.path.exists() for s in sessions)

    def test_summary_has_timestamps(self, temp_claude_home):
        """Summary should have start_time and last_activity."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        for s in sessions:
            assert hasattr(s, "start_time")
            assert hasattr(s, "last_activity")
            assert isinstance(s.start_time, datetime)
            assert isinstance(s.last_activity, datetime)

    def test_summary_has_message_count(self, temp_claude_home):
        """Summary should have message_count."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        session = next(s for s in sessions if s.session_id == "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd")
        assert session.message_count >= 2

    def test_summary_has_total_tokens(self, temp_claude_home):
        """Summary should have total_tokens from usage data."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        session = next(s for s in sessions if s.session_id == "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd")
        assert session.total_tokens > 0


class TestTranscriptMessageFields:
    """Test that TranscriptMessage has all required fields."""

    def test_message_has_type(self, temp_claude_home):
        """Message should have type field (user/assistant)."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        project_dir = reader.get_project_dir("/Users/test/code/myproject")
        session_path = project_dir / "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd.jsonl"

        messages = reader.load_session(session_path)

        assert all(m.type in ("user", "assistant") for m in messages)

    def test_message_has_timestamp(self, temp_claude_home):
        """Message should have timestamp as datetime."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        project_dir = reader.get_project_dir("/Users/test/code/myproject")
        session_path = project_dir / "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd.jsonl"

        messages = reader.load_session(session_path)

        assert all(isinstance(m.timestamp, datetime) for m in messages)

    def test_message_has_content(self, temp_claude_home):
        """Message should have content field."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        project_dir = reader.get_project_dir("/Users/test/code/myproject")
        session_path = project_dir / "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd.jsonl"

        messages = reader.load_session(session_path)

        # User messages should have full content
        user_msgs = [m for m in messages if m.type == "user"]
        assert all(m.content for m in user_msgs)

    def test_message_has_tools_used_list(self, temp_claude_home):
        """Message should have tools_used as list."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home)
        project_dir = reader.get_project_dir("/Users/test/code/myproject")
        session_path = project_dir / "eb3513a8-77ea-41c9-94fd-e8cdf700a4dd.jsonl"

        messages = reader.load_session(session_path)

        assert all(isinstance(m.tools_used, list) for m in messages)


# Sample transcript data with lesson citations for citation tests
ASSISTANT_WITH_CITATIONS = {
    "type": "assistant",
    "uuid": "msg-asst-cite-001",
    "parentUuid": "msg-user-001",
    "timestamp": "2026-01-07T10:16:00.000Z",
    "sessionId": "citation-session-id",
    "message": {
        "role": "assistant",
        "id": "msg_cite_001",
        "model": "claude-opus-4-5-20251101",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 500
        },
        "content": [
            {"type": "text", "text": "Based on [L001]: Test-first development, I'll write tests first. Also referencing [S002]: System lesson about patterns."}
        ]
    }
}

ASSISTANT_WITH_DUPLICATE_CITATIONS = {
    "type": "assistant",
    "uuid": "msg-asst-cite-002",
    "parentUuid": "msg-asst-cite-001",
    "timestamp": "2026-01-07T10:17:00.000Z",
    "sessionId": "citation-session-id",
    "message": {
        "role": "assistant",
        "id": "msg_cite_002",
        "model": "claude-opus-4-5-20251101",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 150,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 600
        },
        "content": [
            {"type": "text", "text": "As mentioned in [L001]: this is important. Also [L003]: another lesson and [L001] again."}
        ]
    }
}

USER_WITH_CITATION = {
    "type": "user",
    "uuid": "msg-user-cite-001",
    "parentUuid": None,
    "timestamp": "2026-01-07T10:15:00.000Z",
    "sessionId": "citation-session-id",
    "cwd": "/Users/test/code/myproject",
    "message": {
        "role": "user",
        "content": "Please use [L999]: this lesson in your response."
    },
    "userType": "external"
}

ASSISTANT_WITHOUT_CITATIONS = {
    "type": "assistant",
    "uuid": "msg-asst-nocite-001",
    "parentUuid": "msg-user-001",
    "timestamp": "2026-01-07T10:16:30.000Z",
    "sessionId": "no-citation-session-id",
    "message": {
        "role": "assistant",
        "id": "msg_nocite_001",
        "model": "claude-opus-4-5-20251101",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 800,
            "output_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 400
        },
        "content": [
            {"type": "text", "text": "Here is a response without any lesson citations."}
        ]
    }
}


@pytest.fixture
def temp_claude_home_with_citations(tmp_path):
    """Create a temporary ~/.claude structure with transcripts containing citations."""
    claude_home = tmp_path / ".claude"
    projects_dir = claude_home / "projects"

    project_dir = projects_dir / "-Users-test-code-myproject"
    project_dir.mkdir(parents=True)

    # Create transcript with citations in assistant messages
    citation_transcript = project_dir / "citation-session-id.jsonl"
    with open(citation_transcript, "w") as f:
        f.write(json.dumps(USER_WITH_CITATION) + "\n")
        f.write(json.dumps(ASSISTANT_WITH_CITATIONS) + "\n")
        f.write(json.dumps(ASSISTANT_WITH_DUPLICATE_CITATIONS) + "\n")

    # Create transcript without citations
    no_citation_transcript = project_dir / "no-citation-session-id.jsonl"
    with open(no_citation_transcript, "w") as f:
        f.write(json.dumps(SAMPLE_USER_MESSAGE) + "\n")
        f.write(json.dumps(ASSISTANT_WITHOUT_CITATIONS) + "\n")

    return claude_home


class TestLessonCitationExtraction:
    """Test extraction of lesson citations [L###] and [S###] from transcripts."""

    def test_extract_citations_from_assistant_messages(self, temp_claude_home_with_citations):
        """Transcript with citations should populate lesson_citations field."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home_with_citations)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        # Find the session with citations
        session = next(s for s in sessions if s.session_id == "citation-session-id")

        # This should fail because lesson_citations field doesn't exist yet
        assert hasattr(session, "lesson_citations"), "TranscriptSummary should have lesson_citations field"
        assert "L001" in session.lesson_citations
        assert "S002" in session.lesson_citations

    def test_citations_are_unique_and_sorted(self, temp_claude_home_with_citations):
        """Duplicate citations should be deduplicated and sorted."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home_with_citations)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        session = next(s for s in sessions if s.session_id == "citation-session-id")

        # This should fail because lesson_citations field doesn't exist yet
        assert hasattr(session, "lesson_citations"), "TranscriptSummary should have lesson_citations field"

        # Citations should be unique (L001 appears multiple times but should only be listed once)
        # and sorted alphabetically: L001, L003, S002
        assert session.lesson_citations == ["L001", "L003", "S002"]

    def test_citations_ignore_user_messages(self, temp_claude_home_with_citations):
        """Citations in user messages should be ignored."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home_with_citations)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        session = next(s for s in sessions if s.session_id == "citation-session-id")

        # This should fail because lesson_citations field doesn't exist yet
        assert hasattr(session, "lesson_citations"), "TranscriptSummary should have lesson_citations field"

        # L999 is in user message, should NOT be extracted
        assert "L999" not in session.lesson_citations

    def test_no_citations_returns_empty_list(self, temp_claude_home_with_citations):
        """Transcript without citations should have empty lesson_citations list."""
        from core.tui.transcript_reader import TranscriptReader

        reader = TranscriptReader(claude_home=temp_claude_home_with_citations)
        sessions = reader.list_sessions("/Users/test/code/myproject")

        session = next(s for s in sessions if s.session_id == "no-citation-session-id")

        # This should fail because lesson_citations field doesn't exist yet
        assert hasattr(session, "lesson_citations"), "TranscriptSummary should have lesson_citations field"
        assert session.lesson_citations == []
