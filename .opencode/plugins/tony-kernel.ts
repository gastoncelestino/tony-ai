/**
 * Tony Kernel Plugin — OpenCode adapter.
 *
 * The plugin is intentionally kept thin: OpenCode events belong here;
 * Kernel policy and execution decisions belong in the Kernel.
 *
 * The legacy Python CLI/orchestrator bridge was removed while the new
 * Kernel execution boundary is being rebuilt. Until that boundary exists,
 * Task execution fails closed rather than falling back to legacy behavior.
 *
 * IMPORTANT: OpenCode's local-file plugin loader treats a module as
 * exporting "one or more plugin functions" — it scans EVERY top-level
 * export, not just `default`, and calls anything callable as if it were a
 * plugin entry point. A `class` is `typeof === "function"` in JS, so an
 * exported error class gets invoked without `new` and crashes the loader
 * ("Cannot call a class constructor ... without |new|"); an exported plain
 * helper function gets called with the wrong arguments instead. That's why
 * everything below except `export default` is intentionally NOT exported —
 * this file must expose exactly one callable: the plugin itself.
 */
import type { Plugin } from "@opencode-ai/plugin"

class KernelBlockedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelBlockedError"
  }
}
class KernelUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "KernelUnavailableError"
  }
}
interface ExecutionRequest {
  sessionID: string
  tool: string
  arguments: Record<string, unknown>
}
/**
 * Extract only the execution identity carried by the OpenCode Task event.
 * This is transport parsing, not Kernel policy.
 */
function executionRequest(
  input: { sessionID: string; tool: string },
  args: Record<string, unknown>
): ExecutionRequest {
  return {
    sessionID: input.sessionID,
    tool: input.tool,
    arguments: args,
  }
}
/**
 * Temporary fail-closed boundary.
 *
 * The next Kernel phase will replace this with the real Kernel authorization
 * call returning an ExecutionOrder. Keeping the boundary explicit prevents
 * the plugin from silently retaining the removed legacy orchestration path.
 */
async function authorizeExecution(input: ExecutionRequest): Promise<never> {
  if (input.tool !== "Task") {
    throw new KernelUnavailableError(
      "[Tony Kernel] Execution authorization is not implemented for this runtime boundary"
    )
  }
  throw new KernelUnavailableError(
    "[Tony Kernel] Task execution blocked: new Kernel execution boundary is not wired yet"
  )
}
async function taskExecuteBeforeHook(
  input: {
    tool: string
    sessionID: string
    callID: string
  },
  output: {
    args: Record<string, unknown>
  }
): Promise<void> {
  console.error("[TONY DEBUG] tool.execute.before", {
    tool: input.tool,
    sessionID: input.sessionID,
    callID: input.callID,
    args: output.args,
  })
  if (input.tool !== "Task") return
  await authorizeExecution(executionRequest(input, output.args))
}
/**
 * OpenCode 1.18.x requires the default export to be a FUNCTION that
 * receives the plugin context ({project, client, $, directory, worktree})
 * and RETURNS the hooks object.
 */
const TonyKernelPlugin: Plugin = async () => {
  console.log("[tony-kernel] Plugin loaded; execution boundary is fail-closed")

  return {
    "tool.execute.before": taskExecuteBeforeHook,
  }
}

export default TonyKernelPlugin
