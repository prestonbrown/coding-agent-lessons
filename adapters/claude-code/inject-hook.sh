#!/bin/bash
# SPDX-License-Identifier: MIT
# Claude Code SessionStart hook - injects lessons context

set -euo pipefail

MANAGER="$HOME/.config/coding-agent-lessons/lessons-manager.sh"
LESSONS_BASE="${LESSONS_BASE:-$HOME/.config/coding-agent-lessons}"
DECAY_INTERVAL=$((7 * 86400))  # 7 days in seconds

# Check if enabled
is_enabled() {
    local config="$HOME/.claude/settings.json"
    [[ -f "$config" ]] && {
        local enabled=$(jq -r '.lessonsSystem.enabled // true' "$config" 2>/dev/null || echo "true")
        [[ "$enabled" == "true" ]]
    } || return 0
}

# Run decay if it's been more than DECAY_INTERVAL since last run
run_decay_if_due() {
    local decay_state="$LESSONS_BASE/.decay-last-run"
    local now=$(date +%s)
    local last_run=0

    # Read and validate decay state (must be numeric)
    if [[ -f "$decay_state" ]]; then
        last_run=$(head -1 "$decay_state" 2>/dev/null | tr -dc '0-9')
        [[ -z "$last_run" ]] && last_run=0
    fi

    if [[ $((now - last_run)) -gt $DECAY_INTERVAL ]]; then
        # Run decay in background so it doesn't slow down session start
        # Only run if manager exists and is executable
        [[ -x "$MANAGER" ]] && "$MANAGER" decay 30 >/dev/null 2>&1 &
    fi
}

main() {
    is_enabled || exit 0
    
    local input=$(cat)
    local cwd=$(echo "$input" | jq -r '.cwd // "."' 2>/dev/null || echo ".")
    
    # Generate lessons context
    local summary=$(PROJECT_DIR="$cwd" "$MANAGER" inject 5 2>/dev/null || true)
    
    if [[ -n "$summary" ]]; then
        # Add lesson duty reminder
        summary="$summary

LESSON DUTY: When user corrects you, something fails, or you discover a pattern:
  ASK: \"Should I record this as a lesson? [category]: title - content\""
        
        local escaped=$(printf '%s' "$summary" | jq -Rs .)
        cat << EOF
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$escaped}}
EOF
    fi

    # Trigger decay check in background (runs weekly)
    run_decay_if_due

    exit 0
}

main
