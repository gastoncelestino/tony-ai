import { execFile } from "node:child_process"
import { promisify } from "node:util"
import type { KernelBoundaryRequest } from "./kernel-boundary-protocol"

const execFileAsync = promisify(execFile)

export type KernelContextProviderResult =
  | { kind: "available"; context: KernelBoundaryRequest }
  | { kind: "unavailable"; reason: string }

export type KernelContextProviderOptions = {
  pythonCommand?: string
  contextScript?: string
  timeoutMs?: number
}

type CanonicalContext = {
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

export function parseCanonicalContext(stdout: string): KernelContextProviderResult {
  let payload: CanonicalContext
  try {
    payload = JSON.parse(stdout) as CanonicalContext
  } catch {
    return { kind: "unavailable", reason: "Invalid canonical TaskSet context response" }
  }

  if (payload.available !== true) {
    return {
      kind: "unavailable",
      reason: payload.reason ?? "Canonical TaskSet context unavailable",
    }
  }

  if (!isBoundaryContext(payload.state)) {
    return { kind: "unavailable", reason: "Canonical TaskSet context is incomplete" }
  }

  return { kind: "available", context: payload.state }
}

export function createKernelContextProvider(
  projectDirectory: string,
  options: KernelContextProviderOptions = {},
) {
  const pythonCommand = options.pythonCommand ?? process.env.TONYMEM_PYTHON ?? "python3"
  const contextScript =
    options.contextScript ??
    process.env.TONYMEM_TASKSET_CONTEXT_SCRIPT ??
    `${projectDirectory}/kernel/task_set_context.py`
  const timeoutMs = options.timeoutMs ?? 3000

  return {
    async getContext(input: { sessionID: string; tool: string }): Promise<KernelContextProviderResult> {
      if (input.tool.toLowerCase() !== "task") {
        return { kind: "unavailable", reason: "Kernel context requested for non-Task tool" }
      }

      try {
        const stdout = (
          await execFileAsync(
            pythonCommand,
            [contextScript, "--get", "--project", projectDirectory, "--session-id", input.sessionID],
            { cwd: projectDirectory, timeout: timeoutMs, maxBuffer: 1024 * 1024 },
          )
        ).stdout
        return parseCanonicalContext(stdout)
      } catch {
        return { kind: "unavailable", reason: "Canonical TaskSet context provider unavailable" }
      }
    },
  }
}
