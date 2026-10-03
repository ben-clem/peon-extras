function latestAssistantUsage(messages) {
  const transcript = transcriptOf(messages)
  for (const message of [...transcript].reverse()) {
    const info = message?.info || message
    if (info?.type !== "assistant" && info?.role !== "assistant") continue
    const tokens = info.tokens || message?.tokens
    const model = info.model || message?.model
    const input = Number(tokens?.input)
    if (!tokens || !Number.isFinite(input)) continue
    const cached = Number(tokens.cache?.read || 0)
    return {
      used: input + (Number.isFinite(cached) ? cached : 0),
      providerID: info.providerID || message?.providerID || model?.providerID,
      modelID:
        info.modelID || message?.modelID || model?.modelID || model?.id,
    }
  }
  return null
}

function transcriptOf(messages) {
  const transcript = Array.isArray(messages) ? messages : messages?.data
  return Array.isArray(transcript) ? transcript : []
}

function latestCompletedCompaction(messages) {
  const transcript = transcriptOf(messages)
  for (let index = transcript.length - 1; index >= 0; index -= 1) {
    const message = transcript[index]
    const info = message?.info || message
    if (info?.type === "compaction" && info?.status === "completed") {
      return { index, message: info }
    }
  }
  return null
}

function postCompactionUsage(messages, fallbackMessages) {
  const source = [messages, fallbackMessages].find(latestCompletedCompaction)
  if (!source) {
    return {
      assistantUsage:
        latestAssistantUsage(messages) || latestAssistantUsage(fallbackMessages),
    }
  }

  const completed = latestCompletedCompaction(source)
  const transcript = transcriptOf(source)
  const assistantUsage = latestAssistantUsage(transcript.slice(completed.index + 1))
  if (assistantUsage) return { assistantUsage }

  const outputTokens = Number(completed.message.tokens?.output)
  return Number.isFinite(outputTokens) && outputTokens >= 0
    ? {
        summaryOutputTokens: outputTokens,
        providerID: completed.message.model?.providerID,
        modelID: completed.message.model?.modelID || completed.message.model?.id,
      }
    : {}
}

export async function compactionUsage(
  session,
  messages,
  listModels,
  fallbackMessages,
  stage = "before",
) {
  const postUsage = stage === "after"
    ? postCompactionUsage(messages, fallbackMessages)
    : null
  const assistantUsage = stage === "after"
    ? postUsage.assistantUsage || (postUsage.summaryOutputTokens === undefined
      ? null
      : {
          used: postUsage.summaryOutputTokens,
          providerID: postUsage.providerID,
          modelID: postUsage.modelID,
        })
    : latestAssistantUsage(messages) || latestAssistantUsage(fallbackMessages)
  if (!assistantUsage) return {}

  const sessionInfo = session?.data || session
  const providerID = assistantUsage.providerID || sessionInfo?.model?.providerID
  const modelID =
    assistantUsage.modelID ||
    sessionInfo?.model?.modelID ||
    sessionInfo?.model?.id
  if (!providerID || !modelID) return {}

  let models
  try {
    models = await listModels()
  } catch {
    return {}
  }

  const availableModels = Array.isArray(models) ? models : models?.data
  if (!Array.isArray(availableModels)) return {}
  const model = availableModels.find(
    (candidate) => candidate.providerID === providerID && candidate.id === modelID,
  )
  const window = Number(model?.limit?.context)
  if (!Number.isFinite(window) || window <= 0) return {}

  return {
    context_tokens: assistantUsage.used,
    context_window_size: window,
    context_usage_percent: (assistantUsage.used / window) * 100,
  }
}

export async function compactionUsageForSession(
  sessionID,
  messages,
  stage,
  { getSession, getMessages, listModels },
) {
  let session
  try {
    session = await getSession(sessionID)
  } catch {
    return {}
  }

  let storedMessages = []
  if (stage === "after" || !latestAssistantUsage(messages)) {
    try {
      storedMessages = await getMessages(sessionID)
    } catch {
      // No stored context is available; the hook payload can still be used.
    }
  }

  const storedTranscript = transcriptOf(storedMessages)
  const hasStoredMessages = storedTranscript.length > 0
  const primaryMessages = stage === "after" && hasStoredMessages
    ? storedMessages
    : messages
  const fallbackMessages = stage === "after" ? messages : storedMessages
  return compactionUsage(
    session,
    primaryMessages,
    listModels,
    fallbackMessages,
    stage,
  )
}
