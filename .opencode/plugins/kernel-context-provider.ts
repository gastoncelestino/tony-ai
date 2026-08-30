import { execFile } from "node:child_process"
import { promisify } from "node:util"
import { join } from "node:path"
import type { KernelBoundaryRequest } from "./kernel-boundary-protocol"

const execFileAsync = promisify(execFile)

export type KernelContextProviderResult =
  | { kind: "available"; context: KernelBoundaryRequest }
  | { kind: "unavailable"; reason: string }

export type KernelContextProviderOptions = {
  pythonCommand?: string
  contextScript?: string
  dbPath?: string
  timeoutMs?: number
  debugLog?: (event: string, details?: Record<string, unknown>) => void
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
  const dbPath =
    options.dbPath ??
    process.env.LOCAL_MEMORY_DB ??
    join(projectDirectory, "local-memory", "memory.db")
  const timeoutMs = options.timeoutMs ?? 3000
  const debugLog = options.debugLog

  return {
    async getContext(input: { sessionID: string; tool: string }): Promise<KernelContextProviderResult> {
      const childEnv = { ...process.env }
      delete childEnv.LOCAL_MEMORY_DB
      debugLog?.("context provider invoking", {
        sessionID: input.sessionID,
        tool: input.tool,
        pythonCommand,
        contextScript,
        dbPath,
        projectDirectory,
        cwd: projectDirectory,
        localMemoryDb: process.env.LOCAL_MEMORY_DB ?? null,
      })

      try {
        const result = await execFileAsync(
          pythonCommand,
          [
            contextScript,
            "--get",
            "--project",
            projectDirectory,
            "--session-id",
            input.sessionID,
            "--db-path",
            dbPath,
          ],
          { cwd: projectDirectory, timeout: timeoutMs, maxBuffer: 1024 * 1024, env: childEnv },
        )
        debugLog?.("context provider succeeded", {
          sessionID: input.sessionID,
          stdout: result.stdout,
          stderr: result.stderr,
        })
        return parseCanonicalContext(result.stdout)
      } catch (error) {
        const childError = error as { message?: unknown; stdout?: unknown; stderr?: unknown; code?: unknown }
        debugLog?.("context provider failed", {
          sessionID: input.sessionID,
          error: childError.message ?? String(error),
          code: childError.code ?? null,
          stdout: typeof childError.stdout === "string" ? childError.stdout : null,
          stderr: typeof childError.stderr === "string" ? childError.stderr : null,
        })
        return { kind: "unavailable", reason: "Canonical TaskSet context provider unavailable" }
      }
    },
  }
}
