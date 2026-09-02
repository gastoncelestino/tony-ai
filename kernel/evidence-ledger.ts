export type EvidenceKind =
  | "FILE_DISCOVERED"
  | "FILE_CONTENT_READ"
  | "SEARCH_RESULT"
  | "COMMAND_RESULT"
  | "FILE_MODIFIED"
  | "TOOL_ERROR"

export type Evidence = {
  id: string
  kind: EvidenceKind
  sessionId: string
  callId: string
  tool: string
  createdAt: string
  target?: string
  summary: string
  output?: string
  metadata?: Record<string, unknown>
}

export type EvidenceLedger = {
  record: (input: Omit<Evidence, "id" | "createdAt"> & { id?: string; createdAt?: string }) => Evidence
  get: (id: string) => Evidence | undefined
  getByCallId: (callId: string) => Evidence[]
  list: () => Evidence[]
  hasKindForCall: (callId: string, kind: EvidenceKind) => boolean
}

const MAX_OUTPUT = 12000

function trimOutput(output: string | undefined) {
  if (!output) return undefined
  if (output.length <= MAX_OUTPUT) return output
  return `${output.slice(0, MAX_OUTPUT)}\n[truncated]`
}

export function createEvidenceLedger(now: () => string = () => new Date().toISOString()): EvidenceLedger {
  const entries = new Map<string, Evidence>()
  const byCallId = new Map<string, string[]>()
  let sequence = 0

  const record = (input: Omit<Evidence, "id" | "createdAt"> & { id?: string; createdAt?: string }) => {
    const id = input.id ?? `evidence:${++sequence}`
    const evidence: Evidence = {
      ...input,
      id,
      createdAt: input.createdAt ?? now(),
      output: trimOutput(input.output),
    }
    entries.set(id, evidence)
    const callEntries = byCallId.get(evidence.callId) ?? []
    callEntries.push(id)
    byCallId.set(evidence.callId, callEntries)
    return evidence
  }

  const get = (id: string) => entries.get(id)
  const getByCallId = (callId: string) => (byCallId.get(callId) ?? []).map((id) => entries.get(id)!).filter(Boolean)
  const list = () => [...entries.values()]
  const hasKindForCall = (callId: string, kind: EvidenceKind) => getByCallId(callId).some((entry) => entry.kind === kind)

  return { record, get, getByCallId, list, hasKindForCall }
}

export type ToolEvidenceInput = {
  sessionId: string
  callId: string
  tool: string
  args: unknown
  output: string
  metadata: unknown
  failed: boolean
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined
}

function targetFromArgs(args: Record<string, unknown> | undefined) {
  const candidates = ["path", "file", "filepath", "filePath", "pattern", "query", "command"]
  for (const key of candidates) {
    if (typeof args?.[key] === "string" && args[key]) return args[key] as string
  }
  return undefined
}

function globMatches(output: string) {
  if (output === "No files found") return []
  return output
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

export function recordToolEvidence(ledger: EvidenceLedger, input: ToolEvidenceInput): Evidence[] {
  const tool = input.tool.toLowerCase()
  const args = record(input.args)
  const metadata = record(input.metadata)
  const target = targetFromArgs(args)
  const details = metadata ?? (args ? { input: args } : undefined)

  if (input.failed) {
    return [ledger.record({
      sessionId: input.sessionId,
      callId: input.callId,
      tool: input.tool,
      kind: "TOOL_ERROR",
      target,
      summary: `Tool '${input.tool}' returned an error`,
      output: input.output,
      metadata: details,
    })]
  }

  if (tool === "glob") {
    const matches = globMatches(input.output)
    if (matches.length === 0) {
      return [ledger.record({
        sessionId: input.sessionId,
        callId: input.callId,
        tool: input.tool,
        kind: "SEARCH_RESULT",
        target,
        summary: "File discovery returned no matches",
        output: input.output,
        metadata: details,
      })]
    }

    return matches.map((match) => ledger.record({
      sessionId: input.sessionId,
      callId: input.callId,
      tool: input.tool,
      kind: "FILE_DISCOVERED",
      target: match,
      summary: "File discovery returned a matching path",
      output: input.output,
      metadata: details,
    }))
  }

  if (tool === "read") {
    return [ledger.record({
      sessionId: input.sessionId,
      callId: input.callId,
      tool: input.tool,
      kind: "FILE_CONTENT_READ",
      target,
      summary: "File content was returned by the read tool",
      output: input.output,
      metadata: details,
    })]
  }

  if (tool === "grep" || tool === "list") {
    return [ledger.record({
      sessionId: input.sessionId,
      callId: input.callId,
      tool: input.tool,
      kind: "SEARCH_RESULT",
      target,
      summary: `Search/list operation completed with tool '${input.tool}'`,
      output: input.output,
      metadata: details,
    })]
  }

  if (tool === "bash") {
    return [ledger.record({
      sessionId: input.sessionId,
      callId: input.callId,
      tool: input.tool,
      kind: "COMMAND_RESULT",
      target,
      summary: "Command execution returned a result",
      output: input.output,
      metadata: details,
    })]
  }

  if (tool === "write" || tool === "edit" || tool === "apply_patch") {
    return [ledger.record({
      sessionId: input.sessionId,
      callId: input.callId,
      tool: input.tool,
      kind: "FILE_MODIFIED",
      target,
      summary: `File modification completed with tool '${input.tool}'`,
      output: input.output,
      metadata: details,
    })]
  }

  return []
}
