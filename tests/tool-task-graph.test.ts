import { expect, test } from "bun:test"
import {
  __setKernelClientForTests,
  taskExecuteAfterHook,
  type KernelClientLike,
} from "../plugins/tony-kernel/index"

type CompletedTask = {
  taskId: string
  evidence: unknown[]
}

function client(completed: CompletedTask[], allowed = true): KernelClientLike {
  return {
    canStartPhase: async () => ({
      decision: "proceed",
      allowed: true,
      reason: "ok",
      current_phase: "apply",
      requested_phase: "apply",
      missing_artifacts: [],
      missing_evidence: [],
      scope_violations: [],
      retry_status: null,
      next_action: null,
    }),
    recordDelegation: async () => {},
    completeTask: async (taskId, evidence) => {
      completed.push({ taskId, evidence })
      return {
        decision: allowed ? "proceed" : "block_evidence_required",
        allowed,
        reason: allowed ? "task completed" : "evidence rejected",
        missing_artifacts: [],
        missing_evidence: allowed ? [] : ["valid evidence"],
      }
    },
    recordPhaseCompletion: async () => ({
      decision: "phase_complete",
      allowed: true,
      reason: "ok",
      missing_artifacts: [],
      missing_evidence: [],
    }),
    checkScope: async () => ({
      decision: "proceed",
      allowed: true,
      reason: "ok",
      scope_violations: [],
    }),
    getStatus: async () => ({ current_phase: "apply" }),
  }
}

test("links task-scoped tool evidence to Kernel task completion", async () => {
  const completed: CompletedTask[] = []
  __setKernelClientForTests(client(completed))

  await taskExecuteAfterHook(
    {
      sessionID: "session-1",
      tool: "bash",
      arguments: { task_id: "task-1", command: "echo ok" },
    },
    { success: true },
  )

  expect(completed).toHaveLength(1)
  expect(completed[0]?.taskId).toBe("task-1")
  expect(completed[0]?.evidence[0]).toMatchObject({
    type: "command",
    exit_code: 0,
  })

  __setKernelClientForTests(null)
})

test("does not link tool observations without an explicit task id", async () => {
  const completed: CompletedTask[] = []
  __setKernelClientForTests(client(completed))

  await taskExecuteAfterHook(
    {
      sessionID: "session-2",
      tool: "bash",
      arguments: { command: "echo ok" },
    },
    { success: true },
  )

  expect(completed).toHaveLength(0)

  __setKernelClientForTests(null)
})

test("keeps failed task evidence governed by the Kernel", async () => {
  const completed: CompletedTask[] = []
  __setKernelClientForTests(client(completed, false))

  await expect(taskExecuteAfterHook(
    {
      sessionID: "session-3",
      tool: "bash",
      arguments: { task_id: "task-1", command: "false" },
    },
    { success: false, error: "command failed" },
  )).rejects.toThrow("Task completion rejected")

  expect(completed[0]?.evidence[0]).toMatchObject({
    type: "command",
    exit_code: 1,
  })

  __setKernelClientForTests(null)
})
