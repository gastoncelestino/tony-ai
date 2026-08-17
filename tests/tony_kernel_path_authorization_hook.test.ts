import { describe, expect, test } from "bun:test"
import {
  __setKernelClientForTests,
  KernelBlockedError,
  taskExecuteBeforeHook,
  type KernelClientLike,
} from "../plugins/tony-kernel/index"

function fakeClient(allowedPath: boolean): KernelClientLike {
  return {
    authorizeTool: async () => ({ allowed: true, reason: "tool allowed" }),
    authorizeCommand: async () => ({ allowed: true, reason: "command allowed" }),
    authorizePath: async () => ({
      allowed: allowedPath,
      reason: allowedPath ? "path allowed" : "path denied",
    }),
    canStartPhase: async () => ({
      decision: "proceed", allowed: true, reason: "ok",
      current_phase: "apply", requested_phase: "apply",
      missing_artifacts: [], missing_evidence: [], scope_violations: [],
      retry_status: null, next_action: null,
    }),
    recordDelegation: async () => {},
    completeTask: async () => ({ decision: "proceed", allowed: true, reason: "ok", missing_artifacts: [], missing_evidence: [] }),
    recordPhaseCompletion: async () => ({ decision: "proceed", allowed: true, reason: "ok", missing_artifacts: [], missing_evidence: [] }),
    checkScope: async () => ({ decision: "proceed", allowed: true, reason: "ok", scope_violations: [] }),
    getStatus: async () => ({ current_phase: "apply" }),
  }
}

describe("Tony Kernel path authorization boundary", () => {
  test("allows an explicitly provided path", async () => {
    __setKernelClientForTests(fakeClient(true))
    await expect(taskExecuteBeforeHook(
      { sessionID: "session-1", tool: "edit", arguments: { filePath: "src/app.ts" } },
      { success: true },
    )).resolves.toBeUndefined()
  })

  test("blocks an explicitly provided denied path", async () => {
    __setKernelClientForTests(fakeClient(false))
    await expect(taskExecuteBeforeHook(
      { sessionID: "session-1", tool: "write", arguments: { filePath: "secrets/key.pem" } },
      { success: true },
    )).rejects.toBeInstanceOf(KernelBlockedError)
  })
})
