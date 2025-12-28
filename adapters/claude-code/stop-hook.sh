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

main() {
    is_enabled || exit 0

    local input=$(cat)
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
    local filtered_citations=""
    while IFS= read -r cite; do
        [[ -z "$cite" ]] && continue
        # Check if this citation appears with a star bracket immediately after
        # If transcript contains "[L010] [*" pattern, skip it
        if ! jq -r '.message.content[]? | select(.type == "text") | .text' "$transcript_path" 2>/dev/null | \
            grep -qE "\\$cite \\[\\*"; then
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
