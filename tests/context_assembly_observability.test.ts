import { expect, test } from "bun:test"
import { resolve } from "node:path"

import { ContextAssembly } from "../plugins/context-assembly"

const ROOT = resolve(import.meta.dir, "..")
const CODE = {
  type: "project_code",
  path: "src/foo.py",
  start_line: 42,
  end_line: 58,
  text: "def foo():\n    return 42",
  lang: "python",
  score: 0.9,
}

test("context assembly logs cumulative accepted context characters per session", async () => {
  const logs: Array<{ body: Record<string, unknown> }> = []
  const client = {
    app: {
      log: async (request: { body: Record<string, unknown> }) => {
        logs.push(request)
      },
    },
  }

  const hooks = ContextAssembly({ worktree: ROOT, client })

  await hooks["tool.execute.after"](
    { tool: "code-index_code_search", sessionID: "session-A" },
    { output: "", metadata: { project_code: [CODE] } },
  )
  const firstOutput = { system: ["task"] }
  await hooks["experimental.chat.system.transform"]({ sessionID: "session-A" }, firstOutput)

  await hooks["tool.execute.after"](
    { tool: "code-index_code_search", sessionID: "session-A" },
    { output: "", metadata: { project_code: [{ ...CODE, path: "src/bar.py" }] } },
  )
  const secondOutput = { system: ["task"] }
  await hooks["experimental.chat.system.transform"]({ sessionID: "session-A" }, secondOutput)

  expect(logs).toHaveLength(2)
  expect(logs[0].body).toMatchObject({
    service: "context-assembly",
    message: "accepted context characters",
    extra: { sessionID: "session-A", accepted_context_chars: expect.any(Number) },
  })
  expect(logs[1].body).toMatchObject({
    service: "context-assembly",
    message: "accepted context characters",
    extra: { sessionID: "session-A", accepted_context_chars: expect.any(Number) },
  })

  const firstChars = (logs[0].body.extra as { accepted_context_chars: number }).accepted_context_chars
  const secondChars = (logs[1].body.extra as { accepted_context_chars: number }).accepted_context_chars
  expect(firstChars).toBeGreaterThan(0)
  expect(secondChars).toBeGreaterThan(firstChars)
})
