#!/bin/bash
# SPDX-License-Identifier: MIT
# Claude Code Stop hook - tracks lesson citations from AI responses
#
# Uses timestamp-based checkpointing to process citations incrementally:
# - First run: process all entries, save latest timestamp
# - Subsequent runs: only process entries newer than checkpoint

set -uo pipefail

MANAGER="$HOME/.config/coding-agent-lessons/lessons-manager.sh"
STATE_DIR="${LESSONS_BASE:-$HOME/.config/coding-agent-lessons}/.citation-state"

is_enabled() {
    local config="$HOME/.claude/settings.json"
    [[ -f "$config" ]] && {
        local enabled=$(jq -r '.lessonsSystem.enabled // true' "$config" 2>/dev/null || echo "true")
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

# Clean up orphaned checkpoint files (transcripts deleted but checkpoints remain)
# Runs opportunistically: max 10 files per invocation, only files >7 days old
cleanup_orphaned_checkpoints() {
    local max_age_days=7
    local max_cleanup=10
    local cleaned=0

    [[ -d "$STATE_DIR" ]] || return 0

    for state_file in "$STATE_DIR"/*; do
        [[ -f "$state_file" ]] || continue
        [[ $cleaned -ge $max_cleanup ]] && break

        local session_id=$(basename "$state_file")
        local found=false

        # Check if transcript exists in Claude's project directories
        if find ~/.claude/projects -name "${session_id}.jsonl" -type f 2>/dev/null | grep -q .; then
            found=true
        fi

        # If transcript not found and checkpoint is old enough, delete it
        if [[ "$found" == "false" ]]; then
            # Get file age in days (macOS: stat -f %m, Linux: stat -c %Y)
            local now=$(date +%s)
            local mtime=$(stat -f %m "$state_file" 2>/dev/null || stat -c %Y "$state_file" 2>/dev/null || echo "")

            # Safety: if stat failed or returned non-numeric, treat as new (don't delete)
            if [[ ! "$mtime" =~ ^[0-9]+$ ]]; then
                mtime=$now
            fi

            local file_age_days=$(( (now - mtime) / 86400 ))

            if [[ $file_age_days -gt $max_age_days ]]; then
                rm -f "$state_file"
                ((cleaned++)) || true
            fi
        fi
    done

    (( cleaned > 0 )) && echo "[lessons] Cleaned $cleaned orphaned checkpoint(s)" >&2
}

main() {
    is_enabled || exit 0

    # Read input first (stdin must be consumed before other operations)
    local input=$(cat)

    # Opportunistic cleanup runs early (doesn't depend on current session)
    cleanup_orphaned_checkpoints

    local cwd=$(echo "$input" | jq -r '.cwd // "."' 2>/dev/null || echo ".")
    local project_root=$(find_project_root "$cwd")
    local transcript_path=$(echo "$input" | jq -r '.transcript_path // ""' 2>/dev/null || echo "")

    # Expand tilde
    transcript_path="${transcript_path/#\~/$HOME}"

    [[ -z "$transcript_path" || ! -f "$transcript_path" ]] && exit 0

    # Checkpoint state
    mkdir -p "$STATE_DIR"
    local session_id=$(basename "$transcript_path" .jsonl)
    local state_file="$STATE_DIR/$session_id"
    local last_timestamp=""
    [[ -f "$state_file" ]] && last_timestamp=$(cat "$state_file")

    # Process entries newer than checkpoint
    # Filter by timestamp, extract citations from assistant messages
    local citations=""
    if [[ -z "$last_timestamp" ]]; then
        # First run: process all assistant messages
        citations=$(jq -r 'select(.type == "assistant") |
            .message.content[]? | select(.type == "text") | .text' "$transcript_path" 2>/dev/null | \
            grep -oE '\[[LS][0-9]{3}\]' | sort -u || true)
    else
        # Incremental: only entries after checkpoint
        citations=$(jq -r --arg ts "$last_timestamp" '
            select(.type == "assistant" and .timestamp > $ts) |
            .message.content[]? | select(.type == "text") | .text' "$transcript_path" 2>/dev/null | \
            grep -oE '\[[LS][0-9]{3}\]' | sort -u || true)
    fi

    # Get latest timestamp for checkpoint update
    local latest_ts=$(jq -r '.timestamp // empty' "$transcript_path" 2>/dev/null | tail -1)

    # Update checkpoint even if no citations (to advance the checkpoint)
    if [[ -z "$citations" ]]; then
        [[ -n "$latest_ts" ]] && echo "$latest_ts" > "$state_file"
        exit 0
    fi

    # Filter out lesson listings (ID followed by star rating bracket)
    # Real citations: "[L010]:" or "[L010]," (no star bracket)
    # Listings: "[L010] [*****" (ID followed by star rating)
    # Cache all text to avoid running jq per-citation
    local all_text=$(jq -r '.message.content[]? | select(.type == "text") | .text' "$transcript_path" 2>/dev/null || true)
    local filtered_citations=""
    while IFS= read -r cite; do
        [[ -z "$cite" ]] && continue
        # Check if this citation appears with a star bracket immediately after
        # Escape regex metacharacters in citation ID
        local escaped_cite=$(printf '%s' "$cite" | sed 's/[][\\.*^$()+?{|]/\\&/g')
        if ! echo "$all_text" | grep -qE "${escaped_cite} \\[\\*"; then
            filtered_citations+="$cite"$'\n'
        fi
    done <<< "$citations"
    citations=$(echo "$filtered_citations" | sort -u | grep -v '^$' || true)

    [[ -z "$citations" ]] && {
        [[ -n "$latest_ts" ]] && echo "$latest_ts" > "$state_file"
        exit 0
    }

    # Cite each lesson
    local cited_count=0
    while IFS= read -r citation; do
        [[ -z "$citation" ]] && continue
        local lesson_id=$(echo "$citation" | tr -d '[]')
        local result=$(PROJECT_DIR="$project_root" "$MANAGER" cite "$lesson_id" 2>&1 || true)
        if [[ "$result" == OK:* ]]; then
            ((cited_count++)) || true
        fi
    done <<< "$citations"

    # Update checkpoint
    [[ -n "$latest_ts" ]] && echo "$latest_ts" > "$state_file"

    (( cited_count > 0 )) && echo "[lessons] $cited_count lesson(s) cited" >&2
    exit 0
}

main
