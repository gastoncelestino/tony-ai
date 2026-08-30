/**
 * Tony Kernel Plugin — OpenCode adapter.
 *
 * OpenCode supplies execution identity. Persistent SDD state is read through
 * the explicit Kernel context provider, normalized by the boundary adapter,
 * and authorized by the Python Kernel. Missing state, provider errors,
 * transport errors, blocked decisions, or invalid execution orders all fail
 * closed.
 *
 * Execution observations are correlated with OpenCode's callID. The first
 * observation layer is intentionally in-memory; persistence in TonyMem is a
 * separate increment so observation semantics stay independently testable.
 */
import { appendFileSync } from "node:fs"
import { join } from "node:path"
import type { Plugin } from "@opencode-ai/plugin"
import { adaptTaskExecutionContext } from "./kernel-boundary-adapter"
import { createExecutionObservationStore } from "./execution-observation"
import { createKernelContextProvider } from "./kernel-context-provider"
import { callKernelBoundary } from "./kernel-boundary-transport"
import type { KernelBoundaryRequest, KernelBoundaryResponse, KernelExecutionOrder } from "./kernel-boundary-protocol"

class KernelBlockedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelBlockedError"
  }
}

class KernelUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelUnavailableError"
  }
}

interface ExecutionRequest {
  sessionID: string
  tool: string
  arguments: Record<string, unknown>
}

function executionRequest(
  input: { sessionID: string; tool: string },
  args: Record<string, unknown>,
): ExecutionRequest {
  return {
    sessionID: input.sessionID,
    tool: input.tool,
    arguments: args,
  }
}

function validateExecutionOrder(
  request: KernelBoundaryRequest,
  response: KernelBoundaryResponse,
): KernelExecutionOrder {
  if (!response.allowed) throw new KernelBlockedError(response.reason)

  const order = response.execution_order
  const task = request.tasks.find((candidate) => candidate.id === order.task_id)

  if (!task || task.phase !== order.phase || task.description !== order.description) {
    throw new KernelBlockedError("[Tony Kernel] Invalid execution order")
  }

  return order
}

async function authorizeExecution(
  input: ExecutionRequest,
  provider: ReturnType<typeof createKernelContextProvider>,
): Promise<KernelExecutionOrder> {
  if (input.tool !== "Task") {
    throw new KernelUnavailableError(
      "[Tony Kernel] Execution authorization is not implemented for this runtime boundary",
    )
  }

  const provided = await provider.getContext(input)
  if (provided.kind !== "available") {
    throw new KernelUnavailableError(`[Tony Kernel] ${provided.reason}`)
  }

  const adapted = adaptTaskExecutionContext(input, provided.context)
  if (adapted.kind !== "ready") {
    throw new KernelUnavailableError(`[Tony Kernel] ${adapted.reason}`)
  }

  const response = await callKernelBoundary(adapted.request)
  return validateExecutionOrder(adapted.request, response)
}

function normalizeResult(value: unknown): { title: string; output: string; metadata: unknown } {
  if (value && typeof value === "object") {
    const result = value as Record<string, unknown>
    return {
      title: typeof result.title === "string" ? result.title : "Task",
      output: typeof result.output === "string" ? result.output : JSON.stringify(value),
      metadata: result.metadata ?? {},
    }
  }

  return {
    title: "Task",
    output: typeof value === "string" ? value : JSON.stringify(value),
    metadata: {},
  }
}

function resultIndicatesFailure(metadata: unknown): boolean {
  if (!metadata || typeof metadata !== "object") return false
  const value = metadata as Record<string, unknown>
  return value.status === "error" || value.error === true || value.failed === true
}

function createDebugLogger(directory: string) {
  const logPath = join(directory, ".opencode", "tony-kernel-debug.log")

  return (event: string, details: Record<string, unknown> = {}) => {
    const entry = {
      timestamp: new Date().toISOString(),
      event,
      ...details,
    }

    try {
      appendFileSync(logPath, `${JSON.stringify(entry)}\n`, "utf8")
    } catch (error) {
      console.error("[TONY DEBUG] unable to write debug log", { logPath, error })
    }
  }
}

async function taskExecuteBeforeHook(
  input: {
    tool: string
    sessionID: string
    callID: string
  },
  output: {
    args: Record<string, unknown>
  },
  provider: ReturnType<typeof createKernelContextProvider>,
  observations: ReturnType<typeof createExecutionObservationStore>,
  directory: string,
  debugLog: ReturnType<typeof createDebugLogger>,
): Promise<void> {
  const details = {
    tool: input.tool,
    sessionID: input.sessionID,
    callID: input.callID,
  }

  console.error("[TONY DEBUG] tool.execute.before hook received", details)
  debugLog("tool.execute.before hook received", details)

  if (input.tool.toLowerCase() !== "task") return

  console.error("[TONY DEBUG] tool.execute.before", details)
  debugLog("tool.execute.before", details)

  debugLog("authorizeExecution started", details)
  console.error("[TONY DEBUG] authorizeExecution started", details)

  let order: KernelExecutionOrder
  try {
    order = await authorizeExecution(executionRequest(input, output.args), provider)
    debugLog("authorizeExecution succeeded", {
      ...details,
      taskId: order.task_id,
      phase: order.phase,
    })
    console.error("[TONY DEBUG] authorizeExecution succeeded", {
      ...details,
      taskId: order.task_id,
      phase: order.phase,
    })
  } catch (error) {
    debugLog("authorizeExecution failed", {
      ...details,
      error: error instanceof Error ? error.message : String(error),
      errorName: error instanceof Error ? error.name : typeof error,
    })
    console.error("[TONY DEBUG] authorizeExecution failed", {
      ...details,
      error,
    })
    throw error
  }

  debugLog("observations.start started", {
    ...details,
    taskId: order.task_id,
    phase: order.phase,
  })
  console.error("[TONY DEBUG] observations.start started", {
    ...details,
    taskId: order.task_id,
    phase: order.phase,
  })

  try {
    observations.start({
      projectId: directory,
      sessionId: input.sessionID,
      callId: input.callID,
      taskId: order.task_id,
      phase: order.phase,
    })

    debugLog("observations.start succeeded", {
      ...details,
      taskId: order.task_id,
      phase: order.phase,
    })
    console.error("[TONY DEBUG] observations.start succeeded", {
      ...details,
      taskId: order.task_id,
      phase: order.phase,
    })
  } catch (error) {
    debugLog("observations.start failed", {
      ...details,
      error: error instanceof Error ? error.message : String(error),
      errorName: error instanceof Error ? error.name : typeof error,
    })
    console.error("[TONY DEBUG] observations.start failed", {
      ...details,
      error,
    })
    throw error
  }
}

function taskExecuteAfterHook(
  input: {
    tool: string
    sessionID: string
    callID: string
  },
  output: unknown,
  observations: ReturnType<typeof createExecutionObservationStore>,
  debugLog: ReturnType<typeof createDebugLogger>,
): void {
  if (input.tool.toLowerCase() !== "task") return

  try {
    const result = normalizeResult(output)
    const finished = resultIndicatesFailure(result.metadata)
      ? observations.fail(input.callID, result)
      : observations.succeed(input.callID, result)

    const details = {
      tool: input.tool,
      sessionID: input.sessionID,
      callID: input.callID,
      status: finished.status,
    }

    console.error("[TONY DEBUG] tool.execute.after", details)
    debugLog("tool.execute.after", details)
  } catch (error) {
    // OpenCode's normal tool.execute.after hook is a successful-result
    // surface. A tool exception may never reach this hook. Therefore we do
    // not invent a failed Result here; the still-running observation remains
    // eligible to be classified as incomplete by a later reconciliation step.
    console.error("[TONY DEBUG] execution observation unavailable", {
      callID: input.callID,
      error,
    })
    debugLog("execution observation unavailable", {
      callID: input.callID,
      error: error instanceof Error ? error.message : String(error),
    })
  }
}

const TonyKernelPlugin: Plugin = async ({ directory }) => {
  const provider = createKernelContextProvider(directory)
  const observations = createExecutionObservationStore()
  const debugLog = createDebugLogger(directory)

  debugLog("plugin loaded", {
    message: "Kernel execution boundary is active and fail-closed",
  })
  console.log("[tony-kernel] Plugin loaded; Kernel execution boundary is active and fail-closed")

  return {
    "tool.execute.before": (input, output) =>
      taskExecuteBeforeHook(input, output, provider, observations, directory, debugLog),
    "tool.execute.after": (input, output) =>
      taskExecuteAfterHook(input, output, observations, debugLog),
  }
}

export default TonyKernelPlugin
