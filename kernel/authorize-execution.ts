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

  return { allowed: true, reason: "task_delegation_authorized" }
}
