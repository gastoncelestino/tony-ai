/**
 * Tony Kernel Plugin — OpenCode adapter.
 *
 * OpenCode supplies execution identity. Persistent SDD state is read through
 * the explicit Kernel context provider, normalized by the boundary adapter,
 * and authorized by the Python Kernel. Missing state, provider errors,
 * transport errors, blocked decisions, or invalid execution orders all fail
 * closed.
 *
 * The first task in a new session is a tightly-scoped bootstrap delegation:
 * the subagent returns a machine-readable TaskSet, after which all execution
 * is authorized against that canonical graph. Successful task execution is
 * reconciled back into the TaskSet; failed/incomplete tasks never unlock work.
 */
import { appendFileSync } from "node:fs"
import { join } from "node:path"
import { execFile } from "node:child_process"
import { promisify } from "node:util"
import type { Plugin } from "@opencode-ai/plugin"
import { adaptTaskExecutionContext } from "./kernel-boundary-adapter"
import { createExecutionObservationStore } from "./execution-observation"
import { createKernelContextProvider } from "./kernel-context-provider"
import { callKernelBoundary } from "./kernel-boundary-transport"
import type { KernelBoundaryRequest, KernelBoundaryResponse, KernelExecutionOrder } from "./kernel-boundary-protocol"

const execFileAsync = promisify(execFile)
const BOOTSTRAP_COMMAND = "tony:bootstrap-decompose"
const BOOTSTRAP_DESCRIPTION = "decompose task graph"
const BOOTSTRAP_READ_ONLY_TOOLS = new Set(["read", "glob"])
const bootstrapInFlight = new Map<string, number>()

function bootstrapPrompt(originalDescription: string, originalPrompt: string): string {
  return `You are Tony's task-graph decomposition subagent. This is ONLY the bootstrap planning step of a new execution session.

Your ONLY output is a machine-readable TaskSet. Do NOT perform the requested work, implement anything, modify files, create files, or create temporary files. Do not use bash, shell commands, write/edit tools, or skills. If repository inspection is necessary, use read/glob only. Never ask for permission to write anything.

ORIGINAL TASK DESCRIPTION:
${originalDescription || "(not provided)"}

ORIGINAL TASK PROMPT / OBJECTIVE:
${originalPrompt || "(not provided)"}

Return ONLY valid JSON wrapped in <task_result> tags, with this exact top-level shape:
<task_result>{"tasks":[{"id":"unique-id","description":"unique executable task description","phase":"phase-name","dependencies":["other-task-id"],"files":["optional/path"]}]}</task_result>

Decomposition rules:
- The task list MUST contain at least 2 tasks for any non-trivial objective and normally 3-8 tasks.
- Every task must be genuinely atomic: one bounded action with one clear result that a single delegated subagent can complete without further decomposition.
- Do not create umbrella tasks such as "analyze architecture", "implement feature", "document system", or "validate everything". Split those into concrete file/component-level actions.
- Each task description must say what to inspect, change, test, or produce, not merely name a topic.
- Prefer independent tasks in parallel. Add dependencies only when the output of one task is actually required by another.
- Keep each task small enough to finish in one focused delegation; if a task would require several unrelated tool calls or multiple phases of work, split it.
- Every task must be directly required by the original objective. Do not invent unrelated cleanup, documentation, tests, or refactors unless the objective requires them.
- Include relevant file paths when they are known from inspection, but do not modify those files during bootstrap.
- Use a concrete phase name appropriate to the work (for example exploration, implementation, testing).
- IDs must be unique, stable, lowercase, and descriptive.
- Do not include the reserved bootstrap task.
- Do not return an empty tasks array.
- Do not add commentary, markdown fences, explanations, or prose before or after the JSON.`
}

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
  return { sessionID: input.sessionID, tool: input.tool, arguments: args }
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

function beginBootstrap(directory: string): void {
  bootstrapInFlight.set(directory, (bootstrapInFlight.get(directory) ?? 0) + 1)
}

function endBootstrap(directory: string): void {
  const remaining = (bootstrapInFlight.get(directory) ?? 1) - 1
  if (remaining <= 0) bootstrapInFlight.delete(directory)
  else bootstrapInFlight.set(directory, remaining)
}

function isBootstrapInFlight(directory: string): boolean {
  return (bootstrapInFlight.get(directory) ?? 0) > 0
}

function assertBootstrapToolAllowed(directory: string, tool: string): void {
  if (!isBootstrapInFlight(directory)) return
  if (!BOOTSTRAP_READ_ONLY_TOOLS.has(tool.toLowerCase())) {
    throw new KernelBlockedError(
      `[Tony Kernel] Bootstrap is strictly atomic and read-only; tool '${tool}' is not allowed until decomposition completes`,
    )
  }
}

async function authorizeExecution(
  input: ExecutionRequest,
  provider: ReturnType<typeof createKernelContextProvider>,
): Promise<KernelExecutionOrder> {
  if (input.tool.toLowerCase() !== "task") {
    throw new KernelUnavailableError("[Tony Kernel] Execution authorization is not implemented for this runtime boundary")
  }
  const provided = await provider.getContext(input)
  if (provided.kind !== "available") throw new KernelUnavailableError(`[Tony Kernel] ${provided.reason}`)
  const adapted = adaptTaskExecutionContext(input, provided.context)
  if (adapted.kind !== "ready") throw new KernelUnavailableError(`[Tony Kernel] ${adapted.reason}`)
  return validateExecutionOrder(adapted.request, await callKernelBoundary(adapted.request))
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
  return { title: "Task", output: typeof value === "string" ? value : JSON.stringify(value), metadata: {} }
}

function resultIndicatesFailure(metadata: unknown): boolean {
  if (!metadata || typeof metadata !== "object") return false
  const value = metadata as Record<string, unknown>
  return value.status === "error" || value.error === true || value.failed === true
}

function createDebugLogger(directory: string) {
  const logPath = join(directory, ".opencode", "tony-kernel-debug.log")
  return (event: string, details: Record<string, unknown> = {}) => {
    try {
      appendFileSync(logPath, `${JSON.stringify({ timestamp: new Date().toISOString(), event, ...details })}\n`, "utf8")
    } catch (error) {
      console.error("[TONY DEBUG] unable to write debug log", { logPath, error })
    }
  }
}

async function runPython(
  directory: string,
  script: string,
  args: string[],
): Promise<{ ok?: boolean; result?: Record<string, unknown>; reason?: string }> {
  const pythonCommand = process.env.TONYMEM_PYTHON ?? "python3"
  const dbPath = process.env.LOCAL_MEMORY_DB ?? join(directory, "local-memory", "memory.db")
  const childEnv = { ...process.env }
  delete childEnv.LOCAL_MEMORY_DB
  const completed = await execFileAsync(
    pythonCommand,
    [script, ...args, "--db-path", dbPath],
    { cwd: directory, timeout: 5000, maxBuffer: 1024 * 1024, env: childEnv },
  )
  try {
    return JSON.parse(completed.stdout) as { ok?: boolean; result?: Record<string, unknown>; reason?: string }
  } catch {
    throw new Error("Invalid Tony Kernel Python response")
  }
}

async function prepareBootstrap(directory: string, sessionID: string): Promise<void> {
  const script = process.env.TONYMEM_TASKSET_BOOTSTRAP_SCRIPT ?? `${directory}/kernel/task_set_bootstrap.py`
  const payload = await runPython(directory, script, ["--prepare", "--project", directory, "--session-id", sessionID])
  if (payload.ok !== true) throw new KernelUnavailableError(payload.reason ?? "Unable to initialize SDD bootstrap state")
}

function extractTaskResult(output: string): string {
  const match = output.match(/<task_result>\s*([\s\S]*?)\s*<\/task_result>/)
  return (match?.[1] ?? output).trim()
}

async function completeBootstrap(
  directory: string,
  sessionID: string,
  output: string,
): Promise<string> {
  const script = process.env.TONYMEM_TASKSET_BOOTSTRAP_SCRIPT ?? `${directory}/kernel/task_set_bootstrap.py`
  const decomposition = extractTaskResult(output)
  const payload = await runPython(directory, script, [
    "--complete",
    "--project",
    directory,
    "--session-id",
    sessionID,
    "--decomposition",
    decomposition,
  ])
  if (payload.ok !== true) throw new Error(payload.reason ?? "TaskSet bootstrap completion failed")
  return typeof payload.result?.version === "number" ? String(payload.result.version) : "unknown"
}

async function completeSuccessfulTask(
  directory: string,
  sessionID: string,
  taskId: string,
  result: { title: string; output: string; metadata: unknown },
): Promise<string> {
  const script = process.env.TONYMEM_TASKSET_COMPLETION_SCRIPT ?? `${directory}/kernel/task_completion.py`
  const evidence = JSON.stringify([{ kind: "opencode-task-result", title: result.title, output: result.output, metadata: result.metadata }])
  const payload = await runPython(directory, script, [
    "--complete",
    "--project",
    directory,
    "--session-id",
    sessionID,
    "--task-id",
    taskId,
    "--evidence",
    evidence,
  ])
  if (payload.ok !== true) throw new Error(payload.reason ?? "TaskSet completion failed")
  return typeof payload.result?.version === "number" ? String(payload.result.version) : "unknown"
}

async function taskExecuteBeforeHook(
  input: { tool: string; sessionID: string; callID: string },
  output: { args: Record<string, unknown> },
  provider: ReturnType<typeof createKernelContextProvider>,
  observations: ReturnType<typeof createExecutionObservationStore>,
  directory: string,
  debugLog: ReturnType<typeof createDebugLogger>,
): Promise<void> {
  const details = { tool: input.tool, sessionID: input.sessionID, callID: input.callID }
  debugLog("tool.execute.before hook received", details)

  // Once bootstrap delegation starts, the whole runtime boundary is locked to
  // repository reads. This is a Kernel invariant, not merely a prompt rule:
  // nested task/skill/shell/write/edit calls cannot escape the bootstrap phase.
  assertBootstrapToolAllowed(directory, input.tool)

  if (input.tool.toLowerCase() !== "task") return
  debugLog("tool.execute.before", { ...details, args: output.args })
  debugLog("authorizeExecution started", details)
  let bootstrapStarted = false
  try {
    let provided = await provider.getContext(input)
    if (provided.kind !== "available" && provided.reason === "SDD state unavailable") {
      const originalDescription = typeof output.args.description === "string" ? output.args.description.trim() : ""
      const originalPrompt = typeof output.args.prompt === "string" ? output.args.prompt.trim() : ""
      debugLog("bootstrap initialization started", {
        ...details,
        originalDescription,
        originalCommand: output.args.command,
      })
      await prepareBootstrap(directory, input.sessionID)

      // OpenCode's before-hook contract gives us a mutable args object. Mutate
      // it in place so the very first task() call becomes the bootstrap
      // delegation itself; the original call must not be allowed to execute
      // without a canonical TaskSet.
      output.args.description = BOOTSTRAP_DESCRIPTION
      output.args.prompt = bootstrapPrompt(originalDescription, originalPrompt)
      output.args.subagent_type = "explore"
      output.args.command = BOOTSTRAP_COMMAND
      beginBootstrap(directory)
      bootstrapStarted = true

      provided = await provider.getContext(input)
      debugLog("bootstrap initialization succeeded", {
        ...details,
        delegatedDescription: output.args.description,
        delegatedCommand: output.args.command,
        delegatedSubagentType: output.args.subagent_type,
      })
    }
    if (provided.kind !== "available") throw new KernelUnavailableError(`[Tony Kernel] ${provided.reason}`)
    const request = executionRequest(input, output.args)
    const adapted = adaptTaskExecutionContext(request, provided.context)
    if (adapted.kind !== "ready") throw new KernelUnavailableError(`[Tony Kernel] ${adapted.reason}`)
    const order = validateExecutionOrder(adapted.request, await callKernelBoundary(adapted.request))
    debugLog("authorizeExecution succeeded", { ...details, taskId: order.task_id, phase: order.phase, description: order.description })
    observations.start({ projectId: directory, sessionId: input.sessionID, callId: input.callID, taskId: order.task_id, phase: order.phase })
    debugLog("observations.start succeeded", { ...details, taskId: order.task_id, phase: order.phase })
  } catch (error) {
    if (bootstrapStarted) endBootstrap(directory)
    debugLog("authorizeExecution failed", { ...details, error: error instanceof Error ? error.message : String(error), errorName: error instanceof Error ? error.name : typeof error })
    throw error
  }
}

async function taskExecuteAfterHook(
  input: { tool: string; sessionID: string; callID: string },
  output: unknown,
  observations: ReturnType<typeof createExecutionObservationStore>,
  directory: string,
  debugLog: ReturnType<typeof createDebugLogger>,
): Promise<void> {
  if (input.tool.toLowerCase() !== "task") return
  let bootstrapStarted = false
  try {
    const result = normalizeResult(output)
    const finished = resultIndicatesFailure(result.metadata)
      ? observations.fail(input.callID, result)
      : observations.succeed(input.callID, result)

    debugLog("tool.execute.after", {
      tool: input.tool,
      sessionID: input.sessionID,
      callID: input.callID,
      taskId: finished.taskId,
      status: finished.status,
    })

    if (finished.status !== "succeeded") return

    bootstrapStarted = finished.taskId === "__tony_bootstrap_decompose__"
    debugLog("task completion started", { sessionID: input.sessionID, callID: input.callID, taskId: finished.taskId })
    const version = bootstrapStarted
      ? await completeBootstrap(directory, input.sessionID, result.output)
      : await completeSuccessfulTask(directory, input.sessionID, finished.taskId, result)
    debugLog("task completion succeeded", { sessionID: input.sessionID, callID: input.callID, taskId: finished.taskId, version })
  } catch (error) {
    debugLog("task completion/observation failed", { callID: input.callID, error: error instanceof Error ? error.message : String(error), errorName: error instanceof Error ? error.name : typeof error })
    throw error
  } finally {
    if (bootstrapStarted) endBootstrap(directory)
  }
}

const TonyKernelPlugin: Plugin = async ({ directory }) => {
  const debugLog = createDebugLogger(directory)
  const provider = createKernelContextProvider(directory, { debugLog })
  const observations = createExecutionObservationStore()
  debugLog("plugin loaded", { message: "Kernel execution boundary is active and fail-closed" })
  console.log("[tony-kernel] Plugin loaded; Kernel execution boundary is active and fail-closed")
  return {
    "tool.execute.before": (input, output) => taskExecuteBeforeHook(input, output, provider, observations, directory, debugLog),
    "tool.execute.after": (input, output) => taskExecuteAfterHook(input, output, observations, directory, debugLog),
  }
}

export default TonyKernelPlugin
