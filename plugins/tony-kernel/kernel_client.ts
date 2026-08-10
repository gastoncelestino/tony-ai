/**
 * Kernel Client — Communicates with Python Kernel via subprocess
 */

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
    // Path to the kernel orchestrator module
    this.kernelModulePath = "/workspace/7cf8dcfc-72e2-49b9-9795-75440ba1be96/sessions/agent_0a609c26-9e31-4ad3-abf7-5af14c9f5367/kernel/orchestrator_integration.py"
  }

  private async runCommand(args: string[]): Promise<any> {
    return new Promise((resolve, reject) => {
      const proc = Bun.spawn(["python3", "-m", "kernel.orchestrator_integration", ...args], {
        cwd: "/workspace/7cf8dcfc-72e2-49b9-9795-75440ba1be96/sessions/agent_0a609c26-9e31-4ad3-abf7-5af14c9f5367",
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
          resolve(JSON.parse(stdout.trim()))
        } catch {
          resolve({ success: true, output: stdout.trim() })
        }
      } else {
        reject(new Error(`Kernel error: ${stderr}`))
      }
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

  private async runCommand(args: string[]): Promise<any> {
    const proc = Bun.spawn(["python3", "-m", "kernel.orchestrator_integration", ...args], {
      cwd: "/workspace/7cf8dcfc-72e2-49b9-9795-75440ba1be96/sessions/agent_0a609c26-9e31-4ad3-abf7-5af14c9f5367",
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
}