import { spawn } from "node:child_process"

export type TonyActionPlan =
  | {
      action: "delegate"
      phase: string
      task_id: string
      agent: string
      objective: string
      files: string[]
      allowed_tools: string[]
      max_iterations: number
    }
  | { action: "done"; reason: string }

export type TonyKernelResult = { available: true; plan: TonyActionPlan } | { available: false; reason: string }

type KernelResponse = TonyKernelResult | { ok: true; result?: Record<string, unknown> } | { ok: false; reason: string }

type CompletionResult = { ok: true; result?: Record<string, unknown> } | { ok: false; reason: string }

const command = () => process.env.TONYMEM_PYTHON ?? "python3"
const args = () => ["-m", "kernel.boundary"]
const timeoutMs = 5000

function call<T extends KernelResponse>(payload: Record<string, unknown>): Promise<T> {
  return new Promise((resolve, reject) => {
    const root = process.env.TONY_KERNEL_ROOT
    const env = root ? { ...process.env, PYTHONPATH: [root, process.env.PYTHONPATH].filter(Boolean).join(":"), } : process.env
    const child = spawn(command(), args(), { cwd: root, env, stdio: ["pipe", "pipe", "pipe"] })
    let stdout = ""
    let stderr = ""
    let settled = false
    const finish = (fn: () => void) => { if (settled) return; settled = true; clearTimeout(timer); fn() }
    const timer = setTimeout(() => {
      child.kill()
      finish(() => reject(new Error("Tony Kernel transport timed out")))
    }, timeoutMs)
    child.stdout.setEncoding("utf8")
    child.stderr.setEncoding("utf8")
    child.stdout.on("data", (chunk: string) => { stdout += chunk })
    child.stderr.on("data", (chunk: string) => { stderr += chunk })
    child.on("error", (error) => finish(() => reject(error)))
    child.on("close", (code) => {
      if (settled) return
      if (code !== 0) return finish(() => reject(new Error(stderr.trim() || `Tony Kernel exited with code ${code}`)))
      try {
        const response = JSON.parse(stdout.trim()) as T
        finish(() => resolve(response))
      } catch (error) {
        finish(() => reject(new Error(`Invalid Tony Kernel response: ${error instanceof Error ? error.message : String(error)}`)))
      }
    })
    child.stdin.end(JSON.stringify(payload))
  })
}

export async function nextAction(projectDirectory: string, sessionID: string): Promise<TonyKernelResult> {
  return call<TonyKernelResult>({ operation: "next_action", project_directory: projectDirectory, session_id: sessionID })
}

export async function completeBootstrap(projectDirectory: string, sessionID: string, decomposition: string): Promise<CompletionResult> {
  return call<CompletionResult>({
    operation: "complete_bootstrap",
    project_directory: projectDirectory,
    session_id: sessionID,
    decomposition,
  })
}

export async function completeTask(projectDirectory: string, sessionID: string, taskID: string, evidence: string): Promise<CompletionResult> {
  return call<CompletionResult>({
    operation: "complete_task",
    project_directory: projectDirectory,
    session_id: sessionID,
    task_id: taskID,
    evidence,
  })
}
