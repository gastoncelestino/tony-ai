/**
 * Tony Kernel Plugin — OpenCode Plugin
 * 
 * Deterministic hook that intercepts task delegations and validates them
 * against the Tony Kernel state machine before allowing execution.
 * 
 * Fail-closed: any Kernel communication failure BLOCKS the delegation/completion.
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
  allowed: boolean
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

// ─── Errors ───────────────────────────────────────────────────────────────

export class KernelBlockedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelBlockedError"
  }
}

export class KernelUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelUnavailableError"
  }
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

  async canStartPhase(phase: string): Promise<CanStartPhaseResult> {
    const result = await this.runKernelCommand(["can_start_phase", phase])
    return result
  }

  async recordDelegation(phase: string, subAgent: string, taskId?: string): Promise<void> {
    await this.runKernelCommand(["record_delegation", phase, subAgent, taskId || ""])
  }

  async recordPhaseCompletion(phase: string, artifacts: Array<{ kind: string; path: string; store: string; hash?: string }>, evidence: unknown[] = []): Promise<void> {
    await this.runKernelCommand(["record_phase_completion", phase, JSON.stringify(artifacts), JSON.stringify(evidence)])
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
}

// ─── Global Kernel Client ────────────────────────────────────────────────

let kernelClient: KernelClient | null = null

async function getKernelClient(): Promise<KernelClient> {
  if (!kernelClient) {
    kernelClient = new KernelClient()
  }
  return kernelClient
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function phaseTransitionBlockedMessage(result: CanStartPhaseResult): string {
  return (
    `[Tony Kernel] Phase transition blocked: ${result.reason}\n` +
    `Current phase: ${result.current_phase}, Requested: ${result.requested_phase}\n` +
    (result.missing_artifacts.length > 0 ? `Missing artifacts: ${result.missing_artifacts.join(", ")}\n` : "") +
    (result.missing_evidence.length > 0 ? `Missing evidence: ${result.missing_evidence.join(", ")}\n` : "") +
    (result.scope_violations.length > 0 ? `Scope violations: ${result.scope_violations.join(", ")}\n` : "") +
    (result.retry_status && result.retry_status.exhausted ? "\nRetry budget exhausted. Human required.\n" : "") +
    (result.next_action ? `Next action: ${result.next_action}` : "")
  )
}

function kernelErrorMessage(context: string, error: unknown): string {
  const reason = error instanceof Error ? error.message : String(error)
  return `[Tony Kernel] ${context} failed: ${reason}`
}

const PHASE_BY_SUBAGENT: Record<string, string> = {
  "sdd-explore": "explore",
  "sdd-propose": "propose",
  "sdd-spec": "spec",
  "sdd-design": "design",
  "sdd-tasks": "tasks",
  "sdd-apply": "apply",
  "sdd-verify": "verify",
  "sdd-archive": "archive",
}

export function derivePhase(args: Record<string, unknown>): string {
  if (typeof args.phase === "string" && args.phase.length > 0) {
    return args.phase
  }

  if (typeof args.subagent_type === "string") {
    const phase = PHASE_BY_SUBAGENT[args.subagent_type]

    if (phase) {
      return phase
    }
  }

  throw new KernelBlockedError(
    "[Tony Kernel] Unable to derive phase from task delegation"
  )
}

// ─── Hook: task.execute.before ────────────────────────────────────────────

/**
 * Hook that intercepts task delegations before they execute.
 * Validates against the Kernel state machine before allowing delegation.
 * 
 * Fail-closed: any Kernel error blocks the delegation.
 */
async function taskExecuteBeforeHook(
  input: DelegationInput,
  output: DelegationOutput
): Promise<void> {
  if (input.tool !== "Task") return

  const args = input.arguments as Record<string, unknown>
  const requestedPhase = derivePhase(args)

  try {
    const client = await getKernelClient()
    const result = await client.canStartPhase(requestedPhase)

    if (!result.allowed) {
      throw new KernelBlockedError(phaseTransitionBlockedMessage(result))
    }

    await client.recordDelegation(requestedPhase, "sub-agent")
  } catch (error) {
    if (error instanceof KernelBlockedError) {
      throw error
    }

    if (error instanceof KernelUnavailableError) {
      throw error
    }

    throw new KernelUnavailableError(
      kernelErrorMessage("Delegation gate", error)
    )
  }
}

// ─── Hook: task.execute.after ─────────────────────────────────────────────

/**
 * Hook that captures task completion and records phase completion.
 * 
 * Fail-closed: any Kernel error or missing artifacts blocks completion.
 */
async function taskExecuteAfterHook(
  input: { sessionID: string; tool: string; arguments: Record<string, unknown> },
  output: unknown
): Promise<void> {
  if (input.tool !== "Task") return

  const args = input.arguments as Record<string, unknown>
  const phase = derivePhase(args)

  try {
    const outputText = typeof output === "string" ? output : JSON.stringify(output)
    const success = !outputText.includes("error") && !outputText.includes("Error")

    if (!success) {
      throw new KernelBlockedError(`[Tony Kernel] Phase completion rejected: task reported failure for phase ${phase}`)
    }

    const artifacts = args.artifacts as Array<{ kind: string; path: string; store: string; hash?: string }> | undefined
    const evidence = (args.evidence as Array<unknown> | undefined) || []

    if (!artifacts || artifacts.length === 0) {
      throw new KernelBlockedError(
        `[Tony Kernel] Phase completion rejected for "${phase}": missing artifacts. ` +
          `Kernel state will NOT advance; the next phase will be blocked.`
      )
    }

    const client = await getKernelClient()
    await client.recordPhaseCompletion(phase, artifacts, evidence)

    // Post-phase validation: verify the phase is actually complete in the kernel
    const status = await client.getStatus()
    const currentPhase = status.current_phase
    if (currentPhase !== phase) {
      throw new KernelBlockedError(
        `[Tony Kernel] Post-phase validation failed: kernel state is ${currentPhase}, expected ${phase} after completion`
      )
    }
  } catch (error) {
    if (error instanceof KernelBlockedError) {
      throw error
    }

    if (error instanceof KernelUnavailableError) {
      throw error
    }

    throw new KernelUnavailableError(
      kernelErrorMessage("Phase completion", error)
    )
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
