import type { Plugin } from "@opencode-ai/plugin"
import { appendFileSync } from "node:fs"
import { join } from "node:path"

const GLOBAL_KEY = Symbol.for("tony-ai.observability")

type ObservabilityState = {
  logPaths: Set<string>
  installed: boolean
}

function state(): ObservabilityState {
  const root = globalThis as typeof globalThis & { [GLOBAL_KEY]?: ObservabilityState }
  if (!root[GLOBAL_KEY]) root[GLOBAL_KEY] = { logPaths: new Set<string>(), installed: false }
  return root[GLOBAL_KEY]!
}

function serialize(value: unknown, seen = new WeakSet<object>()): unknown {
  if (value instanceof Error) {
    return {
      name: value.name,
      message: value.message,
      stack: value.stack,
      ...("cause" in value ? { cause: serialize((value as Error & { cause?: unknown }).cause, seen) } : {}),
    }
  }
  if (value && typeof value === "object") {
    if (seen.has(value)) return "[Circular]"
    seen.add(value)
    if (Array.isArray(value)) return value.map((item) => serialize(item, seen))
    const output: Record<string, unknown> = {}
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      try { output[key] = serialize(item, seen) } catch { output[key] = "[Unserializable]" }
    }
    return output
  }
  if (typeof value === "bigint") return value.toString()
  if (typeof value === "function") return `[Function ${value.name || "anonymous"}]`
  return value
}

function write(paths: Set<string>, event: string, details: Record<string, unknown> = {}) {
  const record = JSON.stringify({ ts: new Date().toISOString(), event, ...details }) + "\n"
  for (const path of paths) {
    try { appendFileSync(path, record, "utf8") }
    catch (error) { console.error("[TONY OBSERVABILITY] write failed", error) }
  }
}

function installProcessHooks(observability: ObservabilityState) {
  if (observability.installed) return
  observability.installed = true

  process.on("warning", (warning) => {
    write(observability.logPaths, "PROCESS_WARNING", {
      warning: serialize(warning),
      warningName: warning.name,
      warningMessage: warning.message,
      warningStack: warning.stack,
    })
  })

  const onUnhandledRejection = (reason: unknown, promise: Promise<unknown>) => {
    write(observability.logPaths, "UNHANDLED_REJECTION", {
      reason: serialize(reason),
      promise: serialize(promise),
    })

    // Observability must not turn an unhandled rejection into a swallowed error.
    // Remove this listener so the normal uncaught-exception path remains fatal.
    process.removeListener("unhandledRejection", onUnhandledRejection)
    queueMicrotask(() => { throw reason instanceof Error ? reason : new Error(String(reason)) })
  }
  process.on("unhandledRejection", onUnhandledRejection)

  const onUncaughtException = (error: Error, origin: NodeJS.UncaughtExceptionOrigin) => {
    write(observability.logPaths, "UNCAUGHT_EXCEPTION", {
      origin,
      error: serialize(error),
    })

    // Keep Node's fatal semantics. The trace is synchronous, so it is flushed
    // before the process exits.
    process.exitCode = 1
    process.exit(1)
  }
  process.on("uncaughtException", onUncaughtException)
}

export const TonyObservability: Plugin = async ({ directory }) => {
  const observability = state()
  const logPath = join(directory, "tony-observability.jsonl")
  observability.logPaths.add(logPath)
  installProcessHooks(observability)

  write(observability.logPaths, "OBSERVABILITY_START", {
    directory,
    pid: process.pid,
    node: process.version,
  })

  return {
    event: async ({ event }) => {
      const properties: any = (event as any).properties ?? {}
      const sessionID = typeof properties.sessionID === "string"
        ? properties.sessionID
        : typeof properties.info?.id === "string"
          ? properties.info.id
          : undefined

      if (event.type === "session.error") {
        write(observability.logPaths, "SESSION_ERROR", {
          sessionID,
          error: serialize(properties.error),
        })
        return
      }

      if (event.type === "session.status") {
        write(observability.logPaths, "SESSION_STATUS", {
          sessionID,
          status: properties.status,
        })
        return
      }

      if (event.type === "session.idle") {
        write(observability.logPaths, "SESSION_IDLE", { sessionID })
        return
      }

      if (event.type === "session.created") {
        write(observability.logPaths, "SESSION_CREATED", {
          sessionID,
          parentID: properties.info?.parentID,
        })
        return
      }

      if (event.type === "session.deleted") {
        write(observability.logPaths, "SESSION_DELETED", { sessionID })
        return
      }

      if (event.type === "message.updated") {
        const info = properties.info ?? {}
        write(observability.logPaths, "MESSAGE_UPDATED", {
          sessionID: info.sessionID,
          messageID: info.id,
          role: info.role,
          agent: info.agent,
          providerID: info.providerID,
          modelID: info.modelID,
          finish: info.finish,
          hasError: !!info.error,
          error: info.error ? serialize(info.error) : undefined,
        })
        return
      }

      if (event.type === "message.part.updated") {
        const part = properties.part ?? {}
        if (part.type === "tool" || part.type === "step-finish") {
          write(observability.logPaths, "MESSAGE_PART_UPDATED", {
            sessionID: part.sessionID,
            messageID: part.messageID,
            partID: part.id,
            partType: part.type,
            callID: part.callID,
            tool: part.tool,
            status: part.state?.status,
            reason: part.reason,
          })
        }
      }
    },
  }
}

export default TonyObservability
