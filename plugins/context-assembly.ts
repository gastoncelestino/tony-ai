import { readFile } from "node:fs/promises"
import { join } from "node:path"

type ToolOutput = { output: string; metadata?: Record<string, unknown> }
type CodeContext = {
  type: "project_code"
  path: string
  start_line: number
  end_line: number
  text: string
  lang: string
  score: number
}
type Documentation = { source_id: string; url: string; title: string; text: string }

type PendingContext = { documentation: Documentation[]; code: CodeContext[] }

const CONTEXT7_TOOLS = new Set(["context7_query_docs", "context7_get_library_docs"])
const CODE_INDEX_TOOL = "code-index_code_search"
export const MAX_CONTEXT_CHARS = 24_000

async function loadAllowedSources(worktree: string): Promise<Map<string, Documentation>> {
  const path = join(worktree, "config", "knowledge_sources.json")
  const data = JSON.parse(await readFile(path, "utf-8")) as { sources?: Record<string, unknown>[] }
  return new Map(
    (data.sources ?? [])
      .filter((s) => s.enabled === true && typeof s.id === "string" && typeof s.url === "string")
      .map((s) => [s.id as string, {
        source_id: s.id as string,
        url: s.url as string,
        title: typeof s.name === "string" ? s.name : s.id as string,
        text: "",
      }]),
  )
}

function validCode(value: unknown): value is CodeContext {
  if (!value || typeof value !== "object") return false
  const code = value as Record<string, unknown>
  return code.type === "project_code" && typeof code.path === "string" &&
    typeof code.start_line === "number" && typeof code.end_line === "number" &&
    typeof code.text === "string" && typeof code.lang === "string" &&
    typeof code.score === "number"
}

function dedupeDocumentation(items: Documentation[]): Documentation[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    const key = `${item.source_id}|${item.url}|${item.title}|${item.text}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function dedupeCode(items: CodeContext[]): CodeContext[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    const key = `${item.path}|${item.start_line}|${item.end_line}|${item.text}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function prioritizeCode(items: CodeContext[]): CodeContext[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => b.item.score - a.item.score || a.index - b.index)
    .map(({ item }) => item)
}

function fitContext(parts: string[], maxChars: number): string {
  const selected: string[] = []
  let size = 0
  for (const part of parts) {
    const separator = selected.length ? 2 : 0
    if (size + separator + part.length > maxChars) break
    selected.push(part)
    size += separator + part.length
  }
  return selected.join("\n\n")
}

function formatContext(context: PendingContext): string {
  const documentation = dedupeDocumentation(context.documentation)
  const codeContext = dedupeCode(prioritizeCode(context.code))
  const sourceCount = Number(documentation.length > 0) + Number(codeContext.length > 0)
  const sourceBudget = sourceCount > 1 ? Math.floor(MAX_CONTEXT_CHARS / 2) : MAX_CONTEXT_CHARS
  const sections: string[] = []

  if (documentation.length) {
    const docs = documentation.map((d) =>
      `### ${d.title}\nsource: ${d.source_id}\n${d.url}\n\n${d.text}`,
    )
    sections.push("## Authorized documentation\n\n" + fitContext(docs, sourceBudget))
  }
  if (codeContext.length) {
    const code = codeContext.map((c) =>
      `### ${c.path}:${c.start_line}-${c.end_line}\nsource: code-index\n\n${c.text}`,
    )
    sections.push("## Existing project code\n\n" + fitContext(code, sourceBudget))
  }
  return fitContext(sections, MAX_CONTEXT_CHARS)
}

export const ContextAssembly = ({ worktree }: { worktree: string }) => {
  const pending = new Map<string, PendingContext>()

  return {
    "tool.execute.after": async (input: { tool: string; sessionID?: string }, output: ToolOutput) => {
      const sessionID = input.sessionID
      if (!sessionID || !output?.metadata) return

      const current = pending.get(sessionID) ?? { documentation: [], code: [] }
      if (CONTEXT7_TOOLS.has(input.tool)) {
        const reference = output.metadata.reference
        const sources = await loadAllowedSources(worktree)
        if (reference && typeof reference === "object") {
          const ref = reference as Record<string, unknown>
          const allowed = typeof ref.source_id === "string" ? sources.get(ref.source_id) : undefined
          if (allowed && ref.url === allowed.url && typeof ref.text === "string") {
            current.documentation.push({ source_id: ref.source_id as string, url: ref.url as string, title: typeof ref.title === "string" ? ref.title : allowed.title, text: ref.text })
          }
        }
      }
      if (input.tool === CODE_INDEX_TOOL) {
        const code = output.metadata.project_code
        if (Array.isArray(code)) current.code.push(...code.filter(validCode))
      }
      if (current.documentation.length || current.code.length) pending.set(sessionID, current)
    },

    "experimental.chat.system.transform": async (input: { sessionID?: string }, output: { system: string[] }) => {
      const sessionID = input.sessionID
      if (!sessionID) return
      const context = pending.get(sessionID)
      if (!context) return
      const block = formatContext(context)
      if (!block) return
      if (output.system.length) output.system[output.system.length - 1] += "\n\n" + block
      else output.system.push(block)
      pending.delete(sessionID)
    },
  }
}

export default ContextAssembly
