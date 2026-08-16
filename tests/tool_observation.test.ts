import { expect, test } from "bun:test"
import { observeToolExecution } from "../plugins/tony-kernel/tool-observation"

test("binds an observation only to an explicit task_id", () => {
  const observation = observeToolExecution(
    {
      sessionID: "session-1",
      tool: "bash",
      arguments: {
        task_id: "task-42",
        command: "pytest",
      },
    },
    { success: true },
  )

  expect(observation.task_id).toBe("task-42")
})

test("does not infer task identity from session or other arguments", () => {
  const observation = observeToolExecution(
    {
      sessionID: "session-1",
      tool: "bash",
      arguments: {
        phase: "apply",
        command: "pytest",
      },
    },
    { success: true },
  )

  expect(observation.task_id).toBeNull()
})

test("rejects an empty task_id as an implicit binding", () => {
  const observation = observeToolExecution(
    {
      sessionID: "session-1",
      tool: "bash",
      arguments: {
        task_id: "",
      },
    },
    { success: true },
  )

  expect(observation.task_id).toBeNull()
})
