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
}
type Documentation = { source_id: string; url: string; title: string; text: string }

type PendingContext = { documentation: Documentation[]; code: CodeContext[] }

const CONTEXT7_TOOLS = new Set(["context7_query_docs", "context7_get_library_docs"])
const CODE_INDEX_TOOL = "code-index_code_search"

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
    typeof code.text === "string" && typeof code.lang === "string"
}

function formatContext(context: PendingContext): string {
  const sections: string[] = []
  if (context.documentation.length) {
    sections.push("## Authorized documentation\n\n" + context.documentation.map((d) =>
      `### ${d.title}\n${d.url}\n\n${d.text}`,
    ).join("\n\n"))
  }
  if (context.code.length) {
    sections.push("## Existing project code\n\n" + context.code.map((c) =>
      `### ${c.path}:${c.start_line}-${c.end_line}\n\n${c.text}`,
    ).join("\n\n"))
  }
  return sections.join("\n\n")
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
