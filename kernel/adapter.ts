import type { KernelBoundaryRequest, KernelTask } from "./protocol"

type AdapterResult =
  | { kind: "ready"; request: KernelBoundaryRequest }
  | { kind: "unavailable"; reason: string }
  | { kind: "ignored" }

function isTask(value: unknown): value is KernelTask {
  if (!value || typeof value !== "object") return false
  const task = value as Record<string, unknown>
  return typeof task.id === "string" && typeof task.description === "string" &&
    typeof task.phase === "string" && Array.isArray(task.dependencies) &&
    task.dependencies.every((dependency) => typeof dependency === "string")
}

function isContext(value: unknown): value is Omit<KernelBoundaryRequest, "requested_description"> {
  if (!value || typeof value !== "object") return false
  const context = value as Record<string, unknown>
  return typeof context.phase === "string" && typeof context.status === "string" &&
    Array.isArray(context.tasks) && context.tasks.every(isTask) &&
    Array.isArray(context.completed) && context.completed.every((id) => typeof id === "string")
}

export function adaptTaskExecutionContext(
  input: { tool: string; arguments: Record<string, unknown> },
  context: unknown,
): AdapterResult {
  if (input.tool.toLowerCase() !== "task") return { kind: "ignored" }
  if (!isContext(context)) return { kind: "unavailable", reason: "Kernel execution context is incomplete" }
  const description = input.arguments.description
  if (typeof description !== "string" || !description.trim()) {
    return { kind: "unavailable", reason: "Task description is required for Kernel authorization" }
  }
  return { kind: "ready", request: { ...context, requested_description: description.trim() } }
}
