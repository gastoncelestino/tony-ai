export type KernelTask = {
  id: string
  description: string
  phase: string
  dependencies: string[]
}

export type KernelBoundaryRequest = {
  phase: string
  status: string
  tasks: KernelTask[]
  completed: string[]
}

type AdapterResult =
  | { kind: "ready"; request: KernelBoundaryRequest }
  | { kind: "unavailable"; reason: string }
  | { kind: "ignored" }

function isTask(value: unknown): value is KernelTask {
  if (!value || typeof value !== "object") return false
  const task = value as Record<string, unknown>
  return (
    typeof task.id === "string" &&
    typeof task.description === "string" &&
    typeof task.phase === "string" &&
    Array.isArray(task.dependencies) &&
    task.dependencies.every((dependency) => typeof dependency === "string")
  )
}

function isKernelContext(value: unknown): value is KernelBoundaryRequest {
  if (!value || typeof value !== "object") return false
  const context = value as Record<string, unknown>
  return (
    typeof context.phase === "string" &&
    typeof context.status === "string" &&
    Array.isArray(context.tasks) &&
    context.tasks.every(isTask) &&
    Array.isArray(context.completed) &&
    context.completed.every((taskID) => typeof taskID === "string")
  )
}

export function adaptTaskExecutionContext(
  input: { sessionID: string; tool: string },
  context: unknown,
): AdapterResult {
  if (input.tool !== "Task") return { kind: "ignored" }

  if (!isKernelContext(context)) {
    return {
      kind: "unavailable",
      reason: "Kernel execution context is incomplete",
    }
  }

  return {
    kind: "ready",
    request: context,
  }
}
