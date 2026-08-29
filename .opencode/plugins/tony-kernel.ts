/**
 * Tony Kernel Plugin — OpenCode adapter.
 *
 * OpenCode supplies only execution identity. Persistent SDD state is read
 * through the explicit Kernel context provider, normalized by the boundary
 * adapter, and authorized by the Python Kernel. Missing state, provider
 * errors, transport errors, blocked decisions, or invalid execution orders
 * all fail closed.
 */
import type { Plugin } from "@opencode-ai/plugin"
import { adaptTaskExecutionContext } from "./kernel-boundary-adapter"
import { createKernelContextProvider } from "./kernel-context-provider"
import { callKernelBoundary } from "./kernel-boundary-transport"
import type { KernelBoundaryRequest, KernelBoundaryResponse } from "./kernel-boundary-protocol"

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
): void {
  if (!response.allowed) throw new KernelBlockedError(response.reason)

  const order = response.execution_order
  const task = request.tasks.find((candidate) => candidate.id === order.task_id)

  if (!task || task.phase !== order.phase || task.description !== order.description) {
    throw new KernelBlockedError("[Tony Kernel] Invalid execution order")
  }
}

async function authorizeExecution(
  input: ExecutionRequest,
  provider: ReturnType<typeof createKernelContextProvider>,
): Promise<void> {
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
  validateExecutionOrder(adapted.request, response)
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
): Promise<void> {
  if (input.tool !== "Task") return

  console.error("[TONY DEBUG] tool.execute.before", {
    tool: input.tool,
    sessionID: input.sessionID,
    callID: input.callID,
  })

  await authorizeExecution(executionRequest(input, output.args), provider)
}

const TonyKernelPlugin: Plugin = async ({ directory }) => {
  const provider = createKernelContextProvider(directory)
  console.log("[tony-kernel] Plugin loaded; Kernel execution boundary is active and fail-closed")

  return {
    "tool.execute.before": (input, output) => taskExecuteBeforeHook(input, output, provider),
  }
}

export default TonyKernelPlugin
