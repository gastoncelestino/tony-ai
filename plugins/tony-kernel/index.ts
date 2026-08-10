/**
 * Tony Kernel Plugin — OpenCode Plugin
 *
 * Deterministic hook that intercepts task delegations and validates them
 * against the Tony Kernel state machine before allowing execution.
 *
 * Talks to the kernel through `python3 -m kernel.cli` (state persisted by
 * kernel/persistence.py between calls), so a phase completed earlier is seen
 * by later checks.
 */

import type { Plugin } from "@opencode-ai/plugin"
import { spawn } from "bun"
import { join } from "path"
import { fileURLToPath } from "url"
import { dirname } from "path"

const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(PLUGIN_DIR, "..", "..")

// Maps an orchestrator sub-agent to its kernel phase.
const SUBAGENT_TO_PHASE: Record<string, string> = {
  "sdd-explore": "explore",
  "sdd-propose": "propose",
  "sdd-spec": "spec",
  "sdd-design": "design",
  "sdd-tasks": "tasks",
  "sdd-apply": "apply",
  "sdd-verify": "verify",
  "sdd-archive": "archive",
  explore: "explore",
  general: "apply",
}

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

// ─── Kernel Python Subprocess Client ──────────────────────────────────────

class KernelClient {
  private async runKernelCommand(args: string[]): Promise<any> {
    return new Promise((resolve, reject) => {
      const proc = spawn(["python3", "-m", "kernel.cli", ...args], {
        cwd: REPO_ROOT,
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
            reject(new Error(`[tony-kernel] Non-JSON kernel output: ${stdout.trim()}`))
          }
        } else {
          reject(new Error(`[tony-kernel] Kernel error (${code}): ${stderr}`))
        }
      })
    })
  }

  async canStartPhase(phase: string): Promise<CanStartPhaseResult> {
    return this.runKernelCommand(["can_start_phase", phase])
  }

  async recordDelegation(phase: string, subAgent: string, taskId?: string): Promise<void> {
    await this.runKernelCommand(["record_delegation", phase, subAgent, taskId || ""])
  }

  async recordPhaseCompletion(phase: string, artifacts: Array<{ kind: string; path: string; store: string; hash?: string }>): Promise<void> {
    await this.runKernelCommand(["record_phase_completion", phase, JSON.stringify(artifacts)])
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

// Derives the kernel phase from the delegation arguments. The Task tool has no
// native `phase` field, so we map the sub-agent type; an explicit `phase`
// argument always wins.
function derivePhase(args: Record<string, unknown>): string {
  if (typeof args.phase === "string" && args.phase) {
    return args.phase
  }
  const subagent = String(args.subagent_type || args.subagentType || "")
  return SUBAGENT_TO_PHASE[subagent] || "apply"
}

// ─── Hook: tool.execute.before ────────────────────────────────────────────

/**
 * Hook that intercepts task delegations before they execute.
 * Validates against the Kernel state machine before allowing delegation.
 */
async function taskExecuteBeforeHook(
  input: DelegationInput,
  _output: unknown
): Promise<void> {
  if (input.tool !== "Task") return

  const args = input.arguments as Record<string, unknown>
  const requestedPhase = derivePhase(args)

  try {
    const client = await getKernelClient()
    const result = await client.canStartPhase(requestedPhase)

    if (!result.allowed) {
      const retryExhausted = result.retry_status && (result.retry_status as any).exhausted
      throw new Error(
        `[Tony Kernel] Phase transition blocked: ${result.reason}\n` +
        `Current phase: ${result.current_phase}, Requested: ${result.requested_phase}\n` +
        (result.missing_artifacts?.length > 0 ? `Missing artifacts: ${result.missing_artifacts.join(", ")}\n` : "") +
        (result.missing_evidence?.length > 0 ? `Missing evidence: ${result.missing_evidence.join(", ")}\n` : "") +
        (result.scope_violations?.length > 0 ? `Scope violations: ${result.scope_violations.join(", ")}\n` : "") +
        (retryExhausted ? "\nRetry budget exhausted. Human required." : "") +
        (result.next_action ? `\nNext action: ${result.next_action}` : "")
      )
    }

    // Record delegation for tracking (non-fatal if it fails).
    try {
      await client.recordDelegation(requestedPhase, "sub-agent")
    } catch {
      /* non-blocking */
    }
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
  _output: unknown
): Promise<void> {
  if (input.tool !== "Task") return

  const args = input.arguments as Record<string, unknown>
  const phase = derivePhase(args)

  try {
    const client = await getKernelClient()

    if (Array.isArray(args.artifacts)) {
      await client.recordPhaseCompletion(
        phase,
        args.artifacts as Array<{ kind: string; path: string; store: string; hash?: string }>
      )
      console.log(`[tony-kernel] Recorded phase completion for phase: ${phase}`)
    }
  } catch (error) {
    console.error("[tony-kernel] After hook error (non-blocking):", error)
  }
}

// ─── Plugin Definition ───────────────────────────────────────────────────

const TonyKernelPlugin: Plugin = {
  name: "tony-kernel",
  version: "1.1.0",
  description: "Tony Kernel — Deterministic hook for phase transitions, evidence tracking, and scope enforcement",

  hooks: {
    "tool.execute.before": taskExecuteBeforeHook,
    "tool.execute.after": taskExecuteAfterHook,
  },

  async onLoad() {
    const client = await getKernelClient()
    const ok = await client.healthCheck()
    console.log(`[tony-kernel] Plugin loaded. Kernel health: ${ok ? "ok" : "unreachable"}`)
  },

  async onUnload() {
    // Cleanup if needed
  },
}

export default TonyKernelPlugin
