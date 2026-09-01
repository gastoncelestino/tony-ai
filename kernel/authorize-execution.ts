import { adaptTaskExecutionContext } from "./adapter"
import { callKernelBoundary, callKernelCommand, getKernelContext } from "./transport"
import type { KernelBoundaryRequest, KernelExecutionOrder } from "./protocol"
import { createKernelContextProvider } from "./provider"

const BOOTSTRAP_COMMAND = "tony:bootstrap-decompose"
const BOOTSTRAP_DESCRIPTION = "decompose task graph"
const BOOTSTRAP_READ_ONLY_TOOLS = new Set(["read", "glob"])

export class KernelBlockedError extends Error { constructor(message: string) { super(message); this.name = "KernelBlockedError" } }
export class KernelUnavailableError extends Error { constructor(message: string) { super(message); this.name = "KernelUnavailableError" } }
export type ExecutionAuthorizationInput = { directory: string; sessionID: string; callID: string; tool: string; args: Record<string, unknown> }
export type ExecutionAuthorization = { allowed: true; reason: string; order: KernelExecutionOrder } | { allowed: false; reason: string }

const originalPromptBySession = new Map<string, string>()
const bootstrapSessions = new Set<string>()
const sessionKey = (directory: string, sessionID: string) => `${directory}\0${sessionID}`

export function rememberPrompt(directory: string, sessionID: string, prompt: string) { if (prompt.trim()) originalPromptBySession.set(sessionKey(directory, sessionID), prompt.trim()) }

export function assertBootstrapToolAllowed(directory: string, tool: string) {
  const active = [...bootstrapSessions].some((key) => key.startsWith(`${directory}\0`))
  if (active && !BOOTSTRAP_READ_ONLY_TOOLS.has(tool.toLowerCase())) throw new KernelBlockedError(`[Tony Kernel] Bootstrap is strictly atomic and read-only; tool '${tool}' is not allowed until decomposition completes`)
}

function bootstrapPrompt(description: string, prompt: string) {
  return `You are Tony's task-graph decomposition subagent. This is ONLY the bootstrap planning step of a new execution session.

Your ONLY output is a machine-readable TaskSet. Do NOT perform the requested work, implement anything, modify files, create files, or create temporary files. Do not use bash, shell commands, write/edit tools, or skills. If repository inspection is necessary, use read/glob only.

ORIGINAL TASK DESCRIPTION:
${description || "(not provided)"}

ORIGINAL TASK PROMPT / OBJECTIVE:
${prompt || "(not provided)"}

Return ONLY valid JSON wrapped in <task_result> tags, with this exact top-level shape:
<task_result>{"tasks":[{"id":"unique-id","description":"unique executable task description","phase":"phase-name","dependencies":["other-task-id"],"files":["optional/path"]}]}</task_result>

The phase field MUST use one of: explore, propose, spec, design, tasks, apply, verify, archive. Do not include the reserved bootstrap task. Do not return an empty tasks array.`
}

async function kernelCommand(directory: string, request: Parameters<typeof callKernelCommand>[0]) {
  const response = await callKernelCommand(request, { cwd: directory })
  if (!response.ok) throw new KernelUnavailableError(response.reason)
  return response.result ?? {}
}

async function prepareBootstrap(directory: string, sessionID: string) { await kernelCommand(directory, { operation: "prepare_bootstrap", project_directory: directory, session_id: sessionID }) }
export function extractTaskResult(output: string) { return (output.match(/<task_result>\s*([\s\S]*?)\s*<\/task_result>/)?.[1] ?? output).trim() }
export async function completeBootstrap(directory: string, sessionID: string, output: string) { await kernelCommand(directory, { operation: "complete_bootstrap", project_directory: directory, session_id: sessionID, decomposition: extractTaskResult(output) }) }
export async function completeSuccessfulTask(directory: string, sessionID: string, taskId: string, result: { title: string; output: string; metadata: unknown }) {
  await kernelCommand(directory, { operation: "complete_task", project_directory: directory, session_id: sessionID, task_id: taskId, evidence: JSON.stringify([{ kind: "opencode-task-result", title: result.title, output: result.output, metadata: result.metadata }]) })
}

function validateOrder(request: KernelBoundaryRequest, order: KernelExecutionOrder) {
  const task = request.tasks.find((candidate) => candidate.id === order.task_id)
  if (!task || task.phase !== order.phase || task.description !== order.description) throw new KernelBlockedError("[Tony Kernel] Invalid execution order")
  return order
}

export async function authorizeExecution(input: ExecutionAuthorizationInput): Promise<ExecutionAuthorization> {
  if (input.tool.toLowerCase() !== "task") return { allowed: true, reason: "not_task", order: { task_id: input.callID, description: "", phase: "explore", files: [] } }
  const provider = createKernelContextProvider((request) => getKernelContext(request, { cwd: input.directory }))
  let provided = await provider.getContext({ projectDirectory: input.directory, sessionID: input.sessionID, tool: input.tool })
  if (provided.kind !== "available" && provided.reason.startsWith("SDD state unavailable")) {
    const key = sessionKey(input.directory, input.sessionID)
    const description = typeof input.args.description === "string" ? input.args.description.trim() : ""
    const prompt = originalPromptBySession.get(key) ?? (typeof input.args.prompt === "string" ? input.args.prompt.trim() : "")
    await prepareBootstrap(input.directory, input.sessionID)
    input.args.description = BOOTSTRAP_DESCRIPTION
    input.args.prompt = bootstrapPrompt(description, prompt)
    input.args.subagent_type = "explore"
    input.args.command = BOOTSTRAP_COMMAND
    bootstrapSessions.add(key)
    try { provided = await provider.getContext({ projectDirectory: input.directory, sessionID: input.sessionID, tool: input.tool }) }
    catch (error) { bootstrapSessions.delete(key); throw error }
    if (provided.kind !== "available") bootstrapSessions.delete(key)
  }
  if (provided.kind !== "available") throw new KernelUnavailableError(`[Tony Kernel] ${provided.reason}`)
  const adapted = adaptTaskExecutionContext({ tool: input.tool, arguments: input.args }, provided.context)
  if (adapted.kind !== "ready") throw new KernelUnavailableError(`[Tony Kernel] ${adapted.reason}`)
  const response = await callKernelBoundary(adapted.request, { cwd: input.directory })
  if (!response.allowed) throw new KernelBlockedError(response.reason)
  return { allowed: true, reason: response.reason, order: validateOrder(adapted.request, response.execution_order) }
}

export function finishBootstrap(directory: string, sessionID: string) { const key = sessionKey(directory, sessionID); originalPromptBySession.delete(key); bootstrapSessions.delete(key) }
export function bootstrapStarted(directory: string, sessionID: string) { return bootstrapSessions.has(sessionKey(directory, sessionID)) }
