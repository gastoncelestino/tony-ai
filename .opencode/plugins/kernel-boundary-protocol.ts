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
  requested_description?: string
}

export type KernelExecutionOrder = {
  task_id: string
  description: string
  phase: string
  files: string[]
}

export type KernelBoundaryResponse =
  | {
      allowed: true
      decision: "proceed"
      reason: string
      execution_order: KernelExecutionOrder
    }
  | {
      allowed: false
      decision: "blocked"
      reason: string
      execution_order?: null
    }

export function encodeKernelBoundaryRequest(
  request: KernelBoundaryRequest,
): string {
  return JSON.stringify(request)
}

export function decodeKernelBoundaryResponse(
  payload: string,
): KernelBoundaryResponse {
  const value: unknown = JSON.parse(payload)
  if (!isKernelBoundaryResponse(value)) {
    throw new Error("Invalid Kernel boundary response")
  }
  return value
}

function isKernelBoundaryResponse(
  value: unknown,
): value is KernelBoundaryResponse {
  if (!value || typeof value !== "object") return false
  const response = value as Record<string, unknown>

  if (response.allowed === false) {
    return response.decision === "blocked" && typeof response.reason === "string"
  }

  if (response.allowed !== true || response.decision !== "proceed") return false
  if (typeof response.reason !== "string") return false
  if (!response.execution_order || typeof response.execution_order !== "object") return false

  const order = response.execution_order as Record<string, unknown>
  return (
    typeof order.task_id === "string" &&
    typeof order.description === "string" &&
    typeof order.phase === "string" &&
    Array.isArray(order.files) &&
    order.files.every((file) => typeof file === "string")
  )
}
