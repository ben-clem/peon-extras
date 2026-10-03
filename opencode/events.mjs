import { resolve } from "node:path"

function eventProperties(event) {
  if (event?.data && typeof event.data === "object") return event.data
  return event?.properties && typeof event.properties === "object"
    ? event.properties
    : {}
}

function sessionInfoFrom(properties, event) {
  const info = properties.info && typeof properties.info === "object"
    ? properties.info
    : properties.sessionID || properties.id
      ? { ...properties, id: properties.sessionID || properties.id }
      : null
  if (!info) return null
  return {
    ...info,
    location: { ...event?.location, ...info.location },
  }
}

function mergeSessionInfo(previous, current) {
  return {
    ...previous,
    ...current,
    location: { ...previous?.location, ...current?.location },
  }
}

function assistantExcerpt(messages) {
  if (!Array.isArray(messages)) return ""

  for (const message of [...messages].reverse()) {
    const info = message?.info || message
    if (info?.type !== "assistant" && info?.role !== "assistant") continue

    const content = message?.parts || info?.content || message?.content
    const text = Array.isArray(content)
      ? content
          .filter((part) => part?.type === "text" && typeof part.text === "string")
          .map((part) => part.text)
          .join("\n")
      : typeof content === "string"
        ? content
        : ""
    const withoutCode = text.replace(/```[\s\S]*?```/g, "")
    const excerpt = withoutCode
      .split(/\r?\n/)
      .map((line) => line.replace(/^[\s#>*|+-]+/, "").trim())
      .find(Boolean)
    if (excerpt) return excerpt.slice(0, 160)
  }

  return ""
}

function eventPayload(name, session, values = {}) {
  return {
    hook_event_name: name,
    session_id: session?.id || values.session_id || "",
    cwd: session?.location?.directory || "",
    title: session?.title || "",
    source: "opencode",
    ...values,
  }
}

function questionText(properties) {
  const questions = properties.questions
  const first = Array.isArray(questions) ? questions[0] : null
  if (typeof first === "string") return first.trim() || "Question pending"
  if (first && typeof first.question === "string") {
    return first.question.trim() || "Question pending"
  }
  return "Question pending"
}

function errorText(value) {
  if (typeof value === "string") return value
  if (value && typeof value.message === "string") return value.message
  if (value === undefined || value === null) return "OpenCode session failed"
  try {
    return JSON.stringify(value)
  } catch {
    return "OpenCode session failed"
  }
}

export function createOpenCodeEventAdapter({
  emit,
  getSession,
  getMessages,
  getCompactionUsage,
  locationDirectory,
}) {
  const expectedDirectory = locationDirectory ? resolve(locationDirectory) : null
  const sessions = new Map()
  const busySessions = new Set()
  const completedSessions = new Set()
  const failedSessions = new Set()
  const pendingQuestionIds = new Set()
  const pendingCompactions = new Set()

  async function sessionFor(sessionID, event) {
    const cached = sessions.get(sessionID)
    if (cached) return cached
    if (!getSession) return null

    try {
      const result = await getSession(sessionID)
      const properties = result?.data && typeof result.data === "object" ? result.data : result
      if (!properties || typeof properties !== "object") return null
      const info = sessionInfoFrom(properties, event) || { id: sessionID }
      const session = mergeSessionInfo(null, { ...info, id: info.id || sessionID })
      sessions.set(sessionID, session)
      return session
    } catch {
      return null
    }
  }

  async function belongsToLocation(event, properties, info) {
    if (!expectedDirectory) return true

    let directory = info?.location?.directory
    const sessionID = properties.sessionID || info?.id
    if (!directory && sessionID) {
      const session = await sessionFor(sessionID, event)
      directory = session?.location?.directory
    }
    return typeof directory === "string" && resolve(directory) === expectedDirectory
  }

  async function sessionFailed(sessionID, properties, event) {
    const session = await sessionFor(sessionID, event)
    if (session?.parentID) return
    busySessions.delete(sessionID)
    completedSessions.add(sessionID)
    failedSessions.add(sessionID)
    pendingCompactions.delete(sessionID)
    await emit(
      eventPayload("PostToolUseFailure", session, {
        session_id: sessionID,
        // peon.sh classifies this event as an error when tool_name is Bash.
        tool_name: "Bash",
        error: errorText(properties.error),
      }),
    )
  }

  async function sessionCompleted(sessionID, event) {
    const session = await sessionFor(sessionID, event)
    if (session?.parentID) return
    busySessions.delete(sessionID)
    if (failedSessions.delete(sessionID)) {
      completedSessions.add(sessionID)
      return
    }
    if (completedSessions.has(sessionID)) return
    completedSessions.add(sessionID)
    const messages = getMessages ? await getMessages(sessionID) : []
    await emit(
      eventPayload("Stop", session, {
        session_id: sessionID,
        message: assistantExcerpt(messages) || "Done",
      }),
    )
  }

  async function beforeCompaction(event) {
    const sessionID = event?.sessionID
    if (!sessionID) return
    const session = await sessionFor(sessionID, event)
    if (session?.parentID) return
    pendingCompactions.add(sessionID)
    const usage = getCompactionUsage
      ? await getCompactionUsage(sessionID, event.messages || [], "before")
      : {}
    await emit(eventPayload("PreCompact", session, { session_id: sessionID, ...usage }))
  }

  async function handle(event) {
    const properties = eventProperties(event)
    const info = sessionInfoFrom(properties, event)
    if (!(await belongsToLocation(event, properties, info))) return

    if (event?.type === "session.created" || event?.type === "session.updated") {
      if (info?.id) {
        const session = mergeSessionInfo(sessions.get(info.id), info)
        sessions.set(info.id, session)
      }
      return
    }

    if (event?.type === "session.status") {
      const sessionID = properties.sessionID
      const status = properties.status
      const statusType = typeof status === "object" ? status?.type : status
      if (!sessionID) return

      if (statusType === "busy" || statusType === "running") {
        if (busySessions.has(sessionID)) return
        busySessions.add(sessionID)
        completedSessions.delete(sessionID)
        failedSessions.delete(sessionID)
        const session = await sessionFor(sessionID, event)
        if (session?.parentID) return
        await emit(eventPayload("UserPromptSubmit", session, { session_id: sessionID }))
        return
      }

      busySessions.delete(sessionID)
      return
    }

    if (event?.type === "session.execution.started") {
      const sessionID = properties.sessionID
      if (!sessionID) return
      if (busySessions.has(sessionID)) return
      busySessions.add(sessionID)
      completedSessions.delete(sessionID)
      failedSessions.delete(sessionID)
      const session = await sessionFor(sessionID, event)
      if (session?.parentID) return
      await emit(eventPayload("UserPromptSubmit", session, { session_id: sessionID }))
      return
    }

    if (event?.type === "session.idle" || event?.type === "session.execution.succeeded") {
      const sessionID = properties.sessionID
      if (!sessionID) return
      await sessionCompleted(sessionID, event)
      return
    }

    if (event?.type === "session.error" || event?.type === "session.execution.failed") {
      const sessionID = properties.sessionID
      if (!sessionID) return
      await sessionFailed(sessionID, properties, event)
      return
    }

    if (event?.type === "session.compacted") {
      const sessionID = properties.sessionID
      if (!sessionID || !pendingCompactions.delete(sessionID)) return
      const session = await sessionFor(sessionID, event)
      if (session?.parentID) return
      const usage = getCompactionUsage
        ? await getCompactionUsage(sessionID, properties.messages || [], "after")
        : {}
      await emit(eventPayload("PostCompact", session, { session_id: sessionID, ...usage }))
      return
    }

    if (event?.type === "permission.asked") {
      const sessionID = properties.sessionID
      const session = sessionID ? await sessionFor(sessionID, event) : null
      if (session?.parentID) return
      await emit(
        eventPayload("PermissionRequest", session, {
          session_id: sessionID || "",
          tool_name: properties.action || "OpenCode",
        }),
      )
      return
    }

    if (event?.type === "question.asked" || event?.type === "question.v2.asked") {
      const sessionID = properties.sessionID
      const session = sessionID ? await sessionFor(sessionID, event) : null
      if (session?.parentID) return
      const requestID = properties.id
      if (typeof requestID !== "string" || pendingQuestionIds.has(requestID)) return
      if (pendingQuestionIds.size >= 100) {
        pendingQuestionIds.delete(pendingQuestionIds.values().next().value)
      }
      pendingQuestionIds.add(requestID)
      await emit(
        eventPayload("Notification", session, {
          session_id: sessionID || "",
          notification_type: "elicitation_dialog",
          message: questionText(properties),
          tool_name: "request_user_input",
        }),
      )
      return
    }

    if (
      event?.type === "question.replied" ||
      event?.type === "question.rejected" ||
      event?.type === "question.v2.replied" ||
      event?.type === "question.v2.rejected"
    ) {
      const requestID = properties.requestID || properties.id
      if (typeof requestID === "string") pendingQuestionIds.delete(requestID)
    }
  }

  return { beforeCompaction, handle }
}
