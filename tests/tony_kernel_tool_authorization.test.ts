import { describe, expect, test } from "bun:test"
import {
  __setKernelClientForTests,
  KernelBlockedError,
  taskExecuteBeforeHook,
  type KernelClientLike,
} from "../plugins/tony-kernel/index"

function fakeClient(allowed: boolean): KernelClientLike {
  return {
    authorizeTool: async () => ({
      allowed,
      reason: allowed ? "allowed by runtime policy" : "tool is not permitted",
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

describe("Tony Kernel tool authorization boundary", () => {
  test("allows a tool when Kernel authorization allows it", async () => {
    __setKernelClientForTests(fakeClient(true))

    await expect(
      taskExecuteBeforeHook(
        { sessionID: "session-1", tool: "bash", arguments: { command: "echo ok" } },
        { success: true },
      ),
    ).resolves.toBeUndefined()
  })

  test("blocks a tool when Kernel authorization denies it", async () => {
    __setKernelClientForTests(fakeClient(false))

    await expect(
      taskExecuteBeforeHook(
        { sessionID: "session-1", tool: "bash", arguments: { command: "echo blocked" } },
        { success: true },
      ),
    ).rejects.toBeInstanceOf(KernelBlockedError)
  })

  test("does not require phase derivation for non-Task tools", async () => {
    __setKernelClientForTests(fakeClient(true))

    await expect(
      taskExecuteBeforeHook(
        { sessionID: "session-1", tool: "edit", arguments: { filePath: "src/app.ts" } },
        { success: true },
      ),
    ).resolves.toBeUndefined()
  })
})
