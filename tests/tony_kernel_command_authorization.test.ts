import { describe, expect, test } from "bun:test"
import {
  __setKernelClientForTests,
  KernelBlockedError,
  taskExecuteBeforeHook,
  type KernelClientLike,
} from "../plugins/tony-kernel/index"

function fakeClient(commandAllowed: boolean): KernelClientLike {
  return {
    authorizeTool: async () => ({ allowed: true, reason: "tool allowed" }),
    authorizeCommand: async () => ({
      allowed: commandAllowed,
      reason: commandAllowed ? "command allowed" : "command denied",
    }),
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
    completeTask: async () => ({
      decision: "proceed",
      allowed: true,
      reason: "ok",
      missing_artifacts: [],
      missing_evidence: [],
    }),
    recordPhaseCompletion: async () => ({
      decision: "proceed",
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

describe("Tony Kernel command authorization boundary", () => {
  test("allows bash when the command is authorized", async () => {
    __setKernelClientForTests(fakeClient(true))

    await expect(
      taskExecuteBeforeHook(
        {
          sessionID: "session-1",
          tool: "bash",
          arguments: { command: "git status" },
        },
        { success: true },
      ),
    ).resolves.toBeUndefined()
  })

  test("blocks bash when the command is denied", async () => {
    __setKernelClientForTests(fakeClient(false))

    await expect(
      taskExecuteBeforeHook(
        {
          sessionID: "session-1",
          tool: "bash",
          arguments: { command: "rm -rf /" },
        },
        { success: true },
      ),
    ).rejects.toBeInstanceOf(KernelBlockedError)
  })
})
