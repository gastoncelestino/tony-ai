import { execFile } from "node:child_process"
import { promisify } from "node:util"
import type { KernelBoundaryRequest } from "./kernel-boundary-protocol"

const execFileAsync = promisify(execFile)

export type KernelContextProviderResult =
  | { kind: "available"; context: KernelBoundaryRequest }
  | { kind: "unavailable"; reason: string }

export type KernelContextProviderOptions = {
  pythonCommand?: string
  stateScript?: string
  timeoutMs?: number
  readState?: (projectDirectory: string, sessionID: string) => Promise<unknown>
}

type PersistedState = {
  available: boolean
  reason?: string
  state?: unknown
}

function isTask(value: unknown): value is KernelBoundaryRequest["tasks"][number] {
  if (!value || typeof value !== "object") return false
  const task = value as Record<string, unknown>
  return (
    typeof task.id === "string" &&
    typeof task.description === "string" &&
    typeof task.phase === "string" &&
    Array.isArray(task.dependencies) &&
    task.dependencies.every((dependency) => typeof dependency === "string")
  )
}

function isBoundaryContext(value: unknown): value is KernelBoundaryRequest {
  if (!value || typeof value !== "object") return false
  const context = value as Record<string, unknown>
  return (
    typeof context.phase === "string" &&
    typeof context.status === "string" &&
    Array.isArray(context.tasks) &&
    context.tasks.every(isTask) &&
    Array.isArray(context.completed) &&
    context.completed.every((taskID) => typeof taskID === "string")
  )
}

export function parsePersistedState(stdout: string): KernelContextProviderResult {
  let payload: PersistedState
  try {
    payload = JSON.parse(stdout) as PersistedState
  } catch {
    return { kind: "unavailable", reason: "Invalid TonyMem SDD state response" }
  }

  if (payload.available !== true) {
    return {
      kind: "unavailable",
      reason: payload.reason ?? "TonyMem SDD state unavailable",
    }
  }

  if (!isBoundaryContext(payload.state)) {
    return { kind: "unavailable", reason: "TonyMem SDD state is incomplete" }
  }

  return { kind: "available", context: payload.state }
}

export function createKernelContextProvider(
  projectDirectory: string,
  options: KernelContextProviderOptions = {},
) {
  const pythonCommand = options.pythonCommand ?? process.env.TONYMEM_PYTHON ?? "python3"
  const stateScript =
    options.stateScript ??
    process.env.TONYMEM_SDD_STATE_SCRIPT ??
    `${projectDirectory}/local-memory/sdd_state.py`
  const timeoutMs = options.timeoutMs ?? 3000

  return {
    async getContext(input: { sessionID: string; tool: string }): Promise<KernelContextProviderResult> {
      if (input.tool !== "Task") {
        return { kind: "unavailable", reason: "Kernel context requested for non-Task tool" }
      }

      try {
        const stdout = options.readState
          ? JSON.stringify(await options.readState(projectDirectory, input.sessionID))
          : (
              await execFileAsync(
                pythonCommand,
                [stateScript, "--get", "--project", projectDirectory, "--session-id", input.sessionID],
                { cwd: projectDirectory, timeout: timeoutMs, maxBuffer: 1024 * 1024 },
              )
            ).stdout
        return parsePersistedState(stdout)
      } catch {
        return { kind: "unavailable", reason: "TonyMem SDD state provider unavailable" }
      }
    },
  }
}
