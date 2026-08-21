/**
 * Tony Kernel capability bridge.
 *
 * OpenCode remains the runtime, but the Kernel is authoritative for which
 * tools may execute while an SDD phase is active. This hook asks the Kernel
 * before every tool execution and fails closed on denial.
 */

import type { Plugin } from "@opencode-ai/plugin"
import { spawn } from "node:child_process"
import { join } from "path"
import { fileURLToPath } from "url"
import { dirname } from "path"

const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(PLUGIN_DIR, "..")

interface ToolDecision {
  allowed: boolean
  reason: string
  phase: string
  tool: string
}

function checkWithKernel(tool: string): Promise<ToolDecision> {
  return new Promise((resolve, reject) => {
    const proc = spawn("python3", ["-m", "kernel.tool_policy", tool], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        TONY_RUNTIME_DIR: process.env.TONY_RUNTIME_DIR || REPO_ROOT,
        TONY_REPO_ROOT: REPO_ROOT,
      },
      stdio: ["ignore", "pipe", "pipe"],
    })

    let stdout = ""
    let stderr = ""

    proc.stdout.on("data", (data: Buffer) => { stdout += data.toString() })
    proc.stderr.on("data", (data: Buffer) => { stderr += data.toString() })

    proc.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`Kernel capability check failed (${code}): ${stderr}`))
        return
      }

      try {
        resolve(JSON.parse(stdout.trim()) as ToolDecision)
      } catch {
        reject(new Error(`Kernel capability check returned invalid JSON: ${stdout}`))
      }
    })

    proc.on("error", reject)
  })
}

export async function kernelToolCapabilityBeforeHook(
  input: { sessionID: string; tool: string; arguments: Record<string, unknown> },
  _output: unknown,
): Promise<void> {
  // Task delegation has its own transition gate in plugins/tony-kernel.ts.
  // All other tools, including Kernel control-plane tools, are checked by
  // the authoritative Kernel policy. This prevents phase agents from using
  // reset/transition operations to bypass the state machine.
  if (input.tool === "Task") return

  const decision = await checkWithKernel(input.tool)
  if (!decision.allowed) {
    throw new Error(
      `[Tony Kernel] Tool execution blocked during phase '${decision.phase}': ${decision.reason}`,
    )
  }
}

const plugin: Plugin = {
  name: "tony-kernel-capabilities",
  version: "1.1.0",
  description: "Tony Kernel phase capability enforcement",
  hooks: {
    "tool.execute.before": kernelToolCapabilityBeforeHook,
  },
}

export default plugin
