/**
 * Kernel Client — Communicates with Python Kernel via subprocess
 *
 * Spawns `python3 -m kernel.cli` from the repo root. Kernel state persists
 * across invocations via kernel/persistence.py, so this client sees the same
 * state machine as the MCP server.
 */

import { join } from "path"
import { fileURLToPath } from "url"
import { dirname } from "path"

const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(PLUGIN_DIR, "..", "..")

export interface CanStartPhaseResult {
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

export class KernelClient {
  private async runCommand(args: string[]): Promise<any> {
    const proc = Bun.spawn(["python3", "-m", "kernel.cli", ...args], {
      cwd: REPO_ROOT,
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
        throw new Error(`[tony-kernel] Non-JSON kernel output: ${stdout.trim()}`)
      }
    } else {
      throw new Error(`[tony-kernel] Kernel error (${exitCode}): ${stderr}`)
    }
  }

  async canStartPhase(phase: string): Promise<CanStartPhaseResult> {
    const result = await this.runCommand(["can_start_phase", phase])
    return {
      ...result,
      allowed: result.allowed === true,
    }
  }

  async recordDelegation(phase: string, subAgent: string, taskId?: string): Promise<void> {
    await this.runCommand(["record_delegation", phase, subAgent, taskId || ""])
  }

  async recordPhaseCompletion(phase: string, artifacts: Array<{ kind: string; path: string; store: string; hash?: string }>): Promise<void> {
    await this.runCommand(["record_phase_completion", phase, JSON.stringify(artifacts)])
  }

  async getStatus(): Promise<Record<string, unknown>> {
    return this.runCommand(["status"])
  }
}
