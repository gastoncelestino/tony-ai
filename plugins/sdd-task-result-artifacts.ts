import type { Plugin } from "@opencode-ai/plugin"

const DEBUG_LOG_PATH = process.platform === "win32" ? "NUL" : "/dev/null"
function debugLog(message: string, details?: Record<string, unknown>) {
  try {
    const suffix = details ? ` ${JSON.stringify(details)}` : ""
    require("node:fs").appendFileSync(DEBUG_LOG_PATH, `[${new Date().toISOString()}] [SDD_ARTIFACTS] ${message}${suffix}\n`, "utf8")
  } catch {}
}

const TASK_RESULT = /^<task id="[^"\r\n]+" state="completed">\n<task_result>\n([\s\S]*?)\n<\/task_result>\n<\/task>$/
const TASK_TAG = /<\/?task(?:\s|>)|<\/?task_result>/
const SDD_PHASES = ["sdd-init", "sdd-explore", "sdd-propose", "sdd-spec", "sdd-design", "sdd-tasks", "sdd-apply", "sdd-verify", "sdd-archive", "sdd-onboard"]
const SDD_TASK_FAILURE_PREFIX = "GENTLE_AI_SDD_FAILURE "
const SDD_TASK_ROUTE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$/

type SDDTaskFailure = { phase: string, code: string, handoff: string }
type SDDTaskFailureError = Error & { sddFailure: SDDTaskFailure }

function isSDDPhase(agent: string): boolean {
  return SDD_PHASES.some((phase) => agent === phase || agent.startsWith(phase + "-"))
}

function taskResult(output: unknown): void {
  debugLog("validating task result", { outputType: typeof output, outputLength: typeof output === "string" ? output.length : undefined })
  if (typeof output !== "string" || output.trim() === "") {
    debugLog("task result invalid: empty")
    throw Object.assign(new Error("SDD phase output must not be empty"), { sddClass: "empty_result" })
  }
  const trimmed = output.trim()
  const envelope = TASK_RESULT.exec(trimmed)
  if (!envelope) {
    if (TASK_TAG.test(trimmed)) {
      debugLog("task result invalid: malformed envelope")
      throw Object.assign(new Error("SDD phase output contains a malformed task result envelope"), { sddClass: "malformed_result" })
    }
    debugLog("task result accepted without task envelope")
    return
  }
  if (envelope[1].trim() === "") {
    debugLog("task result invalid: empty envelope payload")
    throw Object.assign(new Error("SDD phase task result is empty"), { sddClass: "empty_result" })
  }
  if (TASK_TAG.test(envelope[1])) {
    debugLog("task result invalid: nested envelope")
    throw Object.assign(new Error("SDD phase task result contains a nested task envelope"), { sddClass: "malformed_result" })
  }
  debugLog("task result envelope accepted", { payloadLength: envelope[1].length })
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, "'\\''")}'`
}

function taskRouteModel(metadata: unknown): string | undefined {
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return undefined
  const model = (metadata as Record<string, unknown>).model
  if (!model || typeof model !== "object" || Array.isArray(model)) return undefined
  const providerID = (model as Record<string, unknown>).providerID
  const modelID = (model as Record<string, unknown>).modelID
  if (typeof providerID !== "string" || typeof modelID !== "string") return undefined
  if (!SDD_TASK_ROUTE_TOKEN.test(providerID) || !SDD_TASK_ROUTE_TOKEN.test(modelID)) return undefined
  return `${providerID}/${modelID}`
}

function sddTaskFailure(phase: string, cwd: string, cause: unknown, metadata?: unknown): SDDTaskFailureError {
  const empty = (cause as Record<string, unknown> | null)?.sddClass === "empty_result"
  const code = empty ? "sdd_task_result_empty" : "sdd_task_result_malformed"
  const taskModel = taskRouteModel(metadata)
  const guidance = "Do not retry or advance SDD; inspect the existing artifact state and surface the terminal failure to the user."
  const summary = empty
    ? `${phase} produced no task output at all. The child task returned nothing, which most often means the provider rejected the request before generation (authentication, region, or model access), the task was interrupted, or the phase genuinely wrote nothing. ${guidance}`
    : `${phase} returned no valid task result. ${guidance}`
  const failure: SDDTaskFailure = {
    phase,
    code,
    handoff: SDD_TASK_FAILURE_PREFIX + JSON.stringify({
      schemaName: "gentle-ai.sdd-task-result-failure/v1",
      status: "blocked",
      code,
      phase,
      ...(taskModel === undefined ? {} : { taskModel }),
      summary,
      continuation: `gentle-ai sdd-status --cwd ${shellQuote(cwd)} --json`,
    }),
  }
  debugLog("SDD task failure created", { phase, code, taskModel, cause: String(cause) })
  return Object.assign(new Error(failure.handoff), { sddFailure: failure }) as SDDTaskFailureError
}

function sddDispatchLatched(requested: string, failure: SDDTaskFailure, cwd: string): Error {
  debugLog("SDD dispatch latched", { requested, latchedPhase: failure.phase, latchedCode: failure.code })
  return new Error(SDD_TASK_FAILURE_PREFIX + JSON.stringify({
    schemaName: "gentle-ai.sdd-task-result-failure/v1",
    status: "blocked",
    code: "sdd_task_dispatch_latched",
    phase: requested,
    latchedPhase: failure.phase,
    latchedCode: failure.code,
    summary: `${requested} was not dispatched. Earlier in this session ${failure.phase} returned ${failure.code}, and SDD launches stay latched afterwards so a failed phase is never silently retried and no later phase advances on top of it. No provider call, no subagent, and no artifact write happened for this launch, so it produced no new evidence about the original failure.`,
    continuation: `gentle-ai sdd-status --cwd ${shellQuote(cwd)} --json`,
    exit: "Inspect the artifact state the original failure left, surface it to the user, and start a new session to launch SDD phases again. Relaunching in this session cannot dispatch.",
  }))
}

const SDDTaskResultArtifactsPlugin: Plugin = async ({ directory, worktree }) => {
  const failedSDDSessions = new Map<string, SDDTaskFailure>()
  const cwd = worktree || directory
  debugLog("plugin initialized", { directory, worktree, cwd })
  return {
    dispose: async () => {
      debugLog("plugin dispose", { failedSessions: failedSDDSessions.size })
      failedSDDSessions.clear()
    },
    event: async ({ event }) => {
      if (event.type === "session.deleted") {
        debugLog("session.deleted", { sessionID: event.properties.info.id })
        failedSDDSessions.delete(event.properties.info.id)
      }
    },
    "tool.execute.before": async (input, output) => {
      if (input.tool !== "task" || typeof output.args?.subagent_type !== "string") return
      const subagent = output.args.subagent_type
      if (!isSDDPhase(subagent)) return
      debugLog("SDD Task before", { sessionID: input.sessionID, callID: input.callID, subagent })
      const failure = failedSDDSessions.get(input.sessionID)
      if (failure) throw sddDispatchLatched(subagent, failure, cwd)
    },
    "tool.execute.after": async (input, output) => {
      if (input.tool !== "task" || typeof input.args?.subagent_type !== "string") return
      const subagent = input.args.subagent_type
      if (!isSDDPhase(subagent)) return
      debugLog("SDD Task after", { sessionID: input.sessionID, callID: input.callID, subagent, outputLength: typeof output.output === "string" ? output.output.length : undefined })
      try {
        taskResult(output.output)
      } catch (cause) {
        const failure = sddTaskFailure(subagent, cwd, cause, output.metadata)
        failedSDDSessions.set(input.sessionID, failure.sddFailure)
        debugLog("SDD session latched", { sessionID: input.sessionID, phase: failure.sddFailure.phase, code: failure.sddFailure.code })
        throw failure
      }
    },
  }
}

export default SDDTaskResultArtifactsPlugin