import { describe, expect, test } from "bun:test"
import { observeToolExecution } from "../plugins/tony-kernel/tool-observation"

describe("tool execution observation", () => {
  test("preserves the tool and arguments from the OpenCode hook", () => {
    const observation = observeToolExecution(
      {
        sessionID: "session-1",
        tool: "bash",
        arguments: { command: "printf 'ok'", workdir: "/repo" },
      },
      { success: true, output: "ok" },
    )

    expect(observation.tool).toBe("bash")
    expect(observation.arguments).toEqual({
      command: "printf 'ok'",
      workdir: "/repo",
    })
  })

  test("preserves an explicit success result", () => {
    const observation = observeToolExecution(
      { sessionID: "session-1", tool: "bash", arguments: {} },
      { success: true, output: "ok" },
    )

    expect(observation.success).toBe(true)
    expect(observation.error).toBeNull()
    expect(observation.result).toEqual({ success: true, output: "ok" })
  })

  test("does not invent success when the result shape is unknown", () => {
    const observation = observeToolExecution(
      { sessionID: "session-1", tool: "read", arguments: { path: "README.md" } },
      "file contents",
    )

    expect(observation.success).toBeNull()
    expect(observation.error).toBeNull()
    expect(observation.result).toBe("file contents")
  })

  test("captures an explicit tool error without interpreting other output", () => {
    const observation = observeToolExecution(
      { sessionID: "session-1", tool: "bash", arguments: { command: "false" } },
      { success: false, error: "command failed", exitCode: 1 },
    )

    expect(observation.success).toBe(false)
    expect(observation.error).toBe("command failed")
    expect(observation.result).toEqual({
      success: false,
      error: "command failed",
      exitCode: 1,
    })
  })
})
