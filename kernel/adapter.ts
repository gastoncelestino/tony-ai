import { isKernelContext, type KernelBoundaryRequest } from "./protocol"

type AdapterResult =
  | { kind: "ready"; request: KernelBoundaryRequest }
  | { kind: "unavailable"; reason: string }
  | { kind: "ignored" }

export function adaptTaskExecutionContext(
  input: { tool: string; arguments: Record<string, unknown> },
  context: unknown,
): AdapterResult {
  if (input.tool.toLowerCase() !== "task") return { kind: "ignored" }
  if (!isKernelContext(context)) return { kind: "unavailable", reason: "Kernel execution context is incomplete" }

  if (input.arguments.task_id !== undefined) {
    return {
      kind: "unavailable",
      reason: "task_id is not allowed for Tony Kernel task execution; child sessions must not be reused",
    }
  }

  if (input.arguments.background === true) {
    return {
      kind: "unavailable",
      reason: "background=true is not allowed for Tony Kernel task execution; tasks must complete synchronously",
    }
  }

  const description = input.arguments.description
  if (typeof description !== "string" || !description.trim()) {
    return { kind: "unavailable", reason: "Task description is required for Kernel authorization" }
  }
  return { kind: "ready", request: { ...context, requested_description: description.trim() } }
}
