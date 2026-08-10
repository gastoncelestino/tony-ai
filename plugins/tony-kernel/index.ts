/**
 * Tony Kernel Plugin — OpenCode Plugin
 * 
 * Deterministic hook that intercepts task delegations and validates them
 * against the Tony Kernel state machine before allowing execution.
 */

import type { Plugin } from "@opencode-ai/plugin"
import { spawn } from "bun"
import { join } from "path"
import { fileURLToPath } from "url"
import { dirname } from "path"

const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url))
const KERNEL_SERVER_PATH = join(PLUGIN_DIR, "kernel_server.py")
const KERNEL_PORT = 7438
const KERNEL_BASE_URL = `http://127.0.0.1:${7438}`

// ─── Types ────────────────────────────────────────────────────────────────

interface CanStartPhaseResult {
  decision: string
  reason: string
  current_phase: string
  requested_phase: string
  missing_artifacts: string[]
  missing_evidence: string[]
  scope_violations: string[]
  retry_status: Record<string, unknown> | null
  next_action: string | null
}

interface DelegationInput {
  sessionID: string
  tool: string
  arguments: Record<string, unknown>
}

interface DelegationOutput {
  success: boolean
  result?: unknown
}

// ─── Kernel HTTP Client ────────────────────────────────────────────────────

class KernelClient {
  private baseUrl: string
  private serverProcess: ReturnType<typeof spawn> | null = null

  constructor(baseUrl: string = KERNEL_BASE_URL) {
    this.baseUrl = baseUrl
  }

  async startServer(): Promise<void> {
    if (this.serverProcess) return

    const kernelServerPath = new URL("./kernel_server.py", import.meta.url).pathname
    
    this.serverProcess = spawn(["python3", kernelServerPath], {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONPATH: "/workspace/7cf8dcfc-72e2-49b9-9795-75440ba1be96/sessions/agent_0a609c26-9e31-4ad3-abf7-5af14c9f5367" }
    })

    this.serverProcess.stdout?.on("data", (data) => {
      console.log(`[tony-kernel] ${data.toString().trim()}`)
    })
    this.serverProcess.stderr?.on("data", (data) => {
      console.error(`[tony-kernel] ${data.toString().trim()}`)
    })

    // Wait for server to be ready
    await this.waitForReady()
  }

  private async waitForReady(timeout = 10000): Promise<void> {
    const start = Date.now()
    while (Date.now() - start < timeout) {
      try {
        const response = await fetch(`${this.baseUrl}/health`, { method: "GET" })
        if (response.ok) return
      } catch {
        // Server not ready yet
      }
      await new Promise(r => setTimeout(r, 100))
    }
    throw new Error("Kernel server failed to start within timeout")
  }

  async stopServer(): Promise<void> {
    if (this.serverProcess) {
      this.serverProcess.kill()
      this.serverProcess = null
    }
  }

  async canStartPhase(phase: string): Promise<{
    allowed: boolean
    decision: string
    reason: string
    current_phase: string
    requested_phase: string
    missing_artifacts: string[]
    missing_evidence: string[]
    scope_violations: string[]
    retry_status: Record<string, unknown> | null
    next_action: string | null
  }> {
    const response = await fetch(`${this.baseUrl}/can_start_phase`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phase })
    })
    if (!response.ok) {
      throw new Error(`Kernel error: ${await response.text()}`)
    }
    return response.json()
  }

  async recordDelegation(phase: string, subAgent: string, taskId?: string): Promise<void> {
    await fetch(`${this.baseUrl}/record_delegation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phase, sub_agent: subAgent, task_id: taskId })
    })
  }

  async recordPhaseCompletion(phase: string, artifacts: Array<{ kind: string; path: string; store: string; hash?: string }>, evidence: unknown[] = []): Promise<void> {
    await fetch(`${this.baseUrl}/record_phase_completion`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phase, artifacts, evidence })
    })
  }

  async checkScope(gitDiff: string, allowedFiles: string[]): Promise<{
    decision: string
    reason: string
    scope_violations: string[]
  }> {
    const response = await fetch(`${this.baseUrl}/check_scope`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ git_diff: gitDiff, allowed_files: allowedFiles })
    })
    return response.json()
  }

  async getStatus(): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.baseUrl}/status`)
    return response.json()
  }

  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`, { method: "GET" })
      return response.ok
    } catch {
      return false
    }
  }
}

// ─── Global Kernel Client ────────────────────────────────────────────────

let kernelClient: KernelClient | null = null

async function getKernelClient(): Promise<KernelClient> {
  if (!kernelClient) {
    kernelClient = new KernelClient()
    await kernelClient.startServer()
  }
  return kernelClient
}

// ─── Hook: task.execute.before ───────────────────────────────────────────

/**
 * Hook that intercepts task delegations before they execute.
 * Validates against the Kernel state machine before allowing delegation.
 */
async function taskExecuteBeforeHook(
  input: DelegationInput,
  output: DelegationOutput
): Promise<void> {
  // Only intercept Task tool delegations
  if (input.tool !== "Task") return

  const args = input.arguments as Record<string, unknown>
  const requestedPhase = (args.phase as string) || "apply" // Default to apply

  try {
    const client = await getKernelClient()
    const result = await kernelClient.canStartPhase(requestedPhase)

    if (!result.allowed) {
      // Block the delegation
      throw new Error(
        `[Tony Kernel] Phase transition blocked: ${result.reason}\n` +
        `Current phase: ${result.current_phase}, Requested: ${result.requested_phase}\n` +
        (result.missing_artifacts.length > 0 ? `Missing artifacts: ${result.missing_artifacts.join(", ")}\n` : "") +
        (result.missing_evidence.length > 0 ? `Missing evidence: ${result.missing_evidence.join(", ")}\n` : "") +
        (result.scope_violations.length > 0 ? `Scope violations: ${result.scope_violations.join(", ")}\n` : "") +
        (result.retry_status && result.retry_status.exhausted ? "\nRetry budget exhausted. Human required." : "") +
        (result.next_action ? `\nNext action: ${result.next_action}` : "")
      )
    }

    // Record delegation for tracking
    const kernelClient = await getKernelClient()
    await kernelClient.recordDelegation(requestedPhase, "sub-agent")
    
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("[Tony Kernel]")) {
      throw error // Re-throw our blocking errors
    }
    console.error("[tony-kernel] Hook error (non-blocking):", error)
  }
}

// ─── Hook: task.execute.after ────────────────────────────────────────────

/**
 * Hook that captures task completion and records phase completion.
 */
async function taskExecuteAfterHook(
  input: { sessionID: string; tool: string; arguments: Record<string, unknown> },
  output: unknown
): Promise<void> {
  if (input.tool !== "Task") return

  const args = input.arguments as Record<string, unknown>
  const phase = (input.arguments.phase as string) || "apply"

  try {
    // Check if task completed successfully
    const outputText = typeof output === "string" ? output : JSON.stringify(output)
    const success = !outputText.includes("error") && !outputText.includes("Error")

    if (success) {
      // Could record phase completion here if we have artifacts
      // For now, just log
      console.log(`[tony-kernel] Task completed for phase: ${phase}`)
    }
  } catch (error) {
    console.error("[tony-kernel] After hook error:", error)
  }
}

// ─── Plugin Definition ───────────────────────────────────────────────────

const TonyKernelPlugin: Plugin = {
  name: "tony-kernel",
  version: "1.0.0",
  description: "Tony Kernel — Deterministic hook for phase transitions, evidence tracking, and scope enforcement",
  
  hooks: {
    "tool.execute.before": taskExecuteBeforeHook,
    "tool.execute.after": taskExecuteAfterHook,
  },
  
  // Cleanup on plugin unload
  async onUnload() {
    // Cleanup handled by process exit
  }
}

export default TonyKernelPlugin