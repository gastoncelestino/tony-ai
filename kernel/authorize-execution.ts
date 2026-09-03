import { adaptTaskExecutionContext } from "./adapter"
import { callKernelBoundary, callKernelCommand, getKernelContext } from "./transport"
import { actionPlanPrompt, resolveActionPlan } from "./action-plan"
import type { KernelBoundaryRequest, KernelExecutionOrder } from "./protocol"

const BOOTSTRAP_COMMAND = "tony:bootstrap-decompose"
const BOOTSTRAP_DESCRIPTION = "decompose task graph"
const BOOTSTRAP_READ_ONLY_TOOLS = new Set(["read", "glob", "grep", "list", "tony-tools_batch_read"])

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

function bootstrapPrompt(
  description: string,
  prompt: string
) {
  return [
    `Task description:\n${description || "(not provided)"}`,
    `Task objective:\n${prompt || "(not provided)"}`,
    `Return a TaskSet using this schema:\n<task_result>{"tasks":[{"id":"unique-id","description":"unique executable task description","phase":"phase-name","dependencies":["other-task-id"],"files":["optional/path"]}]}</task_result>`,
    `phase must be one of: explore, propose, spec, design, tasks, apply, verify, archive.`,
  ].join("\n\n")
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

    input.args.description = BOOTSTRAP_DESCRIPTION
    input.args.prompt = bootstrapPrompt(
      description,
      prompt
    )
    input.args.subagent_type = "sdd-explore"
    input.args.command = BOOTSTRAP_COMMAND

    bootstrapSessions.add(key)

    try {
      provided = await getExecutionContext(
        input.directory,
        input.sessionID
      )
    } catch (error) {
      bootstrapSessions.delete(key)
      throw error
    }

    if (provided.kind !== "available") {
      bootstrapSessions.delete(key)
    }
  }

  if (provided.kind !== "available") {
    throw new KernelUnavailableError(
      `[Tony Kernel] ${provided.reason}`
    )
  }

  const plan = resolveActionPlan(provided.context)
  if (plan.action === "done") {
    throw new KernelDoneError(`[Tony Kernel] ${plan.reason}`)
  }

  input.args.description = plan.objective
  input.args.prompt = actionPlanPrompt(plan)
  input.args.subagent_type = plan.agent
  input.args.command = `tony:${plan.phase}`

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
