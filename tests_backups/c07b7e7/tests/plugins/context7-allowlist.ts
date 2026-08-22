import { readFile } from "node:fs/promises"
import { join } from "node:path"

type Source = {
  id?: unknown
  name?: unknown
  library_id?: unknown
  url?: unknown
  enabled?: unknown
}

type ToolArgs = Record<string, unknown>
type ToolOutput = {
  output: string
  metadata?: Record<string, unknown>
}

const CONTEXT7_RESOLVE_TOOL = "context7_resolve_library_id"
const CONTEXT7_DOC_TOOLS = new Set([
  "context7_query_docs",
  "context7_get_library_docs",
])

async function loadAllowedSources(worktree: string): Promise<Map<string, Source>> {
  const path = join(worktree, "config", "knowledge_sources.json")
  const data = JSON.parse(await readFile(path, "utf-8")) as { sources?: Source[] }
  return new Map(
    (data.sources ?? [])
      .filter(
        (source) =>
          source.enabled === true &&
          typeof source.library_id === "string" &&
          typeof source.id === "string",
      )
      .map((source) => [source.library_id as string, source]),
  )
}

export function isAllowedLibraryId(libraryId: unknown, allowed: Set<string>): boolean {
  return typeof libraryId === "string" && allowed.has(libraryId)
}

export function addDocumentationProvenance(
  libraryId: unknown,
  output: ToolOutput,
  sources: Map<string, Source>,
): void {
  if (typeof libraryId !== "string") return
  const source = sources.get(libraryId)
  if (!source || typeof source.id !== "string" || typeof source.url !== "string") return

  output.metadata = {
    ...(output.metadata ?? {}),
    reference: {
      source_id: source.id,
      url: source.url,
      title: typeof source.name === "string" ? source.name : source.id,
      text: output.output,
    },
  }
}

export const Context7Allowlist = async ({ worktree }: { worktree: string }) => ({
  "tool.execute.before": async (
    input: { tool: string },
    output: { args: ToolArgs },
  ) => {
    if (input.tool === CONTEXT7_RESOLVE_TOOL) {
      throw new Error(
        "[Context7] Library resolution is disabled; use an explicitly authorized library_id from config/knowledge_sources.json",
      )
    }

    if (!CONTEXT7_DOC_TOOLS.has(input.tool)) return

    const libraryId =
      output.args.libraryId ?? output.args.context7CompatibleLibraryID
    const sources = await loadAllowedSources(worktree)

    if (!isAllowedLibraryId(libraryId, new Set(sources.keys()))) {
      throw new Error(
        `[Context7] Documentation source is not authorized: ${String(libraryId)}`,
      )
    }
  },
  "tool.execute.after": async (
    input: { tool: string; args: ToolArgs },
    output: ToolOutput,
  ) => {
    if (!CONTEXT7_DOC_TOOLS.has(input.tool)) return

    const libraryId = input.args.libraryId ?? input.args.context7CompatibleLibraryID
    const sources = await loadAllowedSources(worktree)
    addDocumentationProvenance(libraryId, output, sources)
  },
})
