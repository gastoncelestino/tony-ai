import { spawn } from "node:child_process"
import { decodeKernelBoundaryResponse, encodeKernelBoundaryRequest, type KernelBoundaryRequest, type KernelBoundaryResponse } from "./protocol"

export type KernelTransportOptions = { command?: string; args?: string[]; timeoutMs?: number; cwd?: string }

export async function callKernelBoundary(request: KernelBoundaryRequest, options: KernelTransportOptions = {}): Promise<KernelBoundaryResponse> {
  const command = options.command ?? process.env.TONYMEM_PYTHON ?? "python3"
  const args = options.args ?? ["-m", "kernel.boundary"]
  const timeoutMs = options.timeoutMs ?? 5000
  return new Promise((resolve) => {
    let settled = false
    let stdout = ""
    let stderr = ""
    const child = spawn(command, args, { cwd: options.cwd, stdio: ["pipe", "pipe", "pipe"] })
    const finish = (response: KernelBoundaryResponse) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(response)
    }
    const timer = setTimeout(() => { child.kill(); finish(blocked("Kernel boundary transport timed out")) }, timeoutMs)
    child.stdout.setEncoding("utf8")
    child.stderr.setEncoding("utf8")
    child.stdout.on("data", (chunk: string) => { stdout += chunk })
    child.stderr.on("data", (chunk: string) => { stderr += chunk })
    child.on("error", (error) => finish(blocked(`Kernel boundary process unavailable: ${error.message}`)))
    child.on("close", (code) => {
      if (settled) return
      if (code !== 0) return finish(blocked(`Kernel boundary process failed${stderr.trim() ? `: ${stderr.trim()}` : ""}`))
      try { finish(decodeKernelBoundaryResponse(stdout.trim())) }
      catch { finish(blocked("Invalid Kernel boundary response")) }
    })
    child.stdin.end(encodeKernelBoundaryRequest(request))
  })
}

function blocked(reason: string): KernelBoundaryResponse { return { allowed: false, decision: "blocked", reason, execution_order: null } }
