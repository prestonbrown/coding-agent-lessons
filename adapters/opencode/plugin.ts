// SPDX-License-Identifier: MIT
// OpenCode adapter for coding-agent-lessons
//
// Hooks into OpenCode events to:
// 1. Inject lessons context at session start
// 2. Track lesson citations when AI responds (with checkpointing)
// 3. Capture LESSON: commands from user input

import type { Plugin } from "@opencode-ai/plugin"

const MANAGER = "~/.config/coding-agent-lessons/lessons-manager.sh"

// Per-session checkpoint: tracks the last processed message index
// This ensures we only process new messages on each idle event
const sessionCheckpoints = new Map<string, number>()

export const LessonsPlugin: Plugin = async ({ $, client }) => {
  return {
    // Inject lessons at session start
    "session.created": async (input) => {
      try {
        // Get lesson context to inject
        const { stdout } = await $`${MANAGER} inject 5`
        
        if (stdout && stdout.trim()) {
          // Inject into session as context without triggering AI response
          await client.session.prompt({
            path: { id: input.session.id },
            body: {
              noReply: true,
              parts: [{ 
                type: "text", 
                text: `<lessons-context>\n${stdout}\n</lessons-context>` 
              }],
            },
          })
        }
      } catch (e) {
        // Silently fail if lessons system not installed
        console.error("[lessons] Failed to inject:", e)
      }
    },

    // Track citations when session goes idle (AI finished responding)
    "session.idle": async (input) => {
      try {
        const sessionId = input.session.id

        // Get the messages from this session
        const messages = await client.session.messages({
          path: { id: sessionId }
        })

        // Get checkpoint: last processed message index
        const checkpoint = sessionCheckpoints.get(sessionId) ?? 0

        // Find assistant messages after the checkpoint
        const assistantMessages = messages
          .map((m, idx) => ({ ...m, idx }))
          .filter(m => m.info.role === "assistant" && m.idx >= checkpoint)

        if (assistantMessages.length === 0) {
          // Update checkpoint even if no new messages
          sessionCheckpoints.set(sessionId, messages.length)
          return
        }

        // Extract text content from all new assistant messages
        const allCitations = new Set<string>()

        for (const msg of assistantMessages) {
          const content = msg.parts
            .filter(p => p.type === "text")
            .map(p => (p as { type: "text"; text: string }).text)
            .join("")

          // Find [L###] or [S###] citations
          const citations = content.match(/\[(L|S)\d{3}\]/g) || []

          // Filter out lesson listings (e.g., "[L001] [*****" format)
          for (const cite of citations) {
            // Check if this is a real citation (not followed by star rating)
            if (!content.includes(`${cite} [*`)) {
              allCitations.add(cite)
            }
          }
        }

        // Cite each lesson
        for (const cite of allCitations) {
          const lessonId = cite.slice(1, -1) // Remove brackets
          await $`${MANAGER} cite ${lessonId}`
        }

        // Update checkpoint to current message count
        sessionCheckpoints.set(sessionId, messages.length)

        if (allCitations.size > 0) {
          console.log(`[lessons] Cited: ${[...allCitations].join(", ")}`)
        }
      } catch (e) {
        // Silently fail
      }
    },

    // Capture LESSON: commands from user messages
    "message.updated": async (input) => {
      if (input.message.role !== "user") return

      try {
        const text = input.message.parts
          .filter(p => p.type === "text")
          .map(p => (p as { type: "text"; text: string }).text)
          .join("")

        // Check for LESSON: or SYSTEM LESSON: prefix
        const systemMatch = text.match(/^SYSTEM\s+LESSON:\s*(.+)$/im)
        const projectMatch = text.match(/^LESSON:\s*(.+)$/im)

        if (systemMatch || projectMatch) {
          const isSystem = !!systemMatch
          const lessonText = (systemMatch?.[1] || projectMatch?.[1] || "").trim()

          // Parse category: title - content
          let category = "correction"
          let title = lessonText
          let content = lessonText

          const catMatch = lessonText.match(/^([a-z]+):\s*(.+)$/i)
          if (catMatch) {
            category = catMatch[1].toLowerCase()
            const rest = catMatch[2]
            const dashMatch = rest.match(/^(.+?)\s*-\s*(.+)$/)
            if (dashMatch) {
              title = dashMatch[1].trim()
              content = dashMatch[2].trim()
            } else {
              title = rest
              content = rest
            }
          } else {
            const dashMatch = lessonText.match(/^(.+?)\s*-\s*(.+)$/)
            if (dashMatch) {
              title = dashMatch[1].trim()
              content = dashMatch[2].trim()
            }
          }

          // Add the lesson
          const cmd = isSystem ? "add-system" : "add"
          const result = await $`${MANAGER} ${cmd} ${category} ${title} ${content}`
          console.log(`[lessons] ${result.stdout}`)
        }
      } catch (e) {
        // Silently fail
      }
    },
  }
}
