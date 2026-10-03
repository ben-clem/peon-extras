import assert from "node:assert/strict"
import test from "node:test"

import { createOpenCodeEventAdapter } from "../opencode/events.mjs"

test("a new root session sends one prompt-submit event on its first prompt", async () => {
  const emitted = []
  const adapter = createOpenCodeEventAdapter({ emit: (event) => emitted.push(event) })

  await adapter.handle({
    id: "evt_session_created",
    type: "session.created",
    location: { directory: "/work/peon-extras" },
    data: {
      sessionID: "ses_root",
      title: "Review the adapter",
      location: { directory: "/work/peon-extras" },
    },
  })
  await adapter.handle({
    type: "session.execution.started",
    data: { sessionID: "ses_root" },
  })

  assert.deepEqual(emitted, [
    {
      hook_event_name: "UserPromptSubmit",
      session_id: "ses_root",
      cwd: "/work/peon-extras",
      title: "Review the adapter",
      source: "opencode",
    },
  ])
})

test("child sessions do not send prompt-submit sounds", async () => {
  const emitted = []
  const adapter = createOpenCodeEventAdapter({ emit: (event) => emitted.push(event) })

  await adapter.handle({
    type: "session.created",
    properties: {
      info: {
        id: "ses_child",
        parentID: "ses_root",
        title: "Subtask",
        location: { directory: "/work/peon-extras" },
      },
    },
  })
  await adapter.handle({
    type: "session.execution.started",
    data: { sessionID: "ses_child" },
  })

  assert.deepEqual(emitted, [])
})

test("each busy session transition sends a prompt-submit event", async () => {
  const emitted = []
  const adapter = createOpenCodeEventAdapter({ emit: (event) => emitted.push(event) })

  await adapter.handle({
    type: "session.created",
    properties: {
      info: { id: "ses_root", location: { directory: "/work/repo" } },
    },
  })
  await adapter.handle({
    type: "session.status",
    properties: { sessionID: "ses_root", status: { type: "busy" } },
  })
  await adapter.handle({
    type: "session.status",
    properties: { sessionID: "ses_root", status: { type: "idle" } },
  })
  await adapter.handle({
    type: "session.status",
    properties: { sessionID: "ses_root", status: { type: "busy" } },
  })

  assert.deepEqual(
    emitted.map((event) => event.hook_event_name),
    ["UserPromptSubmit", "UserPromptSubmit"],
  )
})

test("V2 execution lifecycle events emit prompt-submit and completion events", async () => {
  const emitted = []
  const adapter = createOpenCodeEventAdapter({
    emit: (event) => emitted.push(event),
    getMessages: async () => [
      { type: "assistant", content: [{ type: "text", text: "The lifecycle is working." }] },
    ],
  })

  await adapter.handle({
    type: "session.created",
    location: { directory: "/work/repo" },
    data: {
      id: "ses_root",
      title: "Lifecycle test",
      location: { directory: "/work/repo" },
    },
  })
  await adapter.handle({
    type: "session.execution.started",
    data: { sessionID: "ses_root" },
  })
  await adapter.handle({
    type: "session.execution.succeeded",
    data: { sessionID: "ses_root" },
  })

  assert.deepEqual(
    emitted.map(({ hook_event_name, session_id, cwd, title, message }) => ({
      hook_event_name,
      session_id,
      cwd,
      title,
      message,
    })),
    [
      {
        hook_event_name: "UserPromptSubmit",
        session_id: "ses_root",
        cwd: "/work/repo",
        title: "Lifecycle test",
        message: undefined,
      },
      {
        hook_event_name: "Stop",
        session_id: "ses_root",
        cwd: "/work/repo",
        title: "Lifecycle test",
        message: "The lifecycle is working.",
      },
    ],
  )
})

test("lazy plugin activation recovers session title and directory for V2 events", async () => {
  const emitted = []
  const lookups = []
  const adapter = createOpenCodeEventAdapter({
    emit: (event) => emitted.push(event),
    getSession: async (sessionID) => {
      lookups.push(sessionID)
      return {
        id: sessionID,
        title: "Existing session",
        location: { directory: "/work/already-open" },
      }
    },
    getMessages: async () => [],
  })

  await adapter.handle({
    type: "permission.asked",
    data: { sessionID: "ses_existing", action: "shell" },
  })
  await adapter.handle({
    type: "session.execution.started",
    data: { sessionID: "ses_existing" },
  })
  await adapter.handle({
    type: "session.execution.succeeded",
    data: { sessionID: "ses_existing" },
  })

  assert.deepEqual(lookups, ["ses_existing"])
  assert.deepEqual(
    emitted.map(({ hook_event_name, cwd, title }) => ({ hook_event_name, cwd, title })),
    [
      {
        hook_event_name: "PermissionRequest",
        cwd: "/work/already-open",
        title: "Existing session",
      },
      {
        hook_event_name: "UserPromptSubmit",
        cwd: "/work/already-open",
        title: "Existing session",
      },
      {
        hook_event_name: "Stop",
        cwd: "/work/already-open",
        title: "Existing session",
      },
    ],
  )
})

test("location-specific adapters only notify for sessions in their own location", async () => {
  const emittedByHome = []
  const emittedByWorktree = []
  const session = {
    id: "ses_worktree",
    title: "Worktree task",
    location: { directory: "/work/cursor-worktree" },
  }
  const options = {
    getSession: async () => session,
    getMessages: async () => [],
  }
  const homeAdapter = createOpenCodeEventAdapter({
    ...options,
    locationDirectory: "/Users/benoit",
    emit: (event) => emittedByHome.push(event),
  })
  const worktreeAdapter = createOpenCodeEventAdapter({
    ...options,
    locationDirectory: "/work/cursor-worktree",
    emit: (event) => emittedByWorktree.push(event),
  })
  const events = [
    {
      type: "session.created",
      location: { directory: "/work/cursor-worktree" },
      data: {
        id: session.id,
        title: session.title,
        location: session.location,
      },
    },
    { type: "session.execution.started", data: { sessionID: session.id } },
    { type: "session.execution.succeeded", data: { sessionID: session.id } },
  ]

  for (const event of events) {
    await homeAdapter.handle(event)
    await worktreeAdapter.handle(event)
  }

  assert.deepEqual(emittedByHome, [])
  assert.deepEqual(
    emittedByWorktree.map(({ hook_event_name }) => hook_event_name),
    ["UserPromptSubmit", "Stop"],
  )
})

test("V2 execution failures map to errors without a duplicate completion event", async () => {
  const emitted = []
  const adapter = createOpenCodeEventAdapter({
    emit: (event) => emitted.push(event),
    getSession: async (sessionID) => ({ id: sessionID, location: { directory: "/work/repo" } }),
  })

  await adapter.handle({
    type: "session.execution.failed",
    data: { sessionID: "ses_failed", error: { message: "Provider request failed" } },
  })
  await adapter.handle({
    type: "session.execution.succeeded",
    data: { sessionID: "ses_failed" },
  })

  assert.deepEqual(
    emitted.map(({ hook_event_name, error }) => ({ hook_event_name, error })),
    [{ hook_event_name: "PostToolUseFailure", error: "Provider request failed" }],
  )
})

test("an idle root session sends the latest assistant excerpt", async () => {
  const emitted = []
  const adapter = createOpenCodeEventAdapter({
    emit: (event) => emitted.push(event),
    getMessages: async () => [
      {
        type: "assistant",
        content: [
          {
            type: "text",
            text: "```ts\nconst answer = 42\n```\n\nThe task is complete.",
          },
        ],
      },
    ],
  })

  await adapter.handle({
    type: "session.created",
    properties: {
      info: {
        id: "ses_root",
        title: "Review",
        location: { directory: "/work/repo" },
      },
    },
  })
  await adapter.handle({
    type: "session.idle",
    properties: { sessionID: "ses_root" },
  })

  assert.equal(emitted.at(-1).hook_event_name, "Stop")
  assert.equal(emitted.at(-1).message, "The task is complete.")
})

test("questions, permission requests, and session errors map to Peon events", async () => {
  const emitted = []
  const adapter = createOpenCodeEventAdapter({ emit: (event) => emitted.push(event) })

  await adapter.handle({
    type: "session.created",
    properties: {
      info: {
        id: "ses_root",
        title: "Review",
        location: { directory: "/work/repo" },
      },
    },
  })
  await adapter.handle({
    type: "question.asked",
    properties: {
      id: "question-1",
      sessionID: "ses_root",
      questions: [{ question: "Which option should I use?" }],
    },
  })
  await adapter.handle({
    type: "permission.asked",
    properties: {
      id: "permission-1",
      sessionID: "ses_root",
      action: "shell",
    },
  })
  await adapter.handle({
    type: "session.error",
    properties: {
      sessionID: "ses_root",
      error: { message: "Model request failed" },
    },
  })

  assert.deepEqual(
    emitted.map(({ hook_event_name, message, tool_name, error }) => ({
      hook_event_name,
      message,
      tool_name,
      error,
    })),
    [
      {
        hook_event_name: "Notification",
        message: "Which option should I use?",
        tool_name: "request_user_input",
        error: undefined,
      },
      {
        hook_event_name: "PermissionRequest",
        message: undefined,
        tool_name: "shell",
        error: undefined,
      },
      {
        hook_event_name: "PostToolUseFailure",
        message: undefined,
        tool_name: "Bash",
        error: "Model request failed",
      },
    ],
  )
})

test("compaction hooks send before and after Peon banner events", async () => {
  const emitted = []
  const adapter = createOpenCodeEventAdapter({
    emit: (event) => emitted.push(event),
    getCompactionUsage: async (_sessionID, _messages, stage) =>
      stage === "before"
        ? { context_tokens: 90_000, context_window_size: 100_000 }
        : { context_tokens: 12_000, context_window_size: 100_000 },
  })

  await adapter.handle({
    type: "session.created",
    properties: {
      info: {
        id: "ses_root",
        title: "Review",
        location: { directory: "/work/repo" },
      },
    },
  })
  await adapter.beforeCompaction({ sessionID: "ses_root", messages: [] })
  await adapter.handle({
    type: "session.compacted",
    properties: { sessionID: "ses_root" },
  })

  assert.deepEqual(
    emitted.map(({ hook_event_name, context_tokens, context_window_size }) => ({
      hook_event_name,
      context_tokens,
      context_window_size,
    })),
    [
      {
        hook_event_name: "PreCompact",
        context_tokens: 90_000,
        context_window_size: 100_000,
      },
      {
        hook_event_name: "PostCompact",
        context_tokens: 12_000,
        context_window_size: 100_000,
      },
    ],
  )
})
