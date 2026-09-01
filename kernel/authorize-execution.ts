import { execFile } from "node:child_process"
import { join } from "node:path"
import { promisify } from "node:util"
import { adaptTaskExecutionContext } from "./adapter"
import { callKernelBoundary, getKernelContext } from "./transport"
import type { KernelBoundaryRequest, KernelExecutionOrder } from "./protocol"
import { createKernelContextProvider } from "./provider"

const execFileAsync = promisify(execFile)
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

export function rememberPrompt(directory: string, sessionID: string, prompt: string) {
  if (prompt.trim()) originalPromptBySession.set(sessionKey(directory, sessionID), prompt.trim())
}

export function assertBootstrapToolAllowed(directory: string, tool: string) {
  const active = [...bootstrapSessions].some((key) => key.startsWith(`${directory}\0`))
  if (active && !BOOTSTRAP_READ_ONLY_TOOLS.has(tool.toLowerCase())) {
    throw new KernelBlockedError(`[Tony Kernel] Bootstrap is strictly atomic and read-only; tool '${tool}' is not allowed until decomposition completes`)
  }
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

async function runPython(directory: string, script: string, args: string[]) {
  const python = process.env.TONYMEM_PYTHON ?? "python3"
  const dbPath = process.env.LOCAL_MEMORY_DB ?? join(directory, "local-memory", "memory.db")
  const env = { ...process.env }
  delete env.LOCAL_MEMORY_DB
  try {
    const result = await execFileAsync(python, [script, ...args, "--db-path", dbPath], { cwd: directory, timeout: 5000, maxBuffer: 1024 * 1024, env })
    return JSON.parse(result.stdout) as { ok?: boolean; result?: Record<string, unknown>; reason?: string }
  } catch (error) {
    const stdout = error && typeof error === "object" && "stdout" in error ? String((error as { stdout?: unknown }).stdout ?? "") : ""
    if (stdout.trim()) { try { return JSON.parse(stdout) } catch { /* preserve subprocess error */ } }
    throw error
  }
}

async function prepareBootstrap(directory: string, sessionID: string) {
  const script = process.env.TONYMEM_TASKSET_BOOTSTRAP_SCRIPT ?? `${directory}/kernel/task_set_bootstrap.py`
  const result = await runPython(directory, script, ["--prepare", "--project", directory, "--session-id", sessionID])
  if (result.ok !== true) throw new KernelUnavailableError(result.reason ?? "Unable to initialize SDD bootstrap state")
}

export function extractTaskResult(output: string) { return (output.match(/<task_result>\s*([\s\S]*?)\s*<\/task_result>/)?.[1] ?? output).trim() }

export async function completeBootstrap(directory: string, sessionID: string, output: string) {
  const script = process.env.TONYMEM_TASKSET_BOOTSTRAP_SCRIPT ?? `${directory}/kernel/task_set_bootstrap.py`
  const result = await runPython(directory, script, ["--complete", "--project", directory, "--session-id", sessionID, "--decomposition", extractTaskResult(output)])
  if (result.ok !== true) throw new Error(result.reason ?? "TaskSet bootstrap completion failed")
}

export async function completeSuccessfulTask(directory: string, sessionID: string, taskId: string, result: { title: string; output: string; metadata: unknown }) {
  const script = process.env.TONYMEM_TASKSET_COMPLETION_SCRIPT ?? `${directory}/kernel/task_completion.py`
  const evidence = JSON.stringify([{ kind: "opencode-task-result", title: result.title, output: result.output, metadata: result.metadata }])
  const payload = await runPython(directory, script, ["--complete", "--project", directory, "--session-id", sessionID, "--task-id", taskId, "--evidence", evidence])
  if (payload.ok !== true) throw new Error(payload.reason ?? "TaskSet completion failed")
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

export function finishBootstrap(directory: string, sessionID: string) {
  const key = sessionKey(directory, sessionID)
  originalPromptBySession.delete(key)
  bootstrapSessions.delete(key)
}

export function bootstrapStarted(directory: string, sessionID: string) { return bootstrapSessions.has(sessionKey(directory, sessionID)) }
