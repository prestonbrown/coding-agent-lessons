#!/bin/bash
# SPDX-License-Identifier: MIT
# Claude Code UserPromptSubmit hook - captures LESSON: commands

set -euo pipefail

MANAGER="$HOME/.config/coding-agent-lessons/lessons-manager.sh"

is_enabled() {
    local config="$HOME/.claude/settings.json"
    [[ -f "$config" ]] && {
        local enabled=$(jq -r '.lessonsSystem.enabled // true' "$config" 2>/dev/null || echo "true")
        [[ "$enabled" == "true" ]]
    } || return 0
}

parse_lesson() {
    local prompt="$1" level="project" lesson_text=""
    
    if echo "$prompt" | grep -qi "^SYSTEM LESSON:"; then
        level="system"
        lesson_text=$(echo "$prompt" | sed -E 's/^SYSTEM LESSON:[[:space:]]*//i')
    elif echo "$prompt" | grep -qi "^LESSON:"; then
        lesson_text=$(echo "$prompt" | sed -E 's/^LESSON:[[:space:]]*//i')
    else
        return 1
    fi
    
    local category="correction"
    if [[ "$lesson_text" =~ ^([a-z]+):[[:space:]]*(.*)$ ]]; then
        category="${BASH_REMATCH[1]}"
        lesson_text="${BASH_REMATCH[2]}"
    fi
    
    local title="" content=""
    if [[ "$lesson_text" =~ ^([^-]+)[[:space:]]*-[[:space:]]*(.+)$ ]]; then
        title="${BASH_REMATCH[1]}"
        content="${BASH_REMATCH[2]}"
    else
        title="$lesson_text"
        content="$lesson_text"
    fi
    
    title=$(echo "$title" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')
    content=$(echo "$content" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')
    
    [[ -n "$title" && -n "$content" ]] && {
        echo "$level"
        echo "$category"
        echo "$title"
        echo "$content"
        return 0
    }
    return 1
}

main() {
    is_enabled || exit 0
    
    local input=$(cat)
    local prompt=$(echo "$input" | jq -r '.prompt // ""' 2>/dev/null || echo "")
    local cwd=$(echo "$input" | jq -r '.cwd // "."' 2>/dev/null || echo ".")
    
    [[ -z "$prompt" ]] && exit 0

    if parsed=$(parse_lesson "$prompt"); then
        local level=$(echo "$parsed" | sed -n '1p')
        local category=$(echo "$parsed" | sed -n '2p')
        local title=$(echo "$parsed" | sed -n '3p')
        local content=$(echo "$parsed" | sed -n '4p')
        
        local cmd="add"
        [[ "$level" == "system" ]] && cmd="add-system"
        
        local result=$(PROJECT_DIR="$cwd" LESSONS_DEBUG="${LESSONS_DEBUG:-}" "$MANAGER" "$cmd" "$category" "$title" "$content" 2>&1)
        local lesson_id=$(echo "$result" | grep -oE '\[[LS][0-9]+\]' | head -1 || echo "")
        
        cat << EOF
{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"LESSON RECORDED: $lesson_id [$title] added as $level lesson (category: $category). Cite using $lesson_id when applying."}}
EOF
    fi
    exit 0
}

main
