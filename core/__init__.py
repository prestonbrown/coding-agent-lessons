#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Coding Agent Lessons - Core module.

A learning system for AI coding agents that captures lessons across sessions
and tracks multi-step work via approaches.

Usage:
    from core import LessonsManager, Lesson, LessonRating

    manager = LessonsManager(lessons_base, project_root)
    manager.add_lesson("project", "pattern", "Title", "Content")
    manager.cite_lesson("L001")
"""

# Main class
from core.manager import LessonsManager

# Data models - Constants
from core.models import (
    ROBOT_EMOJI,
    SYSTEM_PROMOTION_THRESHOLD,
    STALE_DAYS_DEFAULT,
    MAX_USES,
    VELOCITY_DECAY_FACTOR,
    VELOCITY_EPSILON,
    APPROACH_MAX_COMPLETED,
    APPROACH_MAX_AGE_DAYS,
    SCORE_RELEVANCE_TIMEOUT,
    SCORE_RELEVANCE_MAX_QUERY_LEN,
)

# Data models - Enums
from core.models import (
    LessonLevel,
    LessonCategory,
)

# Data models - Dataclasses
from core.models import (
    Lesson,
    LessonRating,
    CitationResult,
    InjectionResult,
    DecayResult,
    TriedApproach,
    Approach,
    ApproachCompleteResult,
    ScoredLesson,
    RelevanceResult,
)

# Parsing utilities
from core.parsing import parse_lesson, format_lesson

# File locking
from core.file_lock import FileLock

# CLI entry point
from core.cli import main

__all__ = [
    # Main class
    "LessonsManager",
    # Constants
    "ROBOT_EMOJI",
    "SYSTEM_PROMOTION_THRESHOLD",
    "STALE_DAYS_DEFAULT",
    "MAX_USES",
    "VELOCITY_DECAY_FACTOR",
    "VELOCITY_EPSILON",
    "APPROACH_MAX_COMPLETED",
    "APPROACH_MAX_AGE_DAYS",
    "SCORE_RELEVANCE_TIMEOUT",
    "SCORE_RELEVANCE_MAX_QUERY_LEN",
    # Enums
    "LessonLevel",
    "LessonCategory",
    # Dataclasses
    "Lesson",
    "LessonRating",
    "CitationResult",
    "InjectionResult",
    "DecayResult",
    "TriedApproach",
    "Approach",
    "ApproachCompleteResult",
    "ScoredLesson",
    "RelevanceResult",
    # Parsing
    "parse_lesson",
    "format_lesson",
    # File locking
    "FileLock",
    # CLI
    "main",
]
