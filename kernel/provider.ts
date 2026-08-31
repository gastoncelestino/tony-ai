import { execFile } from "node:child_process"
import { promisify } from "node:util"
import { join } from "node:path"
import type { KernelBoundaryRequest } from "./protocol"

const execFileAsync = promisify(execFile)

export type KernelContextProviderResult =
  | { kind: "available"; context: KernelBoundaryRequest }
  | { kind: "unavailable"; reason: string }

export type KernelContextProviderOptions = {
  pythonCommand?: string
  contextScript?: string
  dbPath?: string
  timeoutMs?: number
}

type CanonicalContext = { available: boolean; reason?: string; state?: unknown }

function isContext(value: unknown): value is KernelBoundaryRequest {
  if (!value || typeof value !== "object") return false
  const context = value as Record<string, unknown>
  return typeof context.phase === "string" && typeof context.status === "string" &&
    Array.isArray(context.tasks) && context.tasks.every((task) => {
      if (!task || typeof task !== "object") return false
      const value = task as Record<string, unknown>
      return typeof value.id === "string" && typeof value.description === "string" &&
        typeof value.phase === "string" && Array.isArray(value.dependencies) &&
        value.dependencies.every((id) => typeof id === "string")
    }) && Array.isArray(context.completed) && context.completed.every((id) => typeof id === "string")
}

export function parseCanonicalContext(stdout: string): KernelContextProviderResult {
  let payload: CanonicalContext
  try { payload = JSON.parse(stdout) as CanonicalContext }
  catch { return { kind: "unavailable", reason: "Invalid canonical TaskSet context response" } }
  if (payload.available !== true) return { kind: "unavailable", reason: payload.reason ?? "Canonical TaskSet context unavailable" }
  if (!isContext(payload.state)) return { kind: "unavailable", reason: "Canonical TaskSet context is incomplete" }
  return { kind: "available", context: payload.state }
}

export function createKernelContextProvider(projectDirectory: string, options: KernelContextProviderOptions = {}) {
  const pythonCommand = options.pythonCommand ?? process.env.TONYMEM_PYTHON ?? "python3"
  const contextScript = options.contextScript ?? process.env.TONYMEM_TASKSET_CONTEXT_SCRIPT ?? `${projectDirectory}/kernel/task_set_context.py`
  const dbPath = options.dbPath ?? process.env.LOCAL_MEMORY_DB ?? join(projectDirectory, "local-memory", "memory.db")
  const timeoutMs = options.timeoutMs ?? 3000
  return {
    async getContext(input: { sessionID: string; tool: string }): Promise<KernelContextProviderResult> {
      if (input.tool.toLowerCase() !== "task") return { kind: "unavailable", reason: "Kernel context requested for non-Task tool" }
      const env = { ...process.env }
      delete env.LOCAL_MEMORY_DB
      try {
        const result = await execFileAsync(pythonCommand, [contextScript, "--get", "--project", projectDirectory, "--session-id", input.sessionID, "--db-path", dbPath], {
          cwd: projectDirectory, timeout: timeoutMs, maxBuffer: 1024 * 1024, env,
        })
        return parseCanonicalContext(result.stdout)
      } catch { return { kind: "unavailable", reason: "Canonical TaskSet context provider unavailable" } }
    },
  }
}
