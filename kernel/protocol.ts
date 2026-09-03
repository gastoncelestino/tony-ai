export const KERNEL_PHASES = ["explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive"] as const
export type KernelPhase = (typeof KERNEL_PHASES)[number]

export type KernelTask = { id: string; description: string; phase: KernelPhase; dependencies: string[]; files?: string[] }
export type KernelContext = { phase: string; status: string; tasks: KernelTask[]; completed: string[] }

export type KernelContextRequest = { operation: "get_context"; project_directory: string; session_id: string }
export type KernelContextResponse =
  | { available: true; context: KernelContext }
  | { available: false; reason: string }

export type KernelActionPlan =
  | { action: "delegate"; phase: KernelPhase; task_id: string; agent: string; objective: string; files: string[]; allowed_tools: string[]; max_iterations: number }
  | { action: "done"; reason: string }
export type KernelActionRequest = { operation: "next_action"; project_directory: string; session_id: string }
export type KernelActionResponse = { available: true; plan: KernelActionPlan } | { available: false; reason: string }

export type KernelCommandRequest =
  | KernelContextRequest
  | KernelActionRequest
  | { operation: "prepare_bootstrap"; project_directory: string; session_id: string }
  | { operation: "complete_bootstrap"; project_directory: string; session_id: string; decomposition: string }
  | { operation: "complete_task"; project_directory: string; session_id: string; task_id: string; evidence: string }

export type KernelCommandResponse = { ok: true; result?: Record<string, unknown> } | { ok: false; reason: string }
export type KernelBoundaryRequest = KernelContext & { requested_description: string }
export type KernelExecutionOrder = { task_id: string; description: string; phase: KernelPhase; files: string[] }
export type KernelBoundaryResponse =
  | { allowed: true; decision: "proceed"; reason: string; execution_order: KernelExecutionOrder }
  | { allowed: false; decision: "blocked" | "done"; reason: string; execution_order: null }

export function isKernelTask(value: unknown): value is KernelTask { if (!value || typeof value !== "object") return false; const task = value as Record<string, unknown>; return typeof task.id === "string" && typeof task.description === "string" && typeof task.phase === "string" && KERNEL_PHASES.includes(task.phase as KernelPhase) && Array.isArray(task.dependencies) && task.dependencies.every((id) => typeof id === "string") && (task.files === undefined || (Array.isArray(task.files) && task.files.every((file) => typeof file === "string"))) }
export function isKernelContext(value: unknown): value is KernelContext { if (!value || typeof value !== "object") return false; const context = value as Record<string, unknown>; return typeof context.phase === "string" && typeof context.status === "string" && Array.isArray(context.tasks) && context.tasks.every(isKernelTask) && Array.isArray(context.completed) && context.completed.every((id) => typeof id === "string") }
export function encodeKernelContextRequest(request: KernelContextRequest): string { return JSON.stringify(request) }
export function decodeKernelContextResponse(payload: string): KernelContextResponse { const value: unknown = JSON.parse(payload); if (!isKernelContextResponse(value)) throw new Error("Invalid Kernel context response"); return value }
export function encodeKernelCommandRequest(request: KernelCommandRequest): string { return JSON.stringify(request) }
export function decodeKernelCommandResponse(payload: string): KernelCommandResponse { const value: unknown = JSON.parse(payload); if (!isKernelCommandResponse(value)) throw new Error("Invalid Kernel command response"); return value }
export function encodeKernelBoundaryRequest(request: KernelBoundaryRequest): string { return JSON.stringify(request) }
export function decodeKernelBoundaryResponse(payload: string): KernelBoundaryResponse { const value: unknown = JSON.parse(payload); if (!isKernelBoundaryResponse(value)) throw new Error("Invalid Kernel boundary response"); return value }
function isKernelContextResponse(value: unknown): value is KernelContextResponse { if (!value || typeof value !== "object") return false; const response = value as Record<string, unknown>; if (response.available === false) return typeof response.reason === "string"; return response.available === true && isKernelContext(response.context) }
function isKernelActionPlan(value: unknown): value is KernelActionPlan { if (!value || typeof value !== "object") return false; const plan = value as Record<string, unknown>; if (plan.action === "done") return typeof plan.reason === "string"; return plan.action === "delegate" && typeof plan.phase === "string" && KERNEL_PHASES.includes(plan.phase as KernelPhase) && typeof plan.task_id === "string" && typeof plan.agent === "string" && typeof plan.objective === "string" && Array.isArray(plan.files) && plan.files.every((file) => typeof file === "string") && Array.isArray(plan.allowed_tools) && plan.allowed_tools.every((tool) => typeof tool === "string") && typeof plan.max_iterations === "number" }
function isKernelActionResponse(value: unknown): value is KernelActionResponse { if (!value || typeof value !== "object") return false; const response = value as Record<string, unknown>; if (response.available === false) return typeof response.reason === "string"; return response.available === true && isKernelActionPlan(response.plan) }
function isKernelCommandResponse(value: unknown): value is KernelCommandResponse { if (!value || typeof value !== "object") return false; const response = value as Record<string, unknown>; if (response.ok === false) return typeof response.reason === "string"; return response.ok === true && (response.result === undefined || (typeof response.result === "object" && response.result !== null && !Array.isArray(response.result))) }
function isKernelBoundaryResponse(value: unknown): value is KernelBoundaryResponse { if (!value || typeof value !== "object") return false; const response = value as Record<string, unknown>; if (response.allowed === false) return (response.decision === "blocked" || response.decision === "done") && typeof response.reason === "string" && response.execution_order === null; if (response.allowed !== true || response.decision !== "proceed" || typeof response.reason !== "string") return false; const order = response.execution_order; if (!order || typeof order !== "object") return false; const valueOrder = order as Record<string, unknown>; return typeof valueOrder.task_id === "string" && typeof valueOrder.description === "string" && typeof valueOrder.phase === "string" && KERNEL_PHASES.includes(valueOrder.phase as KernelPhase) && Array.isArray(valueOrder.files) && valueOrder.files.every((file) => typeof file === "string") }
