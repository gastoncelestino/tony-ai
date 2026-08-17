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
import { observeToolExecution } from "./tool-observation"
import { observationToEvidence } from "./tool-evidence"
import { extractToolAuthorizationRequest } from "./tool-authorization"

const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url))
const KERNEL_DIR = join(PLUGIN_DIR, "..", "..", "kernel")

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

interface RuntimeAuthorizationResult {
  allowed: boolean
  reason: string
}

export interface KernelClientLike {
  authorizeTool(tool: string): Promise<RuntimeAuthorizationResult>
  canStartPhase(phase: string): Promise<CanStartPhaseResult>
  recordDelegation(
    phase: string,
    subAgent: string,
    taskId?: string
  ): Promise<void>
  completeTask(
    taskId: string,
    evidence: unknown[],
  ): Promise<{
    decision: string
    allowed: boolean
    reason: string
    missing_artifacts: string[]
    missing_evidence: string[]
  }>
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

  async authorizeTool(tool: string): Promise<RuntimeAuthorizationResult> {
    const result = await this.runKernelCommand(["authorize_tool", tool])
    return {
      allowed: result.allowed === true,
      reason: typeof result.reason === "string" ? result.reason : "",
    }
  }

  async canStartPhase(phase: string): Promise<CanStartPhaseResult> {
    return this.runKernelCommand(["can_start_phase", phase])
  }

  async recordDelegation(phase: string, subAgent: string, taskId?: string): Promise<void> {
    await this.runKernelCommand(["record_delegation", phase, subAgent, taskId || ""])
  }

  async completeTask(taskId: string, evidence: unknown[]): Promise<{
    decision: string
    allowed: boolean
    reason: string
    missing_artifacts: string[]
    missing_evidence: string[]
  }> {
    const result = await this.runKernelCommand(["complete_task", taskId, JSON.stringify(evidence)])
    return {
      ...result,
      allowed: result.allowed === true,
    }
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
    `Kernel state will NOT advance; the next phase will be blocked.`
  )
}

function scopeViolationMessage(phase: string, result: { reason: string; scope_violations: string[] }): string {
  return (
    `[Tony Kernel] Scope violation blocked phase completion for "${phase}": ${result.reason}\n` +
    `Files outside allowed scope: ${result.scope_violations.join(", ")}`
  )
}

function kernelErrorMessage(context: string, error: unknown): string {
  const reason = error instanceof Error ? error.message : String(error)
  return `[Tony Kernel] ${context} failed: ${reason}`
}

const FSM_PHASES = new Set([
  "sdd-explore",
  "sdd-propose",
  "sdd-spec",
  "sdd-design",
  "sdd-tasks",
  "sdd-apply",
  "sdd-verify",
  "sdd-archive",
])

const NON_FSM_PREFIXES = new Set([
  "review-",
  "jd-",
  "sdd-init",
  "sdd-onboard",
])

const KNOWN_NON_FSM = new Set([
  "explore",
  "general",
])

export function isKernelPhase(subAgent: string): boolean {
  return FSM_PHASES.has(subAgent)
}

export function isNonFsmAgent(subAgent: string): boolean {
  if (KNOWN_NON_FSM.has(subAgent)) return true
  for (const prefix of NON_FSM_PREFIXES) {
    if (subAgent.startsWith(prefix)) return true
  }
  return false
}

export function derivePhase(args: Record<string, unknown>): string | null {
  if (typeof args.phase === "string" && args.phase.length > 0) {
    return args.phase.replace(/^sdd-/, "")
  }

  if (typeof args.subagent_type === "string") {
    const subAgent = args.subagent_type

    if (isKernelPhase(subAgent)) {
      return subAgent.replace(/^sdd-/, "")
    }

    if (isNonFsmAgent(subAgent)) {
      return null
    }
  }

  throw new KernelBlockedError(
    "[Tony Kernel] Unable to derive phase from task delegation"
  )
}

export async function taskExecuteBeforeHook(
  input: DelegationInput,
  output: DelegationOutput
): Promise<void> {
  const authorization = extractToolAuthorizationRequest(input.tool, input.arguments)

  try {
    const client = await getKernelClient()
    const toolResult = await client.authorizeTool(authorization.tool)

    if (!toolResult.allowed) {
      throw new KernelBlockedError(
        `[Tony Kernel] Tool authorization blocked "${authorization.tool}": ${toolResult.reason}`
      )
    }
  } catch (error) {
    if (error instanceof KernelBlockedError) throw error
    if (error instanceof KernelUnavailableError) throw error
    throw new KernelUnavailableError(
      kernelErrorMessage("Tool authorization", error)
    )
  }

  if (input.tool !== "Task") return

  const args = input.arguments as Record<string, unknown>
  const requestedPhase = derivePhase(args)

  if (requestedPhase === null) {
    return
  }

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

export async function taskExecuteAfterHook(
  input: { sessionID: string; tool: string; arguments: Record<string, unknown> },
  output: unknown
): Promise<void> {
  const observation = observeToolExecution(input, output)
  const evidence = observationToEvidence(observation)

  if (evidence) {
    try {
      const client = await getKernelClient()
      const result = await client.completeTask(evidence.task_id, [evidence.evidence])
      if (!result.allowed) {
        throw new KernelBlockedError(
          `[Tony Kernel] Task completion rejected for "${evidence.task_id}": ${result.reason}`
        )
      }
      return
    } catch (error) {
      if (error instanceof KernelBlockedError) throw error
      throw new KernelUnavailableError(kernelErrorMessage("Task evidence", error))
    }
  }

  // Non-task tools without an explicit task_id remain observation-only.
  if (input.tool !== "Task") return

  const args = observation.arguments
  const phase = derivePhase(args)

  if (phase === null) {
    return
  }

  try {
    const outputText = typeof observation.result === "string"
      ? observation.result
      : JSON.stringify(observation.result)
    const success = !outputText.includes("error") && !outputText.includes("Error")

    if (!success) {
      throw new KernelBlockedError(`[Tony Kernel] Phase completion rejected: task reported failure for phase ${phase}`)
    }

    const artifacts = args.artifacts as Array<{ kind: string; path: string; store: string; hash?: string }> | undefined
    const evidence = (args.evidence as Array<unknown> | undefined) || []
    const gitDiff = typeof args.gitDiff === "string" ? args.gitDiff : ""
    const allowedFiles = (args.allowedFiles as string[] | undefined) || []

    if (!artifacts || artifacts.length === 0) {
      throw new KernelBlockedError(
        `[Tony Kernel] Phase completion rejected for "${phase}": missing artifacts. ` +
          `Kernel state will NOT advance; the next phase will be blocked.`
      )
    }

    const client = await getKernelClient()

    if (gitDiff.length > 0) {
      const scopeResult = await client.checkScope(gitDiff, allowedFiles)
      if (!scopeResult.allowed) {
        throw new KernelBlockedError(scopeViolationMessage(phase, scopeResult))
      }
    }

    await client.recordPhaseCompletion(phase, artifacts, evidence).then((result) => {
      if (!result.allowed) {
        throw new KernelBlockedError(phaseCompletionBlockedMessage(phase, result))
      }
    })

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
  }
}

export default TonyKernelPlugin
