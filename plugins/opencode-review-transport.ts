import type { Plugin } from "@opencode-ai/plugin"
import { spawn } from "node:child_process"

const DEBUG_LOG_PATH = process.platform === "win32" ? "NUL" : "/dev/null"
function debugLog(message: string, details?: Record<string, unknown>) {
  try {
    const suffix = details ? ` ${JSON.stringify(details)}` : ""
    require("node:fs").appendFileSync(DEBUG_LOG_PATH, `[${new Date().toISOString()}] [REVIEW_TRANSPORT] ${message}${suffix}\n`, "utf8")
  } catch {}
}

const REVIEW_AGENTS = new Set(["review-risk", "review-resilience", "review-readability", "review-reliability", "review-refuter", "review-validator"])
const TRANSPORT = {
  Command: "gentle-ai",
  Schema: "gentle-ai.provider-transport/v1",
  Start: "start",
  Prompt: "prompt",
  Complete: "complete",
  Result: "result",
} as const

interface TransportFrame {
  schema: string
  operation: string
  nonce?: string
  prompt?: string
  output?: string
  error?: string
}

interface Relay {
  prompt: Promise<{ nonce: string; prompt: string }>
  complete: (output: unknown) => Promise<string>
  close: () => void
}

interface RelayRegistration {
  owner: symbol
  relay: Relay
  completing: boolean
}

const RELAY_REGISTRY_KEY = "__gentleAiOpenCodeReviewTransportRelays" as const

function reviewRelayRegistry(): Map<string, RelayRegistration> {
  const runtime = globalThis as typeof globalThis & { [RELAY_REGISTRY_KEY]?: Map<string, RelayRegistration> }
  if (runtime[RELAY_REGISTRY_KEY] === undefined) runtime[RELAY_REGISTRY_KEY] = new Map<string, RelayRegistration>()
  return runtime[RELAY_REGISTRY_KEY]
}

function taskKey(sessionID: string, callID: string): string {
  return `${sessionID}:${callID}`
}

const RELAY_REFUSED_CODE = "opencode_review_transport_relay_refused"

function relayRefusedReason(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause)
}

function relayRefusedPrompt(reason: string): string {
  return (
    `${RELAY_REFUSED_CODE}: the Go review relay refused this Task before launch: ${reason}\n` +
    `You have no review binding and no frozen candidate evidence. Do not inspect anything, ` +
    `do not fabricate findings, and do not return a review result. ` +
    `Reply with exactly: ${RELAY_REFUSED_CODE}`
  )
}

function relayRefusedOutput(reason: string): string {
  return `${RELAY_REFUSED_CODE}: ${reason}`
}

function decodeTransportFrame(line: string): TransportFrame {
  const frame = JSON.parse(line) as unknown
  if (!frame || typeof frame !== "object" || Array.isArray(frame)) throw new Error("invalid Go transport response")
  return frame as TransportFrame
}

function startRelay(cwd: string, prompt: string): Relay {
  debugLog("starting Go review relay", { cwd, promptLength: prompt.length })
  const child = spawn(TRANSPORT.Command, ["review", "opencode-transport"], { cwd, stdio: ["pipe", "pipe", "pipe"] })
  let buffered = ""
  let closed = false
  const stderr: Buffer[] = []
  let resolvePrompt: (value: { nonce: string; prompt: string }) => void
  let rejectPrompt: (reason: unknown) => void
  let resolveResult: (value: string) => void
  let rejectResult: (reason: unknown) => void
  const promptFrame = new Promise<{ nonce: string; prompt: string }>((resolve, reject) => { resolvePrompt = resolve; rejectPrompt = reject })
  const resultFrame = new Promise<string>((resolve, reject) => { resolveResult = resolve; rejectResult = reject })
  void promptFrame.catch(() => {})
  void resultFrame.catch(() => {})
  const fail = (cause: unknown) => {
    if (closed) return
    closed = true
    debugLog("relay failed", { error: String(cause) })
    rejectPrompt(cause)
    rejectResult(cause)
  }
  child.stdout.on("data", (chunk: Buffer) => {
    buffered += chunk.toString("utf8")
    for (;;) {
      const newline = buffered.indexOf("\n")
      if (newline < 0) return
      const line = buffered.slice(0, newline)
      buffered = buffered.slice(newline + 1)
      try {
        const frame = decodeTransportFrame(line)
        debugLog("relay frame received", { operation: frame.operation, hasNonce: !!frame.nonce, outputLength: frame.output?.length ?? 0 })
        if (frame.schema !== TRANSPORT.Schema) throw new Error("invalid Go transport schema")
        if (frame.operation === TRANSPORT.Prompt && typeof frame.nonce === "string" && frame.nonce !== "" && typeof frame.prompt === "string" && frame.prompt !== "") {
          resolvePrompt({ nonce: frame.nonce, prompt: frame.prompt })
          continue
        }
        if (frame.operation === TRANSPORT.Result && typeof frame.output === "string" && frame.output !== "") {
          closed = true
          resolveResult(frame.output)
          continue
        }
        throw new Error("invalid Go relay frame")
      } catch (cause) {
        fail(cause)
      }
    }
  })
  child.stdin.on("error", fail)
  child.on("error", fail)
  child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk))
  child.on("close", (code) => {
    debugLog("relay process closed", { code })
    if (!closed) fail(new Error(Buffer.concat(stderr).toString("utf8").trim() || `Go review relay exited before completion (${code ?? "signal"})`))
  })
  child.stdin.write(JSON.stringify({ schema: TRANSPORT.Schema, operation: TRANSPORT.Start, prompt }) + "\n", (cause) => {
    if (cause) fail(cause)
  })
  return {
    prompt: promptFrame,
    complete: async (output: unknown) => {
      const materialized = await promptFrame
      debugLog("completing relay", { nonce: materialized.nonce, outputType: typeof output, outputLength: typeof output === "string" ? output.length : undefined })
      const completion: TransportFrame = { schema: TRANSPORT.Schema, operation: TRANSPORT.Complete, nonce: materialized.nonce }
      if (typeof output === "string") completion.output = output
      else completion.error = "opencode_task_host_output_unavailable"
      child.stdin.end(JSON.stringify(completion) + "\n")
      return resultFrame
    },
    close: () => {
      debugLog("closing relay")
      if (!closed) closed = true
      if (!child.killed) child.kill()
    },
  }
}

const OpenCodeReviewTransportPlugin: Plugin = async ({ directory, worktree }) => {
  const owner = Symbol("gentle-ai-opencode-review-transport")
  const relays = reviewRelayRegistry()
  const deferred = new Map<string, RelayRegistration>()
  const refused = new Map<string, string>()
  const cwd = () => worktree || directory
  debugLog("plugin initialized", { directory, worktree, registrySize: relays.size })
  const clearOwned = (key: string) => {
    const registration = relays.get(key)
    if (!registration || registration.owner !== owner) return
    debugLog("clearing owned relay", { key })
    relays.delete(key)
    registration.relay.close()
  }
  const clearSession = (prefix: string) => {
    for (const [key, registration] of relays) {
      if (!key.startsWith(prefix) || registration.owner !== owner) continue
      debugLog("clearing relay for deleted session", { key })
      relays.delete(key)
      registration.relay.close()
    }
    for (const key of deferred.keys()) if (key.startsWith(prefix)) deferred.delete(key)
    for (const key of refused.keys()) if (key.startsWith(prefix)) refused.delete(key)
  }
  return {
    dispose: async () => {
      debugLog("plugin dispose", { ownedRelays: [...relays.values()].filter((r) => r.owner === owner).length })
      deferred.clear()
      refused.clear()
      for (const [key, registration] of relays) if (registration.owner === owner) clearOwned(key)
    },
    event: async ({ event }) => {
      if (event.type !== "session.deleted") return
      debugLog("session.deleted", { sessionID: event.properties.info.id })
      const prefix = `${event.properties.info.id}:`
      clearSession(prefix)
    },
    "tool.execute.before": async (input, output) => {
      if (input.tool !== "task" || typeof output.args?.subagent_type !== "string" || !REVIEW_AGENTS.has(output.args.subagent_type)) return
      if (typeof output.args.prompt !== "string") throw new Error("review task prompt is unavailable for Go relay materialization")
      const key = taskKey(input.sessionID, input.callID)
      debugLog("review Task before", { sessionID: input.sessionID, callID: input.callID, subagent: output.args.subagent_type, key })
      const existing = relays.get(key)
      if (existing) {
        if (existing.owner !== owner) deferred.set(key, existing)
        debugLog("existing relay found", { key, ownedByThisInstance: existing.owner === owner })
        return
      }
      const relay = startRelay(cwd(), output.args.prompt)
      relays.set(key, { owner, relay, completing: false })
      try {
        output.args.prompt = (await relay.prompt).prompt
        debugLog("review prompt materialized", { key, promptLength: output.args.prompt.length })
      } catch (cause) {
        clearOwned(key)
        const reason = relayRefusedReason(cause)
        refused.set(key, reason)
        output.args.prompt = relayRefusedPrompt(reason)
        debugLog("review relay refused", { key, reason })
        throw cause
      }
    },
    "tool.execute.after": async (input, output) => {
      if (input.tool !== "task" || typeof input.args?.subagent_type !== "string" || !REVIEW_AGENTS.has(input.args.subagent_type)) return
      const key = taskKey(input.sessionID, input.callID)
      debugLog("review Task after", { sessionID: input.sessionID, callID: input.callID, subagent: input.args.subagent_type, key, outputLength: typeof output.output === "string" ? output.output.length : undefined })
      const refusal = refused.get(key)
      if (refusal !== undefined) {
        refused.delete(key)
        output.output = relayRefusedOutput(refusal)
        throw new Error(relayRefusedOutput(refusal))
      }
      const deferredTo = deferred.get(key)
      if (deferredTo !== undefined) {
        deferred.delete(key)
        if (relays.get(key) === deferredTo || deferredTo.completing) return
      }
      const registration = relays.get(key)
      if (!registration) throw new Error("review Task relay completion has no matching live before hook")
      if (registration.owner !== owner) throw new Error("review Task relay completion is owned by another plugin instance")
      if (registration.completing) throw new Error("review Task relay completion is already in flight for this task")
      registration.completing = true
      try {
        output.output = await registration.relay.complete(output.output)
        debugLog("review relay result materialized", { key, outputLength: typeof output.output === "string" ? output.output.length : undefined })
      } finally {
        if (relays.get(key) === registration) relays.delete(key)
        registration.relay.close()
      }
    },
  }
}

export default OpenCodeReviewTransportPlugin