#!/bin/bash
# SPDX-License-Identifier: MIT
# Claude Recall PreCompact hook - captures session progress before compaction
#
# When auto-compaction or /compact is triggered, this hook:
# 1. Reads recent conversation from transcript
# 2. Uses Haiku to extract structured HandoffContext as JSON
# 3. Updates the most recent active handoff's context via set-context CLI
#
# This enables rich session handoff across compactions.

set -uo pipefail

# Guard against recursive calls from Haiku subprocesses
[[ -n "${LESSONS_SCORING_ACTIVE:-}" ]] && exit 0

# Support new (CLAUDE_RECALL_*), transitional (RECALL_*), and legacy (LESSONS_*) env vars
CLAUDE_RECALL_BASE="${CLAUDE_RECALL_BASE:-${RECALL_BASE:-${LESSONS_BASE:-$HOME/.config/claude-recall}}}"
CLAUDE_RECALL_STATE="${CLAUDE_RECALL_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/claude-recall}"
CLAUDE_RECALL_DEBUG="${CLAUDE_RECALL_DEBUG:-${RECALL_DEBUG:-${LESSONS_DEBUG:-}}}"
# Export for downstream Python manager
export CLAUDE_RECALL_STATE
# Export legacy names for downstream compatibility
LESSONS_BASE="$CLAUDE_RECALL_BASE"
LESSONS_DEBUG="$CLAUDE_RECALL_DEBUG"
# Python manager - try installed location first, fall back to dev location
if [[ -f "$CLAUDE_RECALL_BASE/cli.py" ]]; then
    PYTHON_MANAGER="$CLAUDE_RECALL_BASE/cli.py"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PYTHON_MANAGER="$SCRIPT_DIR/../../core/cli.py"
fi

# Maximum messages to include in summary prompt
MAX_MESSAGES=20
# Timeout for claude call (seconds)
CLAUDE_TIMEOUT=30

is_enabled() {
    local config="$HOME/.claude/settings.json"
    [[ -f "$config" ]] && {
        local enabled=$(jq -r '.claudeRecall.enabled // true' "$config" 2>/dev/null || echo "true")
        [[ "$enabled" == "true" ]]
    } || return 0
}

find_project_root() {
    local dir="${1:-$(pwd)}"
    while [[ "$dir" != "/" ]]; do
        [[ -d "$dir/.git" ]] && { echo "$dir"; return 0; }
        dir=$(dirname "$dir")
    done
    echo "$1"
}

# Get current git commit hash (short form)
get_git_ref() {
    local project_root="$1"
    git -C "$project_root" rev-parse --short HEAD 2>/dev/null || echo ""
}

# Extract recent messages from transcript for summarization
extract_recent_messages() {
    local transcript_path="$1"
    local max_messages="$2"

    # Get last N user/assistant messages, format as conversation
    jq -r --argjson max "$max_messages" '
        select(.type == "user" or .type == "assistant") |
        if .type == "user" then
            "User: " + (.message.content // "")
        else
            "Assistant: " + (
                if .message.content | type == "array" then
                    [.message.content[] | select(.type == "text") | .text] | join(" ")
                else
                    .message.content // ""
                end
            )
        end
    ' "$transcript_path" 2>/dev/null | tail -n "$max_messages"
}

# Call Haiku to extract structured handoff context as JSON
extract_handoff_context() {
    local messages="$1"
    local git_ref="$2"

    # Skip if messages are empty or too short
    [[ ${#messages} -lt 50 ]] && return 1

    local prompt='Analyze this conversation and extract a structured handoff context for session continuity.

Return ONLY valid JSON with these fields:
{
  "summary": "1-2 sentence progress summary - what was accomplished and current state",
  "critical_files": ["file.py:42", "other.py:100"],  // 2-3 most important file:line refs mentioned
  "recent_changes": ["Added X", "Fixed Y"],          // list of changes made this session
  "learnings": ["Pattern found", "Gotcha discovered"], // discoveries/patterns found
  "blockers": ["Waiting for Z"]                       // issues blocking progress (empty if none)
}

Important:
- Return ONLY the JSON object, no markdown code blocks, no explanation
- Keep arrays short (2-5 items max)
- Use file:line format for critical_files when line numbers are mentioned
- Leave arrays empty [] if nothing applies

Conversation:
'"$messages"

    # Call claude in programmatic mode with haiku
    local result
    result=$(echo "$prompt" | LESSONS_SCORING_ACTIVE=1 timeout "$CLAUDE_TIMEOUT" claude -p --model haiku 2>/dev/null) || return 1

    # Validate we got something useful
    [[ -z "$result" ]] && return 1

    # Strip any markdown code block markers if present
    result=$(echo "$result" | sed 's/^```json//g' | sed 's/^```//g' | sed 's/```$//g')

    # Inject git_ref into the JSON
    result=$(echo "$result" | jq --arg ref "$git_ref" '. + {git_ref: $ref}' 2>/dev/null) || return 1

    echo "$result"
}

# Legacy: Call Haiku to extract simple progress summary (fallback)
# TODO: Remove this function after 2025-06-01 when all users have migrated to structured handoff context
extract_progress_summary() {
    local messages="$1"

    # Skip if messages are empty or too short
    [[ ${#messages} -lt 50 ]] && return 1

    local prompt="Analyze this conversation excerpt and provide a VERY BRIEF progress summary (1-2 sentences max).
Focus on: what was accomplished, current state, and immediate next step.
Format: Just the summary text, no labels or formatting.

Conversation:
$messages"

    # Call claude in programmatic mode with haiku
    local result
    result=$(echo "$prompt" | LESSONS_SCORING_ACTIVE=1 timeout "$CLAUDE_TIMEOUT" claude -p --model haiku 2>/dev/null) || return 1

    # Validate we got something useful
    [[ -z "$result" ]] && return 1

    # Reject Haiku error responses that aren't actual summaries
    if [[ "$result" == *"I don't have"* ]] || [[ "$result" == *"conversation excerpt"* ]] || [[ "$result" == *"didn't come through"* ]]; then
        return 1
    fi

    [[ ${#result} -gt 500 ]] && result="${result:0:500}..."

    echo "$result"
}

# Get the most recent active handoff
get_most_recent_handoff() {
    local project_root="$1"

    if [[ -f "$PYTHON_MANAGER" ]]; then
        # Get first non-completed handoff (most recent by file order)
        # Matches both legacy A### format and new hf-XXXXXXX format
        PROJECT_DIR="$project_root" LESSONS_BASE="$LESSONS_BASE" \
            python3 "$PYTHON_MANAGER" handoff list 2>/dev/null | \
            head -1 | grep -oE '\[(A[0-9]{3}|hf-[0-9a-f]+)\]' | tr -d '[]' || true
    fi
}

# Detect if transcript indicates major work requiring a handoff
# Returns: comma-separated indicators if major, empty if minor
detect_major_work() {
    local transcript_path="$1"
    local indicators=""

    # Count TodoWrite tool uses
    local todo_count
    todo_count=$(jq -s '[.[].message.content[]? | select(.type == "tool_use" and .name == "TodoWrite")] | length' "$transcript_path" 2>/dev/null || echo "0")
    [[ $todo_count -ge 3 ]] && indicators="todos:$todo_count"

    # Count unique file edits (Edit tool_use)
    local file_count
    file_count=$(jq -rs '[.[].message.content[]? | select(.type == "tool_use" and .name == "Edit") | .input.file_path] | unique | length' "$transcript_path" 2>/dev/null || echo "0")
    if [[ $file_count -ge 4 ]]; then
        [[ -n "$indicators" ]] && indicators="$indicators,"
        indicators="${indicators}files:$file_count"
    fi

    # Check for implementing keywords in assistant messages
    local has_impl_keywords
    has_impl_keywords=$(jq -rs '[.[]] | map(select(.type == "assistant") | .message.content) | flatten | map(select(type == "object" and .type == "text") | .text) | join(" ")' "$transcript_path" 2>/dev/null | grep -iE '(implement|refactor|integrat|migrat|major change|multi-step|architecture)' | head -1)
    if [[ -n "$has_impl_keywords" ]]; then
        [[ -n "$indicators" ]] && indicators="$indicators,"
        indicators="${indicators}keywords"
    fi

    echo "$indicators"
}

# Auto-create a handoff from transcript analysis
auto_create_handoff() {
    local project_root="$1"
    local messages="$2"

    # Use Haiku to generate a title from the messages
    local title
    title=$(echo "$messages" | head -c 2000 | LESSONS_SCORING_ACTIVE=1 timeout 15 claude -p --model haiku "Summarize this work in 5-10 words as a task title (no punctuation, no quotes):" 2>/dev/null | head -1 | tr -d '"')
    [[ -z "$title" || ${#title} -lt 5 ]] && title="Auto-detected work session"

    # Create the handoff with implementing phase (we're mid-work)
    local result
    result=$(PROJECT_DIR="$project_root" LESSONS_BASE="$LESSONS_BASE" \
        python3 "$PYTHON_MANAGER" handoff add --phase implementing -- "$title" 2>&1)

    # Extract the ID
    echo "$result" | grep -oE 'hf-[0-9a-f]{7}' | head -1
}

# Save a minimal session snapshot for non-major work
save_session_snapshot() {
    local project_root="$1"
    local messages="$2"

    local snapshot_dir="$project_root/.claude-recall"
    local snapshot_file="$snapshot_dir/.session-snapshot"
    mkdir -p "$snapshot_dir"

    # Use Haiku to generate a brief summary
    local summary
    summary=$(echo "$messages" | head -c 2000 | LESSONS_SCORING_ACTIVE=1 timeout 10 claude -p --model haiku "One sentence summary of what was done in this session:" 2>/dev/null | head -1)
    [[ -z "$summary" ]] && summary="Session work (summary unavailable)"

    # Save with timestamp
    cat > "$snapshot_file" << EOF
timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)
summary: $summary
EOF
    echo "[precompact] Saved session snapshot to $snapshot_file" >&2
}

main() {
    is_enabled || exit 0

    # Read input from stdin
    local input=$(cat)

    local cwd=$(echo "$input" | jq -r '.cwd // "."' 2>/dev/null || echo ".")
    local project_root=$(find_project_root "$cwd")
    local transcript_path=$(echo "$input" | jq -r '.transcript_path // ""' 2>/dev/null || echo "")
    local trigger=$(echo "$input" | jq -r '.trigger // "auto"' 2>/dev/null || echo "auto")

    # Expand tilde
    transcript_path="${transcript_path/#\~/$HOME}"

    [[ -z "$transcript_path" || ! -f "$transcript_path" ]] && exit 0

    # Find most recent active handoff
    local handoff_id
    handoff_id=$(get_most_recent_handoff "$project_root")

    # Extract recent messages (needed for both existing handoff and auto-creation)
    local messages
    messages=$(extract_recent_messages "$transcript_path" "$MAX_MESSAGES")

    [[ -z "$messages" ]] && {
        echo "[precompact] No messages to summarize" >&2
        exit 0
    }

    # No active handoff - detect if we should create one or save snapshot
    if [[ -z "$handoff_id" ]]; then
        local work_indicators
        work_indicators=$(detect_major_work "$transcript_path")

        if [[ -n "$work_indicators" ]]; then
            # Major work detected - auto-create handoff
            echo "[precompact] Major work detected ($work_indicators) - auto-creating handoff" >&2
            handoff_id=$(auto_create_handoff "$project_root" "$messages")
            if [[ -z "$handoff_id" ]]; then
                echo "[precompact] Failed to auto-create handoff, saving snapshot instead" >&2
                save_session_snapshot "$project_root" "$messages"
                exit 0
            fi
            echo "[precompact] Auto-created handoff $handoff_id" >&2
        else
            # Minor work - save session snapshot
            save_session_snapshot "$project_root" "$messages"
            exit 0
        fi
    fi

    # Get current git ref
    local git_ref
    git_ref=$(get_git_ref "$project_root")

    # Try to extract structured handoff context first
    local context_json
    context_json=$(extract_handoff_context "$messages" "$git_ref")

    if [[ -n "$context_json" ]] && echo "$context_json" | jq -e . >/dev/null 2>&1; then
        # Use new structured set-context command
        if [[ -f "$PYTHON_MANAGER" ]]; then
            local result
            result=$(PROJECT_DIR="$project_root" LESSONS_BASE="$LESSONS_BASE" LESSONS_DEBUG="${LESSONS_DEBUG:-}" \
                python3 "$PYTHON_MANAGER" handoff set-context "$handoff_id" --json "$context_json" 2>&1)

            if [[ $? -eq 0 ]]; then
                local summary_preview
                summary_preview=$(echo "$context_json" | jq -r '.summary // ""' | head -c 50)
                echo "[precompact] Set context for $handoff_id (git: ${git_ref:-none}): ${summary_preview}..." >&2
            else
                echo "[precompact] Failed to set context: $result" >&2
                # Fall through to legacy checkpoint
            fi
        fi
    else
        # Fallback to legacy checkpoint if structured extraction fails
        echo "[precompact] Falling back to legacy checkpoint" >&2
        local summary
        summary=$(extract_progress_summary "$messages") || {
            echo "[precompact] Failed to extract progress summary" >&2
            exit 0
        }

        if [[ -f "$PYTHON_MANAGER" ]]; then
            local result
            result=$(PROJECT_DIR="$project_root" LESSONS_BASE="$LESSONS_BASE" LESSONS_DEBUG="${LESSONS_DEBUG:-}" \
                python3 "$PYTHON_MANAGER" handoff update "$handoff_id" --checkpoint "$summary" 2>&1)

            if [[ $? -eq 0 ]]; then
                echo "[precompact] Checkpointed $handoff_id: ${summary:0:50}..." >&2
            else
                echo "[precompact] Failed to update checkpoint: $result" >&2
            fi
        fi
    fi

    exit 0
}

main
