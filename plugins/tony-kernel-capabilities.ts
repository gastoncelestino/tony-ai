import type { Plugin } from "@opencode-ai/plugin"
import { spawn } from "node:child_process"
import { join, dirname } from "path"
import { fileURLToPath } from "url"

const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(PLUGIN_DIR, "..")

interface ToolDecision {
  allowed: boolean
  reason: string
  phase: string
  tool: string
}

const FSM_PHASE_AGENTS = new Set([
  "sdd-explore",
  "sdd-propose",
  "sdd-spec",
  "sdd-design",
  "sdd-tasks",
  "sdd-apply",
  "sdd-verify",
  "sdd-archive",
])

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

    proc.stdout.on("data", (data: Buffer) => {
      stdout += data.toString()
    })
    proc.stderr.on("data", (data: Buffer) => {
      stderr += data.toString()
    })

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
  // Task delegation has a separate FSM transition gate in plugins/tony-kernel.ts.
  // This hook additionally prevents a phase executor from creating arbitrary
  // nested agents. Only configured SDD phase agents may be delegated.
  if (input.tool === "Task") {
    const subAgent = input.arguments.subagent_type
    if (typeof subAgent !== "string" || !FSM_PHASE_AGENTS.has(subAgent)) {
      throw new Error(
        `[Tony Kernel] Nested Task delegation blocked: '${String(subAgent ?? "unknown")}' is not an authorized SDD phase agent`,
      )
    }

    // The main Tony Kernel plugin performs the authoritative phase gate.
    return
  }

  const decision = await checkWithKernel(input.tool)
  if (!decision.allowed) {
    throw new Error(
      `[Tony Kernel] Tool execution blocked during phase '${decision.phase}': ${decision.reason}`,
    )
  }
}

export const TonyKernelCapabilities: Plugin = async () => ({
  "tool.execute.before": kernelToolCapabilityBeforeHook,
})

export default TonyKernelCapabilities
