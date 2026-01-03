#!/bin/bash
# SPDX-License-Identifier: MIT
# test-install.sh - Automated tests for install.sh

set -euo pipefail

# Test configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER="$SCRIPT_DIR/../install.sh"
TEST_DIR=$(mktemp -d)
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Override HOME for testing
export HOME="$TEST_DIR/home"
export CLAUDE_RECALL_BASE="$HOME/.config/claude-recall"

setup() {
    rm -rf "$TEST_DIR"
    mkdir -p "$HOME"
    mkdir -p "$HOME/.claude"  # Simulate Claude Code installed
}

teardown() {
    rm -rf "$TEST_DIR"
}

assert_eq() {
    local expected="$1"
    local actual="$2"
    local msg="${3:-}"
    if [[ "$expected" == "$actual" ]]; then
        return 0
    else
        echo -e "${RED}ASSERTION FAILED${NC}: $msg"
        echo "  Expected: '$expected'"
        echo "  Actual:   '$actual'"
        return 1
    fi
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local msg="${3:-}"
    if [[ "$haystack" == *"$needle"* ]]; then
        return 0
    else
        echo -e "${RED}ASSERTION FAILED${NC}: $msg"
        echo "  Expected to contain: '$needle'"
        echo "  Actual: '$haystack'"
        return 1
    fi
}

assert_file_exists() {
    local file="$1"
    local msg="${2:-File should exist: $file}"
    if [[ -f "$file" ]]; then
        return 0
    else
        echo -e "${RED}ASSERTION FAILED${NC}: $msg"
        return 1
    fi
}

assert_file_not_exists() {
    local file="$1"
    local msg="${2:-File should not exist: $file}"
    if [[ ! -f "$file" ]]; then
        return 0
    else
        echo -e "${RED}ASSERTION FAILED${NC}: $msg"
        return 1
    fi
}

assert_dir_exists() {
    local dir="$1"
    local msg="${2:-Directory should exist: $dir}"
    if [[ -d "$dir" ]]; then
        return 0
    else
        echo -e "${RED}ASSERTION FAILED${NC}: $msg"
        return 1
    fi
}

assert_executable() {
    local file="$1"
    local msg="${2:-File should be executable: $file}"
    if [[ -x "$file" ]]; then
        return 0
    else
        echo -e "${RED}ASSERTION FAILED${NC}: $msg"
        return 1
    fi
}

run_test() {
    local test_name="$1"
    local test_func="$2"
    ((TESTS_RUN++))
    
    setup
    
    echo -n "  Testing: $test_name ... "
    
    local output
    local exit_code=0
    if output=$($test_func 2>&1); then
        echo -e "${GREEN}PASSED${NC}"
        ((TESTS_PASSED++))
    else
        exit_code=$?
        echo -e "${RED}FAILED${NC}"
        echo "$output" | sed 's/^/    /'
        ((TESTS_FAILED++))
    fi
    
    teardown
}

# =============================================================================
# TEST CASES
# =============================================================================

test_help_option() {
    local output
    output=$("$INSTALLER" --help)
    assert_contains "$output" "Usage:" "Help should show usage"
    assert_contains "$output" "--claude" "Help should mention --claude"
    assert_contains "$output" "--opencode" "Help should mention --opencode"
    assert_contains "$output" "--migrate" "Help should mention --migrate"
}

test_install_core() {
    local output
    output=$("$INSTALLER" --claude 2>&1) || true
    
    assert_file_exists "$CLAUDE_RECALL_BASE/lessons-manager.sh" "Core script should be installed"
    assert_executable "$CLAUDE_RECALL_BASE/lessons-manager.sh" "Core script should be executable"
    assert_file_exists "$CLAUDE_RECALL_BASE/LESSONS.md" "System lessons file should be created"
}

test_install_claude_hooks() {
    local output
    output=$("$INSTALLER" --claude 2>&1) || true
    
    local hooks_dir="$HOME/.claude/hooks"
    assert_file_exists "$hooks_dir/inject-hook.sh" "Inject hook should be installed"
    assert_file_exists "$hooks_dir/capture-hook.sh" "Capture hook should be installed"
    assert_file_exists "$hooks_dir/stop-hook.sh" "Stop hook should be installed"
    assert_executable "$hooks_dir/inject-hook.sh" "Inject hook should be executable"
}

test_install_claude_command() {
    local output
    output=$("$INSTALLER" --claude 2>&1) || true
    
    local cmd_file="$HOME/.claude/commands/lessons.md"
    assert_file_exists "$cmd_file" "Lessons command should be installed"
    
    local content
    content=$(cat "$cmd_file")
    assert_contains "$content" "lessons-manager.sh" "Command should reference manager"
}

test_install_claude_settings() {
    local output
    output=$("$INSTALLER" --claude 2>&1) || true
    
    local settings_file="$HOME/.claude/settings.json"
    assert_file_exists "$settings_file" "Settings file should exist"
    
    local content
    content=$(cat "$settings_file")
    assert_contains "$content" "SessionStart" "Settings should have SessionStart hook"
    assert_contains "$content" "UserPromptSubmit" "Settings should have UserPromptSubmit hook"
    assert_contains "$content" "Stop" "Settings should have Stop hook"
}

test_install_claude_updates_claude_md() {
    local output
    output=$("$INSTALLER" --claude 2>&1) || true
    
    local claude_md="$HOME/.claude/CLAUDE.md"
    assert_file_exists "$claude_md" "CLAUDE.md should exist"
    
    local content
    content=$(cat "$claude_md")
    assert_contains "$content" "Lessons System" "CLAUDE.md should mention Lessons System"
    assert_contains "$content" "[L###]" "CLAUDE.md should explain project lesson IDs"
    assert_contains "$content" "[S###]" "CLAUDE.md should explain system lesson IDs"
}

test_install_preserves_existing_settings() {
    # Create existing settings
    mkdir -p "$HOME/.claude"
    echo '{"editor": "vim", "theme": "dark"}' > "$HOME/.claude/settings.json"
    
    local output
    output=$("$INSTALLER" --claude 2>&1) || true
    
    local settings_file="$HOME/.claude/settings.json"
    local content
    content=$(cat "$settings_file")
    assert_contains "$content" '"editor"' "Existing settings should be preserved"
    assert_contains "$content" "SessionStart" "New hooks should be added"
}

test_install_creates_backup() {
    # Create existing settings
    mkdir -p "$HOME/.claude"
    echo '{"existing": "config"}' > "$HOME/.claude/settings.json"
    
    local output
    output=$("$INSTALLER" --claude 2>&1) || true
    
    # Should have created a backup
    local backups
    backups=$(ls "$HOME/.claude/"settings.json.backup.* 2>/dev/null | wc -l)
    [[ $backups -ge 1 ]] || { echo "Should have created at least one backup"; return 1; }
}

test_migrate_system_lessons() {
    # Create old-style system lessons
    mkdir -p "$HOME/.claude"
    cat > "$HOME/.claude/LESSONS.md" << 'EOF'
# Old System Lessons

### [S001] Old Lesson
- **Uses**: 5
> Old content
EOF
    
    local output
    output=$("$INSTALLER" --migrate 2>&1)
    
    # Old file should be backed up
    assert_file_not_exists "$HOME/.claude/LESSONS.md" "Old file should be moved"
    
    # New file should exist
    assert_file_exists "$CLAUDE_RECALL_BASE/LESSONS.md" "New system file should exist"
    
    local content
    content=$(cat "$CLAUDE_RECALL_BASE/LESSONS.md")
    assert_contains "$content" "Old content" "Content should be migrated"
    
    # Backup should exist
    local backups
    backups=$(ls "$HOME/.claude/"LESSONS.md.migrated.* 2>/dev/null | wc -l)
    [[ $backups -ge 1 ]] || { echo "Old file should be backed up"; return 1; }
}

test_migrate_project_lessons() {
    # Create a fake project with old-style lessons
    local project_dir="$TEST_DIR/project"
    mkdir -p "$project_dir/.git"
    mkdir -p "$project_dir/.claude"
    cat > "$project_dir/.claude/LESSONS.md" << 'EOF'
# Old Project Lessons

### [L001] Project Lesson
- **Uses**: 3
> Project content
EOF
    
    # Run migration from project directory
    cd "$project_dir"
    local output
    output=$("$INSTALLER" --migrate 2>&1)
    
    assert_file_not_exists "$project_dir/.claude/LESSONS.md" "Old project file should be moved"
    assert_file_exists "$project_dir/.claude-recall/LESSONS.md" "New project file should exist"
    
    local content
    content=$(cat "$project_dir/.claude-recall/LESSONS.md")
    assert_contains "$content" "Project content" "Project content should be migrated"
}

test_migrate_cleans_empty_claude_dir() {
    local project_dir="$TEST_DIR/project"
    mkdir -p "$project_dir/.git"
    mkdir -p "$project_dir/.claude"
    echo "# Lessons" > "$project_dir/.claude/LESSONS.md"
    
    cd "$project_dir"
    local output
    output=$("$INSTALLER" --migrate 2>&1)
    
    # .claude directory should be removed if it only had LESSONS.md
    assert_file_not_exists "$project_dir/.claude" ".claude dir should be removed if empty"
}

test_migrate_preserves_other_claude_files() {
    local project_dir="$TEST_DIR/project"
    mkdir -p "$project_dir/.git"
    mkdir -p "$project_dir/.claude"
    echo "# Lessons" > "$project_dir/.claude/LESSONS.md"
    echo "Other content" > "$project_dir/.claude/other.txt"
    
    cd "$project_dir"
    local output
    output=$("$INSTALLER" --migrate 2>&1)
    
    # .claude directory should remain if it has other files
    assert_file_exists "$project_dir/.claude/other.txt" "Other files should be preserved"
}

test_migrate_no_lessons() {
    local output
    output=$("$INSTALLER" --migrate 2>&1)
    
    assert_contains "$output" "No old lessons found" "Should indicate nothing to migrate"
}

test_uninstall_removes_claude_hooks() {
    # First install
    "$INSTALLER" --claude >/dev/null 2>&1 || true
    
    # Then uninstall
    local output
    output=$("$INSTALLER" --uninstall 2>&1)
    
    assert_file_not_exists "$HOME/.claude/hooks/inject-hook.sh" "Inject hook should be removed"
    assert_file_not_exists "$HOME/.claude/hooks/capture-hook.sh" "Capture hook should be removed"
    assert_file_not_exists "$HOME/.claude/commands/lessons.md" "Command should be removed"
}

test_uninstall_preserves_lessons() {
    # First install and add some lessons
    "$INSTALLER" --claude >/dev/null 2>&1 || true
    echo "# My lessons" >> "$CLAUDE_RECALL_BASE/LESSONS.md"
    
    # Then uninstall
    local output
    output=$("$INSTALLER" --uninstall 2>&1)
    
    assert_file_exists "$CLAUDE_RECALL_BASE/LESSONS.md" "Lessons should be preserved"
    assert_file_not_exists "$CLAUDE_RECALL_BASE/lessons-manager.sh" "Manager should be removed"
    
    local content
    content=$(cat "$CLAUDE_RECALL_BASE/LESSONS.md")
    assert_contains "$content" "My lessons" "Lesson content should be preserved"
}

test_idempotent_install() {
    # Install twice
    "$INSTALLER" --claude >/dev/null 2>&1 || true
    local output
    output=$("$INSTALLER" --claude 2>&1) || true
    
    # Should not fail and should not duplicate content
    local claude_md="$HOME/.claude/CLAUDE.md"
    local count
    count=$(grep -c "Lessons System" "$claude_md" || echo 0)
    
    assert_eq "1" "$count" "Lessons System section should appear only once"
}

test_opencode_install() {
    mkdir -p "$HOME/.config/opencode"  # Simulate opencode installed
    
    local output
    output=$("$INSTALLER" --opencode 2>&1) || true
    
    assert_file_exists "$HOME/.config/opencode/plugin/lessons.ts" "Plugin should be installed"
    assert_file_exists "$HOME/.config/opencode/command/lessons.md" "Command should be installed"
}

test_auto_detect_claude() {
    # Only Claude is "installed" (setup creates .claude)
    rm -rf "$HOME/.config/opencode"
    
    local output
    output=$("$INSTALLER" 2>&1) || true
    
    assert_file_exists "$HOME/.claude/hooks/inject-hook.sh" "Claude hooks should be installed"
    assert_contains "$output" "Claude Code adapter" "Should mention Claude Code"
}

test_system_lessons_file_format() {
    "$INSTALLER" --claude >/dev/null 2>&1 || true
    
    local content
    content=$(cat "$CLAUDE_RECALL_BASE/LESSONS.md")
    
    assert_contains "$content" "System Level" "Should indicate system level"
    assert_contains "$content" "[S###]" "Should explain system lesson format"
    assert_contains "$content" "Active Lessons" "Should have Active Lessons header"
}

# =============================================================================
# RUN TESTS
# =============================================================================

main() {
    echo ""
    echo -e "${YELLOW}=== Install Script Test Suite ===${NC}"
    echo ""
    
    # Basic commands
    run_test "help option" test_help_option
    
    # Core installation
    run_test "install core" test_install_core
    
    # Claude Code installation
    run_test "install Claude hooks" test_install_claude_hooks
    run_test "install Claude command" test_install_claude_command
    run_test "install Claude settings" test_install_claude_settings
    run_test "install updates CLAUDE.md" test_install_claude_updates_claude_md
    run_test "preserves existing settings" test_install_preserves_existing_settings
    run_test "creates backup" test_install_creates_backup
    run_test "idempotent install" test_idempotent_install
    run_test "system lessons file format" test_system_lessons_file_format
    
    # Migration
    run_test "migrate system lessons" test_migrate_system_lessons
    run_test "migrate project lessons" test_migrate_project_lessons
    run_test "migrate cleans empty .claude dir" test_migrate_cleans_empty_claude_dir
    run_test "migrate preserves other .claude files" test_migrate_preserves_other_claude_files
    run_test "migrate no lessons" test_migrate_no_lessons
    
    # Uninstall
    run_test "uninstall removes Claude hooks" test_uninstall_removes_claude_hooks
    run_test "uninstall preserves lessons" test_uninstall_preserves_lessons
    
    # OpenCode
    run_test "OpenCode install" test_opencode_install
    
    # Auto-detect
    run_test "auto-detect Claude" test_auto_detect_claude
    
    echo ""
    echo -e "${YELLOW}=== Test Results ===${NC}"
    echo -e "  Total:  $TESTS_RUN"
    echo -e "  ${GREEN}Passed: $TESTS_PASSED${NC}"
    echo -e "  ${RED}Failed: $TESTS_FAILED${NC}"
    echo ""
    
    if [[ $TESTS_FAILED -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
