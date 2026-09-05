import { spawnSync } from "node:child_process"
import { adaptTaskExecutionContext } from "./adapter"
import { callKernelBoundary, callKernelCommand, getKernelContext } from "./transport"
import type { KernelBoundaryRequest, KernelExecutionOrder } from "./protocol"

const BOOTSTRAP_READ_ONLY_TOOLS = new Set(["read", "glob", "grep", "list", "tony-tools_batch_read"])

/**
 * Motor de descomposicion atomica (kernel/atomic_decompose.py). Reemplaza el
 * flujo anterior de bootstrapPrompt() + delegacion a sdd-explore: en vez de
 * pedirle al modelo el TaskSet completo en una sola llamada libre, corre un
 * proceso Python determinista que hace N llamadas chicas (una por nodo del
 * arbol) contra llama-swap directamente, sin pasar por el mecanismo de
 * agentes de OpenCode. Devuelve el mismo string JSON que completeBootstrap()
 * ya espera, asi que boundary.py no cambia.
 */
function runAtomicDecompose(
  directory: string,
  description: string,
  prompt: string
): string {
  const input = JSON.stringify({
    description: (prompt || description).trim(),
    phase: "explore",
  })

  const result = spawnSync("python3", ["-m", "kernel.atomic_decompose"], {
    cwd: directory,
    input,
    encoding: "utf8",
  })

  if (result.error) {
    throw new KernelUnavailableError(
      `[Tony Kernel] atomic_decompose spawn failed: ${result.error.message}`
    )
  }

  if (result.status !== 0) {
    throw new KernelUnavailableError(
      `[Tony Kernel] atomic_decompose failed: ${result.stderr || "unknown error"}`
    )
  }

  return result.stdout.trim()
}

export class KernelBlockedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelBlockedError"
  }
}

export class KernelUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelUnavailableError"
  }
}

export class KernelDoneError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelDoneError"
  }
}

export type ExecutionAuthorizationInput = {
  directory: string
  sessionID: string
  callID: string
  tool: string
  args: Record<string, unknown>
}

export type ExecutionAuthorization =
  | {
      allowed: true
      reason: string
      order: KernelExecutionOrder
    }
  | {
      allowed: false
      reason: string
    }

const originalPromptBySession = new Map<string, string>()
const bootstrapSessions = new Set<string>()

const sessionKey = (directory: string, sessionID: string) =>
  `${directory}\0${sessionID}`

export function rememberPrompt(
  directory: string,
  sessionID: string,
  prompt: string
) {
  if (prompt.trim()) {
    originalPromptBySession.set(
      sessionKey(directory, sessionID),
      prompt.trim()
    )
  }
}

export function assertBootstrapToolAllowed(
  directory: string,
  tool: string
) {
  const active = [...bootstrapSessions].some((key) =>
    key.startsWith(`${directory}\0`)
  )

  if (
    active &&
    !BOOTSTRAP_READ_ONLY_TOOLS.has(tool.toLowerCase())
  ) {
    throw new KernelBlockedError(
      `[Tony Kernel] Bootstrap is strictly atomic and read-only; tool '${tool}' is not allowed until decomposition completes`
    )
  }
}

async function kernelCommand(
  directory: string,
  request: Parameters<typeof callKernelCommand>[0]
) {
  const response = await callKernelCommand(request, {
    cwd: directory,
  })

  if (!response.ok) {
    throw new KernelUnavailableError(response.reason)
  }

  return response.result ?? {}
}

async function prepareBootstrap(
  directory: string,
  sessionID: string
) {
  await kernelCommand(directory, {
    operation: "prepare_bootstrap",
    project_directory: directory,
    session_id: sessionID,
  })
}

export function extractTaskResult(output: string) {
  const withoutTags = output
    .replace(/<\/?task_result>/g, "")
    .trim()

  const match = withoutTags.match(/\{[\s\S]*\}/)

  return (match?.[0] ?? withoutTags).trim()
}

export async function completeBootstrap(
  directory: string,
  sessionID: string,
  output: string
) {
  await kernelCommand(directory, {
    operation: "complete_bootstrap",
    project_directory: directory,
    session_id: sessionID,
    decomposition: extractTaskResult(output),
  })
}

export async function completeSuccessfulTask(
  directory: string,
  sessionID: string,
  taskId: string,
  result: {
    title: string
    output: string
    metadata: unknown
  }
) {
  await kernelCommand(directory, {
    operation: "complete_task",
    project_directory: directory,
    session_id: sessionID,
    task_id: taskId,
    evidence: JSON.stringify([
      {
        kind: "opencode-task-result",
        title: result.title,
        output: result.output,
        metadata: result.metadata,
      },
    ]),
  })
}

function validateOrder(
  request: KernelBoundaryRequest,
  order: KernelExecutionOrder
) {
  const task = request.tasks.find(
    (candidate) => candidate.id === order.task_id
  )

  if (
    !task ||
    task.phase !== order.phase ||
    task.description !== order.description
  ) {
    throw new KernelBlockedError(
      "[Tony Kernel] Invalid execution order"
    )
  }

  return order
}

async function getExecutionContext(
  directory: string,
  sessionID: string
) {
  const response = await getKernelContext(
    {
      operation: "get_context",
      project_directory: directory,
      session_id: sessionID,
    },
    {
      cwd: directory,
    }
  )

  if (!response.available) {
    return {
      kind: "unavailable" as const,
      reason: response.reason,
    }
  }

  return {
    kind: "available" as const,
    context: response.context,
  }
}

export async function authorizeExecution(
  input: ExecutionAuthorizationInput
): Promise<ExecutionAuthorization> {
  if (input.tool.toLowerCase() !== "task") {
    return {
      allowed: true,
      reason: "not_task",
      order: {
        task_id: input.callID,
        description: "",
        phase: "explore",
        files: [],
      },
    }
  }

  let provided = await getExecutionContext(
    input.directory,
    input.sessionID
  )

  if (
    provided.kind !== "available" &&
    provided.reason.startsWith("SDD state unavailable")
  ) {
    const key = sessionKey(
      input.directory,
      input.sessionID
    )

    const description =
      typeof input.args.description === "string"
        ? input.args.description.trim()
        : ""

    const prompt =
      originalPromptBySession.get(key) ??
      (typeof input.args.prompt === "string"
        ? input.args.prompt.trim()
        : "")

    await prepareBootstrap(
      input.directory,
      input.sessionID
    )

    bootstrapSessions.add(key)

    try {
      const decomposition = runAtomicDecompose(
        input.directory,
        description,
        prompt
      )
      await completeBootstrap(
        input.directory,
        input.sessionID,
        decomposition
      )
    } catch (error) {
      bootstrapSessions.delete(key)
      throw error
    }

    bootstrapSessions.delete(key)

    provided = await getExecutionContext(
      input.directory,
      input.sessionID
    )
  }

  if (provided.kind !== "available") {
    throw new KernelUnavailableError(
      `[Tony Kernel] ${provided.reason}`
    )
  }

  const adapted = adaptTaskExecutionContext(
    {
      tool: input.tool,
      arguments: input.args,
    },
    provided.context
  )

  if (adapted.kind === "blocked") {
    throw new KernelBlockedError(`[Tony Kernel] ${adapted.reason}`)
  }

  if (adapted.kind !== "ready") {
    throw new KernelUnavailableError(`[Tony Kernel] ${adapted.reason}`)
  }

  const response = await callKernelBoundary(
    adapted.request,
    {
      cwd: input.directory,
    }
  )

  if (!response.allowed && response.decision === "done") {
    throw new KernelDoneError(response.reason)
  }

  if (!response.allowed) {
    throw new KernelBlockedError(response.reason)
  }

  return {
    allowed: true,
    reason: response.reason,
    order: validateOrder(
      adapted.request,
      response.execution_order
    ),
  }
}

export function finishBootstrap(
  directory: string,
  sessionID: string
) {
  const key = sessionKey(directory, sessionID)

  originalPromptBySession.delete(key)
  bootstrapSessions.delete(key)
}

export function bootstrapStarted(
  directory: string,
  sessionID: string
) {
  return bootstrapSessions.has(
    sessionKey(directory, sessionID)
  )
}