import { expect, test } from "bun:test"
import { observationToEvidence } from "../plugins/tony-kernel/tool-evidence"
import type { ToolExecutionObservation } from "../plugins/tony-kernel/tool-observation"

const observation = (
  overrides: Partial<ToolExecutionObservation> = {},
): ToolExecutionObservation => ({
  tool: "bash",
  task_id: "task-1",
  arguments: { command: "echo ok" },
  result: { success: true },
  success: true,
  error: null,
  ...overrides,
})

test("maps a successful task-linked observation to Kernel evidence", () => {
  const evidence = observationToEvidence(observation())

  expect(evidence?.task_id).toBe("task-1")
  expect(evidence?.evidence.type).toBe("command")
  expect(evidence?.evidence.exit_code).toBe(0)
  expect(evidence?.evidence.claim).toContain("completed successfully")
  expect(evidence?.evidence.metadata.tool).toBe("bash")
})

test("does not create evidence without an explicit task link", () => {
  expect(observationToEvidence(observation({ task_id: null }))).toBeNull()
})

test("does not create evidence when the outcome is unknown", () => {
  expect(observationToEvidence(observation({ success: null }))).toBeNull()
})

test("preserves failure evidence when task identity is explicit", () => {
  const evidence = observationToEvidence(observation({
    success: false,
    result: { success: false },
    error: "command failed",
  }))

  expect(evidence?.task_id).toBe("task-1")
  expect(evidence?.evidence.exit_code).toBe(1)
  expect(evidence?.evidence.metadata.error).toBe("command failed")
})
