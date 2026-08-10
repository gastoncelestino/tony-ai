/**
 * Kernel Client — Communicates with Python Kernel via subprocess
 */

import { join } from "path"
import { fileURLToPath } from "url"
import { dirname } from "path"

const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url))
const KERNEL_DIR = join(PLUGIN_DIR, "..", "..", "kernel")

export interface CanStartPhaseResult {
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

export class KernelClient {
  private kernelModulePath: string

  constructor() {
    this.kernelModulePath = join(KERNEL_DIR, "orchestrator_integration.py")
  }

  private async runCommand(args: string[]): Promise<any> {
    const proc = Bun.spawn(["python3", "-m", "kernel.orchestrator_integration", ...args], {
      cwd: join(KERNEL_DIR, ".."),
      stdout: "pipe",
      stderr: "pipe",
    })

    let stdout = ""
    let stderr = ""

    for await (const chunk of proc.stdout) {
      stdout += new TextDecoder().decode(chunk)
    }
    for await (const chunk of proc.stderr) {
      stderr += new TextDecoder().decode(chunk)
    }

    const exitCode = await proc.exited

    if (exitCode === 0) {
      try {
        return JSON.parse(stdout.trim())
      } catch {
        return { success: true, output: stdout.trim() }
      }
    } else {
      throw new Error(`Kernel error: ${stderr}`)
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
    const result = await this.runCommand(["can_start_phase", phase])
    return result
  }

  async recordDelegation(phase: string, subAgent: string, taskId?: string): Promise<void> {
    await this.runCommand(["record_delegation", phase, subAgent, taskId || ""])
  }

  async recordPhaseCompletion(phase: string, artifacts: Array<{ kind: string; path: string; store: string; hash?: string }>): Promise<void> {
    await this.runCommand(["record_phase_completion", phase, JSON.stringify(artifacts)])
  }

  async checkScope(gitDiff: string, allowedFiles: string[]): Promise<{
    decision: string
    reason: string
    scope_violations: string[]
  }> {
    const result = await this.runCommand(["check_scope", JSON.stringify(gitDiff), JSON.stringify(allowedFiles)])
    return result
  }

  async getStatus(): Promise<Record<string, unknown>> {
    return this.runCommand(["status"])
  }
}
