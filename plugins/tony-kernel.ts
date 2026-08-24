/**
 * Tony Kernel Plugin — OpenCode adapter.
 *
 * The plugin is intentionally kept thin: OpenCode events belong here;
 * Kernel policy and execution decisions belong in the Kernel.
 *
 * The legacy Python CLI/orchestrator bridge was removed while the new
 * Kernel execution boundary is being rebuilt. Until that boundary exists,
 * Task execution fails closed rather than falling back to legacy behavior.
 */

import type { Plugin } from "@opencode-ai/plugin"

export class KernelBlockedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelBlockedError"
  }
}

export class KernelUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelUnavailableError"
  }
}

export interface ExecutionRequest {
  sessionID: string
  tool: string
  arguments: Record<string, unknown>
}

/**
 * Extract only the execution identity carried by the OpenCode Task event.
 * This is transport parsing, not Kernel policy.
 */
export function executionRequest(input: ExecutionRequest): ExecutionRequest {
  return {
    sessionID: input.sessionID,
    tool: input.tool,
    arguments: input.arguments,
  }
}

/**
 * Temporary fail-closed boundary.
 *
 * The next Kernel phase will replace this with the real Kernel authorization
 * call returning an ExecutionOrder. Keeping the boundary explicit prevents
 * the plugin from silently retaining the removed legacy orchestration path.
 */
export async function authorizeExecution(
  input: ExecutionRequest
): Promise<never> {
  if (input.tool !== "Task") {
    throw new KernelUnavailableError(
      "[Tony Kernel] Execution authorization is not implemented for this runtime boundary"
    )
  }

  throw new KernelUnavailableError(
    "[Tony Kernel] Task execution blocked: new Kernel execution boundary is not wired yet"
  )
}

export async function taskExecuteBeforeHook(
  input: ExecutionRequest,
  _output: unknown
): Promise<void> {
  console.error("[TONY DEBUG] tool.execute.before", {
    tool: input.tool,
    sessionID: input.sessionID,
    arguments: input.arguments,
  })

  if (input.tool !== "Task") return

  await authorizeExecution(executionRequest(input))
}

const TonyKernelPlugin: Plugin = {
  name: "tony-kernel",
  version: "2.0.0",
  description: "Tony Kernel — thin OpenCode execution boundary",

  hooks: {
    "tool.execute.before": taskExecuteBeforeHook,
  },

  async onLoad() {
    console.log("[tony-kernel] Plugin loaded; execution boundary is fail-closed")
  },
}

export default TonyKernelPlugin
