export type KernelDecision = {
  allowed: boolean
  reason: string
}

export type AuthorizeExecutionInput = {
  tool: string
  sessionID: string
  callID: string
  subagent?: string
}

// Task delegation is currently governed by the kernel only when it targets
// an explicit execution phase. The existing explore flow is the first
// governed phase; other Task targets must not silently bypass the kernel.
const GOVERNED_TASK_AGENTS = new Set(["explore"])

/**
 * Kernel execution policy for delegated Task calls.
 *
 * This is intentionally deterministic and side-effect free. The OpenCode
 * plugin is responsible for emitting KERNEL_INTERCEPT/KERNEL_DECISION and
 * enforcing the returned decision before TOOL_EXECUTE_START.
 */
export async function authorizeExecution(
  input: AuthorizeExecutionInput,
): Promise<KernelDecision> {
  if (input.tool !== "task") {
    return { allowed: true, reason: "not_task" }
  }

  if (!input.subagent) {
    return { allowed: false, reason: "missing_subagent" }
  }

  if (!GOVERNED_TASK_AGENTS.has(input.subagent)) {
    return { allowed: false, reason: "subagent_not_governed" }
  }

  return { allowed: true, reason: "task_delegation_authorized" }
}
