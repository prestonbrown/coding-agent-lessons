#!/bin/bash
# SPDX-License-Identifier: MIT
# test-velocity.sh - Tests for velocity tracking in lessons system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANAGER="$SCRIPT_DIR/../core/lessons-manager.sh"

# Test state
TEST_HOME=""
CLAUDE_RECALL_BASE=""
PROJECT_DIR=""
SYSTEM_LESSONS=""
PROJECT_LESSONS=""
PASSED=0
FAILED=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

setup() {
    TEST_HOME=$(mktemp -d)
    CLAUDE_RECALL_BASE="$TEST_HOME/.config/claude-recall"
    PROJECT_DIR="$TEST_HOME/test-project"
    SYSTEM_LESSONS="$CLAUDE_RECALL_BASE/LESSONS.md"
    PROJECT_LESSONS="$PROJECT_DIR/.claude-recall/LESSONS.md"

    mkdir -p "$CLAUDE_RECALL_BASE" "$PROJECT_DIR/.claude-recall" "$CLAUDE_RECALL_BASE/.citation-state"

    # Create symlink for manager
    ln -sf "$MANAGER" "$CLAUDE_RECALL_BASE/lessons-manager.sh"

    export HOME="$TEST_HOME"
    export CLAUDE_RECALL_BASE
    export PROJECT_DIR
}

teardown() {
    [[ -n "$TEST_HOME" && -d "$TEST_HOME" ]] && rm -rf "$TEST_HOME"
}

run_manager() {
    PROJECT_DIR="$PROJECT_DIR" CLAUDE_RECALL_BASE="$CLAUDE_RECALL_BASE" "$MANAGER" "$@"
}

assert_equals() {
    local expected="$1" actual="$2" msg="${3:-}"
    if [[ "$expected" == "$actual" ]]; then
        return 0
    else
        echo "FAIL: $msg" >&2
        echo "  Expected: $expected" >&2
        echo "  Actual:   $actual" >&2
        return 1
    fi
}

assert_contains() {
    local haystack="$1" needle="$2" msg="${3:-}"
    if [[ "$haystack" == *"$needle"* ]]; then
        return 0
    else
        echo "FAIL: $msg" >&2
        echo "  Expected to contain: $needle" >&2
        echo "  Actual: $haystack" >&2
        return 1
    fi
}

assert_float_ge() {
    local value="$1" threshold="$2" msg="${3:-}"
    if command -v bc >/dev/null 2>&1; then
        if (( $(echo "$value >= $threshold" | bc -l) )); then
            return 0
        fi
    else
        if (( ${value%.*} >= ${threshold%.*} )); then
            return 0
        fi
    fi
    echo "FAIL: $msg" >&2
    echo "  Expected $value >= $threshold" >&2
    return 1
}

assert_float_lt() {
    local value="$1" threshold="$2" msg="${3:-}"
    if command -v bc >/dev/null 2>&1; then
        if (( $(echo "$value < $threshold" | bc -l) )); then
            return 0
        fi
    else
        if (( ${value%.*} < ${threshold%.*} )); then
            return 0
        fi
    fi
    echo "FAIL: $msg" >&2
    echo "  Expected $value < $threshold" >&2
    return 1
}

get_lesson_field() {
    local id="$1" field="$2" file="$3"
    grep -A1 "^### \[$id\]" "$file" 2>/dev/null | \
        grep -oE "\*\*$field\*\*: [0-9.]+" | \
        grep -oE '[0-9.]+' || echo ""
}

get_lesson_stars() {
    local id="$1" file="$2"
    grep "^### \[$id\]" "$file" 2>/dev/null | \
        grep -oE '\[[*+|/ -]+\]' | head -1 || echo ""
}

create_recent_session() {
    # Create a checkpoint file to simulate recent activity
    touch "$CLAUDE_RECALL_BASE/.citation-state/fake-session-$(date +%s)"
}

# Import just the lesson_rating function for direct testing
# This extracts the function without running main()
eval "$(sed -n '/^lesson_rating()/,/^}/p' "$MANAGER")"

#
# Rating Display Tests
#

test_rating_new_cold_lesson() {
    # Uses=1, Velocity=0 → new lesson, no recent activity
    local result=$(lesson_rating 1 0)
    assert_equals "[*----|-----]" "$result" "New cold lesson rating"
}

test_rating_established_hot_lesson() {
    # Uses=50, Velocity=3 → well-established, currently active
    local result=$(lesson_rating 50 3)
    assert_equals "[*****|**---]" "$result" "Established hot lesson rating"
}

test_rating_new_hot_lesson() {
    # Uses=3, Velocity=5 → just created but being cited heavily
    local result=$(lesson_rating 3 5)
    assert_equals "[**---|****+]" "$result" "New hot lesson rating"
}

test_rating_mature_cold_lesson() {
    # Uses=40, Velocity=0 → lots of history, not used recently
    local result=$(lesson_rating 40 0)
    assert_equals "[*****|-----]" "$result" "Mature cold lesson rating"
}

test_rating_uses_boundaries() {
    # Test uses thresholds
    assert_equals "[*----|-----]" "$(lesson_rating 1 0)" "Uses 1"
    assert_equals "[*----|-----]" "$(lesson_rating 2 0)" "Uses 2"
    assert_equals "[**---|-----]" "$(lesson_rating 3 0)" "Uses 3"
    assert_equals "[**---|-----]" "$(lesson_rating 5 0)" "Uses 5"
    assert_equals "[***--|-----]" "$(lesson_rating 6 0)" "Uses 6"
    assert_equals "[***--|-----]" "$(lesson_rating 12 0)" "Uses 12"
    assert_equals "[****-|-----]" "$(lesson_rating 13 0)" "Uses 13"
    assert_equals "[****-|-----]" "$(lesson_rating 30 0)" "Uses 30"
    assert_equals "[*****|-----]" "$(lesson_rating 31 0)" "Uses 31"
    assert_equals "[*****|-----]" "$(lesson_rating 100 0)" "Uses 100"
}

test_rating_velocity_boundaries() {
    # Test velocity thresholds
    assert_equals "[*----|-----]" "$(lesson_rating 1 0)" "Velocity 0"
    assert_equals "[*----|-----]" "$(lesson_rating 1 0.4)" "Velocity 0.4"
    assert_equals "[*----|+----]" "$(lesson_rating 1 0.5)" "Velocity 0.5"
    assert_equals "[*----|+----]" "$(lesson_rating 1 1.4)" "Velocity 1.4"
    assert_equals "[*----|*----]" "$(lesson_rating 1 1.5)" "Velocity 1.5"
    assert_equals "[*----|*----]" "$(lesson_rating 1 2.4)" "Velocity 2.4"
    assert_equals "[*----|**---]" "$(lesson_rating 1 2.5)" "Velocity 2.5"
    assert_equals "[*----|***--]" "$(lesson_rating 1 3.5)" "Velocity 3.5"
    assert_equals "[*----|****+]" "$(lesson_rating 1 4.5)" "Velocity 4.5"
    assert_equals "[*----|****+]" "$(lesson_rating 1 10)" "Velocity 10"
}

#
# Add Lesson Tests
#

test_add_lesson_includes_velocity() {
    setup
    run_manager add pattern "Test Lesson" "Test content" >/dev/null 2>&1 || true

    # Check that Velocity field is present with value 0
    local velocity=$(get_lesson_field "L001" "Velocity" "$PROJECT_LESSONS")
    assert_equals "0" "$velocity" "New lesson should have Velocity: 0"

    # Check new format with pipe separator
    local stars=$(get_lesson_stars "L001" "$PROJECT_LESSONS")
    assert_contains "$stars" "|" "Stars should use pipe separator"
    teardown
}

#
# Citation Tests
#

test_cite_increments_velocity() {
    setup
    run_manager add pattern "Test" "Content" >/dev/null 2>&1 || true

    # Initial velocity should be 0
    local v1=$(get_lesson_field "L001" "Velocity" "$PROJECT_LESSONS")
    assert_equals "0" "$v1" "Initial velocity should be 0"

    # Cite it
    run_manager cite L001 >/dev/null 2>&1 || true

    # Velocity should now be 1
    local v2=$(get_lesson_field "L001" "Velocity" "$PROJECT_LESSONS")
    assert_equals "1" "$v2" "Velocity after first cite should be 1"

    # Cite again
    run_manager cite L001 >/dev/null 2>&1 || true

    # Velocity should now be 2
    local v3=$(get_lesson_field "L001" "Velocity" "$PROJECT_LESSONS")
    assert_equals "2" "$v3" "Velocity after second cite should be 2"
    teardown
}

test_cite_updates_rating_display() {
    setup
    run_manager add pattern "Test" "Content" >/dev/null 2>&1 || true

    # Initial: Uses=1, Velocity=0 → [*----|-----]
    local stars1=$(get_lesson_stars "L001" "$PROJECT_LESSONS")
    assert_equals "[*----|-----]" "$stars1" "Initial rating"

    # Cite 5 times
    for i in {1..5}; do
        run_manager cite L001 >/dev/null 2>&1 || true
    done

    # Now: Uses=6, Velocity=5 → [***--|****+]
    local stars2=$(get_lesson_stars "L001" "$PROJECT_LESSONS")
    assert_equals "[***--|****+]" "$stars2" "Rating after 5 cites"
    teardown
}

#
# Decay Tests
#

test_decay_halves_velocity() {
    setup
    run_manager add pattern "Test" "Content" >/dev/null 2>&1 || true

    # Set up velocity by citing 4 times
    for i in {1..4}; do
        run_manager cite L001 >/dev/null 2>&1 || true
    done

    local v1=$(get_lesson_field "L001" "Velocity" "$PROJECT_LESSONS")
    assert_equals "4" "$v1" "Velocity should be 4 after 4 cites"

    # Create activity and run decay
    create_recent_session
    run_manager decay 0 >/dev/null 2>&1 || true

    # Velocity should be halved (4 → 2)
    local v2=$(get_lesson_field "L001" "Velocity" "$PROJECT_LESSONS")
    assert_equals "2" "$v2" "Velocity should be halved to 2"
    teardown
}

test_decay_velocity_approaches_zero() {
    setup
    run_manager add pattern "Test" "Content" >/dev/null 2>&1 || true

    # Set high velocity
    for i in {1..8}; do
        run_manager cite L001 >/dev/null 2>&1 || true
    done

    # Decay multiple times: 8 → 4 → 2 → 1 → 0.5 → 0.25 → 0.12 → 0.06 → 0.03 → 0
    for i in {1..10}; do
        create_recent_session
        run_manager decay 0 >/dev/null 2>&1 || true
    done

    local v=$(get_lesson_field "L001" "Velocity" "$PROJECT_LESSONS")
    assert_float_lt "${v:-0}" "0.1" "Velocity should approach 0"
    teardown
}

#
# Backward Compatibility Tests
#

test_old_format_lesson_gets_velocity_on_cite() {
    setup
    mkdir -p "$(dirname "$PROJECT_LESSONS")"

    # Create old-format lesson without Velocity field
    cat > "$PROJECT_LESSONS" << 'EOF'
# LESSONS.md - Project Level

> **Lessons System**: Cite lessons with [L###] when applying them.

## Active Lessons

### [L001] [***--/-----] Old Format Lesson
- **Uses**: 5 | **Learned**: 2024-01-01 | **Last**: 2024-12-01 | **Category**: pattern
> This is an old format lesson without velocity

EOF

    # Cite the old-format lesson
    run_manager cite L001 >/dev/null 2>&1 || true

    # Should now have Velocity field
    local velocity=$(get_lesson_field "L001" "Velocity" "$PROJECT_LESSONS")
    assert_equals "1" "$velocity" "Old lesson should get Velocity: 1 after cite"

    # Should have new pipe separator format
    local stars=$(get_lesson_stars "L001" "$PROJECT_LESSONS")
    assert_contains "$stars" "|" "Should use pipe separator after cite"
    teardown
}

test_old_format_displays_without_crashing() {
    setup
    mkdir -p "$(dirname "$PROJECT_LESSONS")"

    # Create old-format lesson
    cat > "$PROJECT_LESSONS" << 'EOF'
# LESSONS.md - Project Level

## Active Lessons

### [L001] [****-/-----] Old Lesson
- **Uses**: 15 | **Learned**: 2024-01-01 | **Last**: 2024-12-01 | **Category**: pattern
> Old format content

EOF

    # inject should work without crashing
    local output=$(run_manager inject 1 2>&1)
    assert_contains "$output" "L001" "Should display old format lesson"
    teardown
}

#
# Integration Tests
#

test_full_lifecycle() {
    setup

    # 1. Create lesson
    run_manager add pattern "Lifecycle Test" "Test content" >/dev/null 2>&1 || true
    local stars1=$(get_lesson_stars "L001" "$PROJECT_LESSONS")
    assert_equals "[*----|-----]" "$stars1" "Initial: new cold"

    # 2. Cite 5 times → hot
    for i in {1..5}; do
        run_manager cite L001 >/dev/null 2>&1 || true
    done
    local stars2=$(get_lesson_stars "L001" "$PROJECT_LESSONS")
    assert_equals "[***--|****+]" "$stars2" "After 5 cites: established hot"

    # 3. Decay twice
    create_recent_session
    run_manager decay 0 >/dev/null 2>&1 || true
    run_manager decay 0 >/dev/null 2>&1 || true

    # Velocity: 5 → 2.5 → 1.25, Uses unchanged
    local stars3=$(get_lesson_stars "L001" "$PROJECT_LESSONS")
    assert_contains "$stars3" "[***--|" "Uses still established"

    teardown
}

#
# Test Runner
#

run_test() {
    local test_name="$1"
    printf "  Testing: %s..." "$test_name"

    if "$test_name" 2>&1; then
        echo -e " ${GREEN}PASSED${NC}"
        ((PASSED++))
    else
        echo -e " ${RED}FAILED${NC}"
        ((FAILED++))
    fi
}

main() {
    echo "========================================"
    echo "  Velocity Tracking Tests"
    echo "========================================"
    echo ""

    echo "  Rating Display Tests"
    echo "  --------------------"
    run_test test_rating_new_cold_lesson
    run_test test_rating_established_hot_lesson
    run_test test_rating_new_hot_lesson
    run_test test_rating_mature_cold_lesson
    run_test test_rating_uses_boundaries
    run_test test_rating_velocity_boundaries
    echo ""

    echo "  Add Lesson Tests"
    echo "  ----------------"
    run_test test_add_lesson_includes_velocity
    echo ""

    echo "  Citation Tests"
    echo "  --------------"
    run_test test_cite_increments_velocity
    run_test test_cite_updates_rating_display
    echo ""

    echo "  Decay Tests"
    echo "  -----------"
    run_test test_decay_halves_velocity
    run_test test_decay_velocity_approaches_zero
    echo ""

    echo "  Backward Compatibility Tests"
    echo "  ----------------------------"
    run_test test_old_format_lesson_gets_velocity_on_cite
    run_test test_old_format_displays_without_crashing
    echo ""

    echo "  Integration Tests"
    echo "  -----------------"
    run_test test_full_lifecycle
    echo ""

    echo "========================================"
    echo "  Results: $PASSED/$((PASSED + FAILED)) passed"
    if (( FAILED == 0 )); then
        echo -e "  ${GREEN}All tests passed!${NC}"
    else
        echo -e "  ${RED}$FAILED test(s) failed${NC}"
    fi
    echo "========================================"

    return $FAILED
}

main "$@"
