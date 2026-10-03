import assert from "node:assert/strict"
import test from "node:test"

import {
  compactionUsage,
  compactionUsageForSession,
} from "../opencode/usage.mjs"

test("compaction usage falls back to session model metadata when needed", async () => {
  const usage = await compactionUsage(
    {
      model: { id: "gpt-6-luna", providerID: "github-copilot", variant: "high" },
    },
    [
      {
        info: {
          role: "assistant",
          tokens: { input: 80_000, cache: { read: 10_000 } },
        },
      },
    ],
    async () => [
      {
        id: "gpt-6-luna",
        providerID: "github-copilot",
        limit: { context: 100_000 },
      },
    ],
  )

  assert.deepEqual(usage, {
    context_tokens: 90_000,
    context_window_size: 100_000,
    context_usage_percent: 90,
  })
})

test("compaction usage resolves model metadata from the latest assistant message", async () => {
  const usage = await compactionUsage(
    { id: "ses_root", title: "Quick check-in" },
    [
      {
        info: {
          role: "assistant",
          providerID: "github-copilot",
          modelID: "gpt-6-luna",
          tokens: { input: 80_000, cache: { read: 10_000 } },
        },
      },
    ],
    async () => [
      {
        id: "gpt-6-luna",
        providerID: "github-copilot",
        limit: { context: 100_000 },
      },
    ],
  )

  assert.deepEqual(usage, {
    context_tokens: 90_000,
    context_window_size: 100_000,
    context_usage_percent: 90,
  })
})

test("compaction usage reads the OpenCode V2 session and assistant model references", async () => {
  const usage = await compactionUsage(
    {
      data: {
        model: { id: "gpt-6-luna", providerID: "github-copilot" },
      },
    },
    {
      data: [
        {
          type: "assistant",
          model: { id: "gpt-6-luna", providerID: "github-copilot" },
          tokens: { input: 80_000, cache: { read: 10_000 } },
        },
      ],
    },
    async () => ({
      location: { directory: "/work/repo" },
      data: [
        {
          id: "gpt-6-luna",
          providerID: "github-copilot",
          limit: { context: 100_000 },
        },
      ],
    }),
  )

  assert.deepEqual(usage, {
    context_tokens: 90_000,
    context_window_size: 100_000,
    context_usage_percent: 90,
  })
})

test("compaction usage falls back to stored history when hook messages lack token metadata", async () => {
  const usage = await compactionUsage(
    {
      data: {
        model: { id: "gpt-6-luna", providerID: "github-copilot" },
      },
    },
    [{ role: "assistant" }],
    async () => ({
      data: [
        {
          id: "gpt-6-luna",
          providerID: "github-copilot",
          limit: { context: 100_000 },
        },
      ],
    }),
    {
      data: [
        {
          type: "assistant",
          model: { id: "gpt-6-luna", providerID: "github-copilot" },
          tokens: { input: 80_000, cache: { read: 10_000 } },
        },
      ],
    },
  )

  assert.deepEqual(usage, {
    context_tokens: 90_000,
    context_window_size: 100_000,
    context_usage_percent: 90,
  })
})

test("plugin compaction usage falls back to stored context when hook messages lack usage", async () => {
  const usage = await compactionUsageForSession(
    "ses_root",
    [{ role: "assistant" }],
    "before",
    {
      getSession: async () => ({
        data: {
          model: { id: "gpt-6-luna", providerID: "github-copilot" },
        },
      }),
      getMessages: async () => ({
        data: [
          {
            type: "assistant",
            model: { id: "gpt-6-luna", providerID: "github-copilot" },
            tokens: { input: 80_000, cache: { read: 10_000 } },
          },
        ],
      }),
      listModels: async () => ({
        data: [
          {
            id: "gpt-6-luna",
            providerID: "github-copilot",
            limit: { context: 100_000 },
          },
        ],
      }),
    },
  )

  assert.deepEqual(usage, {
    context_tokens: 90_000,
    context_window_size: 100_000,
    context_usage_percent: 90,
  })
})

test("plugin compaction usage formats completed summary output against its model window", async () => {
  const usage = await compactionUsageForSession(
    "ses_root",
    [{ role: "assistant" }],
    "after",
    {
      getSession: async () => ({
        data: {
          model: { id: "gpt-6-luna", providerID: "github-copilot" },
        },
      }),
      getMessages: async () => ({
        data: [
          {
            type: "compaction",
            status: "completed",
            model: { id: "gpt-6-luna", providerID: "github-copilot" },
            tokens: {
              input: 80_000,
              output: 96,
              reasoning: 0,
              cache: { read: 10_000, write: 0 },
            },
          },
        ],
      }),
      listModels: async () => ({
        data: [
          {
            id: "gpt-6-luna",
            providerID: "github-copilot",
            limit: { context: 175_000 },
          },
        ],
      }),
    },
  )

  assert.deepEqual(usage, {
    context_tokens: 96,
    context_window_size: 175_000,
    context_usage_percent: (96 / 175_000) * 100,
  })
})

test("post-compaction assistant usage takes precedence over summary output", async () => {
  const usage = await compactionUsage(
    { model: { id: "gpt-6-luna", providerID: "github-copilot" } },
    {
      data: [
        {
          type: "compaction",
          status: "completed",
          tokens: { output: 8_900 },
        },
        {
          type: "assistant",
          model: { id: "gpt-6-luna", providerID: "github-copilot" },
          tokens: { input: 12_000, cache: { read: 0 } },
        },
      ],
    },
    async () => ({
      data: [
        {
          id: "gpt-6-luna",
          providerID: "github-copilot",
          limit: { context: 100_000 },
        },
      ],
    }),
    undefined,
    "after",
  )

  assert.deepEqual(usage, {
    context_tokens: 12_000,
    context_window_size: 100_000,
    context_usage_percent: 12,
  })
})
