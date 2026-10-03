import { spawn } from "node:child_process"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import { createOpenCodeEventAdapter } from "./events.mjs"
import { compactionUsageForSession as calculateCompactionUsage } from "./usage.mjs"

// V2's Plugin.define is a runtime identity helper. Local-path plugins do not
// resolve @opencode/plugin unless its full SDK dependency tree is installed, so
// export the equivalent plugin object directly and keep installation standalone.
export default {
  id: "peon-extras.opencode",
  async setup(ctx) {
    const extrasDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..")
    const hookScript = resolve(extrasDirectory, "opencode_hook.py")
    let traceSequence = 0

    function traceEvent(phase, event) {
      if (process.env.PEON_EXTRAS_TRACE_EVENTS !== "1") return
      const data = event?.data && typeof event.data === "object"
        ? event.data
        : event?.properties && typeof event.properties === "object"
          ? event.properties
          : {}
      const info = data.info && typeof data.info === "object" ? data.info : data
      const title = phase === "peon" ? event?.title : info.title
      const directory = phase === "peon"
        ? event?.cwd
        : info.location?.directory || event?.location?.directory
      console.error(
        "[DEBUG-PEON-EXTRAS-TRACE]",
        JSON.stringify({
          sequence: ++traceSequence,
          phase,
          type: phase === "peon" ? event?.hook_event_name : event?.type,
          hasTitle: typeof title === "string" && Boolean(title.trim()),
          hasWorkspace: typeof directory === "string" && Boolean(directory.trim()),
        }),
      )
    }

    function emit(event) {
      traceEvent("peon", event)
      return new Promise((resolve) => {
        const child = spawn("python3", [hookScript], {
          stdio: ["pipe", "ignore", "ignore"],
        })
        const finish = () => resolve()
        child.on("error", finish)
        child.on("close", finish)
        child.stdin.on("error", finish)
        child.stdin.end(JSON.stringify(event))
      })
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

    async function compactionUsage(sessionID, messages, stage) {
      return calculateCompactionUsage(sessionID, messages, stage, {
        getSession: (id) => ctx.session.get({ sessionID: id }),
        getMessages: messagesFor,
        listModels: () => ctx.model.list(),
      })
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
          traceEvent("opencode", event)
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
