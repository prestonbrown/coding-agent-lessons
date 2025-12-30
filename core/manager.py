#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
LessonsManager class - Main entry point for the lessons system.

This module provides the LessonsManager class that combines lesson and approach
functionality through composition of mixins.
"""

from pathlib import Path

# Handle both module import and direct script execution
try:
    from core.lessons import LessonsMixin
    from core.approaches import ApproachesMixin
except ImportError:
    from lessons import LessonsMixin
    from approaches import ApproachesMixin


class LessonsManager(LessonsMixin, ApproachesMixin):
    """
    Manager for AI coding agent lessons.

    Provides methods to add, cite, edit, delete, promote, and list lessons
    stored in markdown format.

    This class composes functionality from:
    - LessonsMixin: All lesson-related operations
    - ApproachesMixin: All approach-related operations
    """

    def __init__(self, lessons_base: Path, project_root: Path):
        """
        Initialize the lessons manager.

        Args:
            lessons_base: Base directory for system lessons (~/.config/coding-agent-lessons)
            project_root: Root directory of the project (containing .git)
        """
        self.lessons_base = Path(lessons_base)
        self.project_root = Path(project_root)

        self.system_lessons_file = self.lessons_base / "LESSONS.md"
        self.project_lessons_file = self.project_root / ".coding-agent-lessons" / "LESSONS.md"

        self._decay_state_file = self.lessons_base / ".decay-last-run"
        self._session_state_dir = self.lessons_base / ".citation-state"

        # Ensure directories exist for both lessons files
        self.system_lessons_file.parent.mkdir(parents=True, exist_ok=True)
        self.project_lessons_file.parent.mkdir(parents=True, exist_ok=True)
