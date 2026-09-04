import { appendFileSync } from "node:fs"

const TRACE_PATH = "/home/tony/tony-ai/tony-opencode-trace.jsonl"

export function tonyTrace(event: string, data: Record<string, string | number | boolean | null | undefined> = {}) {
  if (globalThis.process?.env?.TONY_TRACE !== "1") return
  try {
    appendFileSync(
      TRACE_PATH,
      JSON.stringify({ ts: Date.now(), event, ...data }) + "\n",
      { encoding: "utf8" },
    )
  } catch {
    // Tracing must never affect OpenCode execution.
  }
}
