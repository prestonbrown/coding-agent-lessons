---
description: View and manage lessons
---

# Lessons Manager

Manage the Claude Recall system. Parse the arguments to determine the action.

**Arguments**: $ARGUMENTS

## Actions

Based on the arguments, run the appropriate command:

### No arguments or "list"
Run: `~/.config/claude-recall/lessons-manager.sh list --verbose`

Format output as a markdown table:
| ID | Stars | Title | Category | Last Cited | Content |
|----|-------|-------|----------|------------|---------|

### "search <term>"
Run: `~/.config/claude-recall/lessons-manager.sh list --search "<term>" --verbose`

### "category <cat>" or "cat <cat>"
Run: `~/.config/claude-recall/lessons-manager.sh list --category <cat> --verbose`

Valid categories: pattern, correction, gotcha, preference, decision

### "stale"
Run: `~/.config/claude-recall/lessons-manager.sh list --stale --verbose`

Show lessons uncited for 60+ days. Suggest reviewing/deleting stale ones.

### "edit <id> <content>"
Run: `~/.config/claude-recall/lessons-manager.sh edit <id> "<content>"`

### "delete <id>"
First show the lesson, ask for confirmation, then:
Run: `~/.config/claude-recall/lessons-manager.sh delete <id>`

### "help"
Show available subcommands:
- `/lessons` - List all lessons
- `/lessons search <term>` - Search by keyword
- `/lessons category <cat>` - Filter by category
- `/lessons stale` - Show stale lessons
- `/lessons edit <id> <content>` - Edit a lesson
- `/lessons delete <id>` - Delete (with confirmation)

## Execution

Run the command and present results clearly. For list operations, always format as a table.
