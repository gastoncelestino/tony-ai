/**
 * Tony Kernel Plugin — OpenCode Plugin
 * 
 * Deterministic hook that intercepts task delegations and validates them
 * against the Tony Kernel state machine before allowing execution.
 * 
 * Fail-closed: any Kernel communication failure BLOCKS the delegation/completion.
 */

import type { Plugin } from "@opencode-ai/plugin"
import { spawn } from "node:child_process"
import { join } from "path"
import { fileURLToPath } from "url"
import { dirname } from "path"

const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url))
const KERNEL_DIR = join(PLUGIN_DIR, "..", "kernel")

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

export interface KernelClientLike {
  canStartPhase(phase: string): Promise<CanStartPhaseResult>
  recordDelegation(
    phase: string,
    subAgent: string,
    taskId?: string
  ): Promise<void>
  recordPhaseCompletion(
    phase: string,
    artifacts: Array<{
      kind: string
      path: string
      store: string
      hash?: string
    }>,
    evidence?: unknown[]
  ): Promise<{
    decision: string
    allowed: boolean
    reason: string
    missing_artifacts: string[]
    missing_evidence: string[]
  }>
  checkScope(
    gitDiff: string,
    allowedFiles: string[]
  ): Promise<{
    decision: string
    allowed: boolean
    reason: string
    scope_violations: string[]
  }>
  getStatus(): Promise<Record<string, unknown>>
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

class KernelClient implements KernelClientLike {
  private kernelModulePath: string

  constructor() {
    this.kernelModulePath = join(KERNEL_DIR, "orchestrator_integration.py")
  }

  private async runKernelCommand(args: string[]): Promise<any> {
    return new Promise((resolve, reject) => {
      const proc = spawn("python3", ["-m", "kernel.cli", ...args], {
        cwd: join(KERNEL_DIR, ".."),
        stdio: ["pipe", "pipe", "pipe"],
      })

      let stdout = ""
      let stderr = ""

      proc.stdout.on("data", (data: Buffer) => { stdout += data.toString() })
      proc.stderr.on("data", (data: Buffer) => { stderr += data.toString() })

      proc.on("close", (code) => {
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

      proc.on("error", (err) => {
        reject(new Error(`Kernel spawn error: ${err.message}`))
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

  async recordPhaseCompletion(phase: string, artifacts: Array<{ kind: string; path: string; store: string; hash?: string }>, evidence: unknown[] = []): Promise<{
    decision: string
    allowed: boolean
    reason: string
    missing_artifacts: string[]
    missing_evidence: string[]
  }> {
    const result = await this.runKernelCommand(["record_phase_completion", phase, JSON.stringify(artifacts), JSON.stringify(evidence)])
    return {
      ...result,
      allowed: result.allowed === true,
    }
  }

  async checkScope(gitDiff: string, allowedFiles: string[]): Promise<{
    decision: string
    allowed: boolean
    reason: string
    scope_violations: string[]
  }> {
    const result = await this.runKernelCommand(["check_scope", gitDiff, JSON.stringify(allowedFiles)])
    return {
      ...result,
      allowed: result.allowed === true,
    }
  }

  async getStatus(): Promise<Record<string, unknown>> {
    return this.runKernelCommand(["status"])
  }
}

// ─── Global Kernel Client ────────────────────────────────────────────────

let kernelClient: KernelClientLike | null = null

async function getKernelClient(): Promise<KernelClientLike> {
  if (!kernelClient) {
    kernelClient = new KernelClient()
  }
  return kernelClient
}

export function __setKernelClientForTests(
  client: KernelClientLike | null
): void {
  kernelClient = client
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

function phaseCompletionBlockedMessage(phase: string, result: { reason: string; missing_artifacts: string[]; missing_evidence: string[] }): string {
  return (
    `[Tony Kernel] Phase completion rejected for "${phase}": ${result.reason}\n` +
    (result.missing_artifacts.length > 0 ? `Missing artifacts: ${result.missing_artifacts.join(", ")}\n` : "") +
    (result.missing_evidence.length > 0 ? `Invalid/missing evidence: ${result.missing_evidence.join(", ")}\n` : "") +
    `Kernel state will NOT advance; completion is blocked.`
  )
}

function inferPhase(input: DelegationInput): string | null {
  const explicit = typeof input.arguments.phase === "string" ? input.arguments.phase : null
  if (explicit) return explicit

  const subagent = typeof input.arguments.subagent_type === "string" ? input.arguments.subagent_type : null
  const mapping: Record<string, string> = {
    "sdd-explore": "explore",
    "sdd-spec": "spec",
    "sdd-design": "design",
    "sdd-tasks": "tasks",
    "sdd-apply": "sdd-apply",
    "sdd-archive": "archive",
  }
  return subagent ? mapping[subagent] || null : null
}

function isTaskTool(input: DelegationInput): boolean {
  return input.tool === "Task"
}

export const taskExecuteBeforeHook = async (
  input: DelegationInput
): Promise<void> => {
  if (!isTaskTool(input)) return

  const phase = inferPhase(input)
  if (!phase) {
    throw new KernelBlockedError(
      "[Tony Kernel] Cannot determine phase from Task arguments; delegation blocked."
    )
  }

  const client = await getKernelClient()
  try {
    const result = await client.canStartPhase(phase)
    if (!result || result.allowed !== true) {
      throw new KernelBlockedError(
        phaseTransitionBlockedMessage(result || {
          reason: "Kernel returned an empty response",
          current_phase: "unknown",
          requested_phase: phase,
          missing_artifacts: [],
          missing_evidence: [],
          scope_violations: [],
          retry_status: null,
          next_action: null,
          decision: "block",
          allowed: false,
        })
      )
    }

    const subAgent = typeof input.arguments.subagent_type === "string"
      ? input.arguments.subagent_type
      : phase
    const taskId = typeof input.arguments.task_id === "string"
      ? input.arguments.task_id
      : input.sessionID
    await client.recordDelegation(phase, subAgent, taskId)
  } catch (error) {
    if (error instanceof KernelBlockedError) {
      throw error
    }
    if (error instanceof KernelUnavailableError) {
      throw error
    }
    throw new KernelUnavailableError(
      `[Tony Kernel] Delegation gate failed: ${error instanceof Error ? error.message : String(error)}`
    )
  }
}

export const taskExecuteAfterHook = async (
  input: DelegationInput,
  output: DelegationOutput
): Promise<void> => {
  if (!isTaskTool(input)) return

  const phase = inferPhase(input)
  if (!phase) {
    throw new KernelBlockedError(
      "[Tony Kernel] Cannot determine phase from Task arguments; completion blocked."
    )
  }

  if (!output || output.success !== true) {
    throw new KernelBlockedError(
      `[Tony Kernel] Task output indicates failure; phase "${phase}" cannot complete.`
    )
  }

  const client = await getKernelClient()
  try {
    if (typeof input.arguments.git_diff === "string") {
      const allowedFiles = Array.isArray(input.arguments.allowed_files)
        ? input.arguments.allowed_files.filter((value): value is string => typeof value === "string")
        : []
      const scope = await client.checkScope(input.arguments.git_diff, allowedFiles)
      if (!scope || scope.allowed !== true) {
        throw new KernelBlockedError(
          `[Tony Kernel] Scope check blocked completion: ${scope?.reason || "Kernel returned an empty response"}`
        )
      }
    }

    const artifacts = Array.isArray(input.arguments.artifacts)
      ? input.arguments.artifacts.filter((artifact): artifact is { kind: string; path: string; store: string; hash?: string } => (
        artifact && typeof artifact === "object" &&
        typeof artifact.kind === "string" &&
        typeof artifact.path === "string" &&
        typeof artifact.store === "string"
      ))
      : []

    if (artifacts.length === 0) {
      throw new KernelBlockedError(
        `[Tony Kernel] Task "${phase}" completed without artifacts; phase completion is blocked.`
      )
    }

    const evidence = Array.isArray(input.arguments.evidence) ? input.arguments.evidence : []
    const result = await client.recordPhaseCompletion(phase, artifacts, evidence)
    if (!result || result.allowed !== true) {
      throw new KernelBlockedError(
        phaseCompletionBlockedMessage(phase, result || {
          reason: "Kernel returned an empty response",
          missing_artifacts: [],
          missing_evidence: [],
        })
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
      `[Tony Kernel] Phase completion failed: ${error instanceof Error ? error.message : String(error)}`
    )
  }
}

export const tonyKernelPlugin: Plugin = async () => ({
  tool: {
    execute: {
      before: taskExecuteBeforeHook,
      after: taskExecuteAfterHook,
    },
  },
})
