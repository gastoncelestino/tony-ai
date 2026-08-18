import { readFile } from "node:fs/promises"
import { join } from "node:path"

type Source = {
  library_id?: unknown
  enabled?: unknown
}

type ToolArgs = Record<string, unknown>

const CONTEXT7_DOC_TOOLS = new Set([
  "context7_query_docs",
  "context7_get_library_docs",
])

async function loadAllowedLibraryIds(worktree: string): Promise<Set<string>> {
  const path = join(worktree, "config", "knowledge_sources.json")
  const data = JSON.parse(await readFile(path, "utf-8")) as { sources?: Source[] }
  return new Set(
    (data.sources ?? [])
      .filter((source) => source.enabled === true && typeof source.library_id === "string")
      .map((source) => source.library_id as string),
  )
}

export function isAllowedLibraryId(libraryId: unknown, allowed: Set<string>): boolean {
  return typeof libraryId === "string" && allowed.has(libraryId)
}

export const Context7Allowlist = async ({ worktree }: { worktree: string }) => ({
  "tool.execute.before": async (
    input: { tool: string },
    output: { args: ToolArgs },
  ) => {
    if (!CONTEXT7_DOC_TOOLS.has(input.tool)) return

    const libraryId =
      output.args.libraryId ?? output.args.context7CompatibleLibraryID
    const allowed = await loadAllowedLibraryIds(worktree)

    if (!isAllowedLibraryId(libraryId, allowed)) {
      throw new Error(
        `[Context7] Documentation source is not authorized: ${String(libraryId)}`,
      )
    }
  },
})
