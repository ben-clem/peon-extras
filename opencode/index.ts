import { spawn } from "node:child_process"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import { createOpenCodeEventAdapter } from "./events.mjs"

function latestAssistantTokens(messages) {
  if (!Array.isArray(messages)) return null
  for (const message of [...messages].reverse()) {
    const info = message?.info || message
    if (info?.type !== "assistant" && info?.role !== "assistant") continue
    const tokens = info.tokens || message?.tokens
    if (!tokens || !Number.isFinite(Number(tokens.input))) continue
    const cached = Number(tokens.cache?.read || 0)
    return Number(tokens.input) + (Number.isFinite(cached) ? cached : 0)
  }
  return null
}

// V2's Plugin.define is a runtime identity helper. Local-path plugins do not
// resolve @opencode/plugin unless its full SDK dependency tree is installed, so
// export the equivalent plugin object directly and keep installation standalone.
export default {
  id: "peon-extras.opencode",
  async setup(ctx) {
    const extrasDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..")
    const hookScript = resolve(extrasDirectory, "opencode_hook.py")

    function emit(event) {
      const child = spawn("python3", [hookScript], {
        detached: true,
        stdio: ["pipe", "ignore", "ignore"],
      })
      child.on("error", () => {})
      child.stdin.end(JSON.stringify(event))
      child.unref()
    }

    async function messagesFor(sessionID) {
      try {
        return await ctx.session.context({ sessionID })
      } catch {
        return []
      }
    }

    async function sessionFor(sessionID) {
      try {
        return await ctx.session.get({ sessionID })
      } catch {
        return null
      }
    }

    async function compactionUsage(sessionID, messages) {
      let session
      try {
        session = await ctx.session.get({ sessionID })
      } catch {
        return {}
      }

      const transcript = Array.isArray(messages) && messages.length
        ? messages
        : await messagesFor(sessionID)
      const used = latestAssistantTokens(transcript)
      if (used === null) return {}

      let window = null
      if (session.model?.providerID && session.model?.modelID) {
        try {
          const models = await ctx.model.list()
          const model = models.find(
            (candidate) =>
              candidate.providerID === session.model.providerID &&
              candidate.id === session.model.modelID,
          )
          window = Number(model?.limit?.context)
        } catch {
          window = null
        }
      }
      if (!Number.isFinite(window) || window <= 0) return {}
      return {
        context_tokens: used,
        context_window_size: window,
        context_usage_percent: (used / window) * 100,
      }
    }

    const adapter = createOpenCodeEventAdapter({
      emit,
      getSession: sessionFor,
      getMessages: messagesFor,
      getCompactionUsage: compactionUsage,
      locationDirectory: ctx.location.directory,
    })

    await ctx.session.hook("compaction", (event) => adapter.beforeCompaction(event))

    const controller = new AbortController()
    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          await adapter.handle(event)
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error("[peon-extras] OpenCode event listener stopped", error)
        }
      }
    })()

    return () => controller.abort()
  },
}
