import { spawn } from "node:child_process"
import { decodeKernelBoundaryResponse, decodeKernelContextResponse, encodeKernelBoundaryRequest, encodeKernelContextRequest, type KernelBoundaryRequest, type KernelBoundaryResponse, type KernelContextRequest, type KernelContextResponse } from "./protocol"

export type KernelTransportOptions = { command?: string; args?: string[]; timeoutMs?: number; cwd?: string }

export async function callKernelBoundary(request: KernelBoundaryRequest, options: KernelTransportOptions = {}): Promise<KernelBoundaryResponse> {
  return callKernelProcess(encodeKernelBoundaryRequest(request), options, decodeKernelBoundaryResponse, "Kernel boundary")
}

export async function getKernelContext(request: KernelContextRequest, options: KernelTransportOptions = {}): Promise<KernelContextResponse> {
  return callKernelProcess(encodeKernelContextRequest(request), options, decodeKernelContextResponse, "Kernel context")
}

async function callKernelProcess<T>(payload: string, options: KernelTransportOptions, decode: (payload: string) => T, label: string): Promise<T> {
  const command = options.command ?? process.env.TONYMEM_PYTHON ?? "python3"
  const args = options.args ?? ["-m", "kernel.boundary"]
  const timeoutMs = options.timeoutMs ?? 5000
  return new Promise((resolve) => {
    let settled = false
    let stdout = ""
    let stderr = ""
    const child = spawn(command, args, { cwd: options.cwd, stdio: ["pipe", "pipe", "pipe"] })
    const finish = (response: T) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(response)
    }
    const timer = setTimeout(() => { child.kill(); finish(blocked(`${label} transport timed out`)) }, timeoutMs)
    child.stdout.setEncoding("utf8")
    child.stderr.setEncoding("utf8")
    child.stdout.on("data", (chunk: string) => { stdout += chunk })
    child.stderr.on("data", (chunk: string) => { stderr += chunk })
    child.on("error", (error) => finish(blocked(`${label} process unavailable: ${error.message}`)))
    child.on("close", (code) => {
      if (settled) return
      if (code !== 0) return finish(blocked(`${label} process failed${stderr.trim() ? `: ${stderr.trim()}` : ""}`))
      try { finish(decode(stdout.trim())) }
      catch { finish(blocked(`Invalid ${label} response`)) }
    })
    child.stdin.end(payload)
  })
}

function blocked(reason: string): KernelBoundaryResponse & KernelContextResponse {
  return { allowed: false, decision: "blocked", reason, execution_order: null, available: false }
}
