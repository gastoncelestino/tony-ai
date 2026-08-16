/**
 * Normalized observation of an OpenCode tool execution.
 *
 * This module deliberately does not execute, authorize, or interpret a tool.
 * It only gives Kernel a stable shape for the data exposed by the OpenCode
 * before/after hook boundary.
 */

export interface ToolExecutionObservation {
  tool: string
  task_id: string | null
  arguments: Record<string, unknown>
  result: unknown
  success: boolean | null
  error: string | null
}

export interface ToolExecutionInput {
  sessionID: string
  tool: string
  arguments: Record<string, unknown>
}

function readBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null
}

function readError(value: unknown): string | null {
  if (typeof value === "string") return value
  if (value instanceof Error) return value.message
  if (value && typeof value === "object") {
    const error = (value as Record<string, unknown>).error
    if (typeof error === "string") return error
    if (error instanceof Error) return error.message
  }
  return null
}

function readTaskId(argumentsObject: Record<string, unknown>): string | null {
  const taskId = argumentsObject.task_id
  return typeof taskId === "string" && taskId.length > 0 ? taskId : null
}

/**
 * Normalize the payload delivered by OpenCode's tool.execute.after hook.
 *
 * Success is intentionally nullable: not every tool result has a stable
 * success flag, and the adapter must not manufacture evidence from an
 * unknown result shape.
 *
 * Task identity is intentionally strict: only an explicit `task_id` argument
 * can establish a graph link. Session ids, phases, tool names, and inferred
 * context are never treated as task identity.
 */
export function observeToolExecution(
  input: ToolExecutionInput,
  result: unknown,
): ToolExecutionObservation {
  const resultObject = result && typeof result === "object"
    ? result as Record<string, unknown>
    : null

  return {
    tool: input.tool,
    task_id: readTaskId(input.arguments),
    arguments: { ...input.arguments },
    result,
    success: readBoolean(resultObject?.success),
    error: readError(resultObject?.error),
  }
}
