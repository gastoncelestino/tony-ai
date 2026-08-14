import { appendFileSync, mkdirSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { createHash } from "node:crypto"

const enabled = () => process.env.TONY_CONTEXT_FLOW_TRACE === "1"
const tracePath = resolve(process.env.TONY_CONTEXT_FLOW_TRACE_FILE ?? ".context-flow/runtime.jsonl")

function json(value: unknown): string {
  try { return JSON.stringify(value) } catch { return JSON.stringify(String(value)) }
}

function text(value: unknown): string {
  if (typeof value === "string") return value
  if (value && typeof value === "object" && "output" in value && typeof (value as { output?: unknown }).output === "string") {
    return (value as { output: string }).output
  }
  return json(value)
}

function hash(value: unknown): string {
  return createHash("sha256").update(text(value), "utf8").digest("hex")
}

function record(event: string, payload: Record<string, unknown>): void {
  if (!enabled()) return
  mkdirSync(dirname(tracePath), { recursive: true })
  appendFileSync(tracePath, `${json({ ts: new Date().toISOString(), event, ...payload })}\n`, "utf8")
}

function interestingTool(tool: string): boolean {
  return tool === "Task" || /(?:mem_save|mem_search|mem_get_observation|mem_review)(?:$|[^a-zA-Z])/.test(tool)
}

const TonyContextFlowPlugin = {
  name: "tony-context-flow",
  version: "1.0.0",
  description: "Runtime trace for SDD phase delegation, TonyMem retrieval, and actual model token usage",
  hooks: {
    event: async ({ event }: { event: unknown }) => {
      if (!enabled()) return
      const value = event as { type?: string; properties?: Record<string, unknown> }
      if (value.type === "session.created" || value.type === "session.updated") {
        const info = value.properties?.info as Record<string, unknown> | undefined
        record(value.type, { session: info ?? value.properties ?? null })
        return
      }
      if (value.type === "message.updated") {
        const info = value.properties?.info as Record<string, unknown> | undefined
        if (info?.role === "assistant") {
          const tokens = info.tokens as Record<string, unknown> | undefined
          record("model.usage", {
            sessionID: info.sessionID,
            messageID: info.id,
            parentID: info.parentID,
            agent: info.agent,
            model: `${info.providerID ?? ""}/${info.modelID ?? ""}`,
            input_tokens: tokens?.input ?? null,
            output_tokens: tokens?.output ?? null,
            reasoning_tokens: tokens?.reasoning ?? null,
            cache_read_tokens: (tokens?.cache as Record<string, unknown> | undefined)?.read ?? null,
            cache_write_tokens: (tokens?.cache as Record<string, unknown> | undefined)?.write ?? null,
            finish: info.finish ?? null,
          })
        }
      }
      if (value.type === "message.part.updated") {
        const part = value.properties?.part as Record<string, unknown> | undefined
        if (part?.type === "subtask") {
          record("subtask.part", {
            sessionID: part.sessionID,
            messageID: part.messageID,
            agent: part.agent,
            prompt_bytes: Buffer.byteLength(String(part.prompt ?? ""), "utf8"),
            description_bytes: Buffer.byteLength(String(part.description ?? ""), "utf8"),
          })
        }
      }
    },
    "tool.execute.before": async (
      input: { tool: string; sessionID: string; callID: string },
      output: { args: unknown },
    ) => {
      if (!interestingTool(input.tool)) return
      const argsText = text(output.args)
      const args = output.args as Record<string, unknown> | undefined
      record("tool.before", {
        tool: input.tool,
        sessionID: input.sessionID,
        callID: input.callID,
        args_bytes: Buffer.byteLength(argsText, "utf8"),
        args_sha256: hash(output.args),
        phase: typeof args?.subagent_type === "string" ? args.subagent_type : null,
        topic_key: typeof args?.topic_key === "string" ? args.topic_key : null,
        query: typeof args?.query === "string" ? args.query : null,
      })
    },
    "tool.execute.after": async (
      input: { tool: string; sessionID: string; callID: string; args: unknown },
      output: unknown,
    ) => {
      if (!interestingTool(input.tool)) return
      const outputText = text(output)
      const args = input.args as Record<string, unknown> | undefined
      record("tool.after", {
        tool: input.tool,
        sessionID: input.sessionID,
        callID: input.callID,
        output_bytes: Buffer.byteLength(outputText, "utf8"),
        output_sha256: hash(output),
        phase: typeof args?.subagent_type === "string" ? args.subagent_type : null,
        topic_key: typeof args?.topic_key === "string" ? args.topic_key : null,
        query: typeof args?.query === "string" ? args.query : null,
      })
    },
  },
  async onLoad() {
    if (enabled()) console.log(`[tony-context-flow] tracing to ${tracePath}`)
  },
}

export default TonyContextFlowPlugin
