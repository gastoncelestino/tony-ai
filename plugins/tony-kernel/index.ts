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
const KERNEL_DIR = join(PLUGIN_DIR, "..", "..", "kernel")

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

// ─── Kernel Python Subprocess Client ──────────────────────────────────────

class KernelClient {
  private kernelModulePath: string

  constructor() {
    this.kernelModulePath = join(KERNEL_DIR, "orchestrator_integration.py")
  }

  private async runKernelCommand(args: string[]): Promise<any> {
    return new Promise((resolve, reject) => {
      const proc = spawn(["python3", "-m", "kernel.orchestrator_integration", ...args], {
        cwd: join(KERNEL_DIR, ".."),
        stdout: "pipe",
        stderr: "pipe",
      })

      let stdout = ""
      let stderr = ""

      proc.stdout?.on("data", (data) => { stdout += data.toString() })
      proc.stderr?.on("data", (data) => { stderr += data.toString() })

      proc.exited.then((code) => {
        if (code === 0) {
          try {
            resolve(JSON.parse(stdout.trim()))
          } catch {
            resolve({ success: true, output: stdout.trim() })
          }
        } else {
          reject(new Error(`Kernel error (${code}): ${stderr}`))
        }
      })
    })
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
    const result = await this.runKernelCommand(["can_start_phase", phase])
    return result
  }

  async recordDelegation(phase: string, subAgent: string, taskId?: string): Promise<void> {
    await this.runKernelCommand(["record_delegation", phase, subAgent, taskId || ""])
  }

  async recordPhaseCompletion(phase: string, artifacts: Array<{ kind: string; path: string; store: string; hash?: string }>): Promise<void> {
    await this.runKernelCommand(["record_phase_completion", phase, JSON.stringify(artifacts)])
  }

  async checkScope(gitDiff: string, allowedFiles: string[]): Promise<{
    decision: string
    reason: string
    scope_violations: string[]
  }> {
    const result = await this.runKernelCommand(["check_scope", JSON.stringify(gitDiff), JSON.stringify(allowedFiles)])
    return result
  }

  async getStatus(): Promise<Record<string, unknown>> {
    return this.runKernelCommand(["status"])
  }

  async healthCheck(): Promise<boolean> {
    try {
      const result = await this.runKernelCommand(["health"])
      return result.status === "ok"
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
  }
  return kernelClient
}

// ─── Hook: tool.execute.before ────────────────────────────────────────────

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
    const result = await client.canStartPhase(requestedPhase)

    if (!result.allowed) {
      // Block the delegation by throwing an error
      throw new Error(
        `[Tony Kernel] Phase transition blocked: ${result.reason}\n` +
        `Current phase: ${result.current_phase}, Requested: ${result.requested_phase}\n` +
        (result.missing_artifacts.length > 0 ? `Missing artifacts: ${result.missing_artifacts.join(", ")}\n` : "") +
        (result.missing_evidence.length > 0 ? `Missing evidence: ${result.missing_evidence.join(", ")}\n` : "") +
        (result.scope_violations.length > 0 ? `Scope violations: ${result.scope_violations.join(", ")}\n` : "") +
        (result.retry_status && (result.retry_status as any).exhausted ? "\nRetry budget exhausted. Human required." : "") +
        (result.next_action ? `\nNext action: ${result.next_action}` : "")
      )
    }

    // Record delegation for tracking
    await client.recordDelegation(requestedPhase, "sub-agent")
    
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("[Tony Kernel]")) {
      throw error // Re-throw our blocking errors
    }
    console.error("[tony-kernel] Hook error (non-blocking):", error)
  }
}

// ─── Hook: tool.execute.after ─────────────────────────────────────────────

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
    const client = await getKernelClient()
    
    // Check if task completed successfully
    const outputText = typeof output === "string" ? output : JSON.stringify(output)
    const success = !outputText.includes("error") && !outputText.includes("Error")

    if (success) {
      // Record phase completion if we have artifacts
      if (args.artifacts && Array.isArray(args.artifacts)) {
        await client.recordPhaseCompletion(phase, args.artifacts as Array<{ kind: string; path: string; store: string; hash?: string }>)
      }
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
  
  async onLoad() {
    console.log("[tony-kernel] Plugin loaded, kernel integration active")
  },
  
  async onUnload() {
    // Cleanup if needed
  }
}

export default TonyKernelPlugin
