import type { KernelContext, KernelContextRequest, KernelContextResponse } from "./protocol"

export type KernelContextProviderResult =
  | { kind: "available"; context: KernelContext }
  | { kind: "unavailable"; reason: string }

export type KernelContextTransport = (request: KernelContextRequest) => Promise<KernelContextResponse>

export function createKernelContextProvider(getContext: KernelContextTransport) {
  return {
    async getContext(input: { projectDirectory: string; sessionID: string; tool: string }): Promise<KernelContextProviderResult> {
      if (input.tool.toLowerCase() !== "task") {
        return { kind: "unavailable", reason: "Kernel context requested for non-Task tool" }
      }
      try {
        const response = await getContext({
          operation: "get_context",
          project_directory: input.projectDirectory,
          session_id: input.sessionID,
        })
        if (!response.available) return { kind: "unavailable", reason: response.reason }
        return { kind: "available", context: response.context }
      } catch (error) {
        const reason = error instanceof Error ? error.message : String(error)
        return { kind: "unavailable", reason: `Kernel context provider unavailable: ${reason}` }
      }
    },
  }
}
