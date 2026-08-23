type CodeIndexResult = {
  path?: unknown
  start_line?: unknown
  end_line?: unknown
  text?: unknown
  lang?: unknown
  score?: unknown
}

type ToolOutput = {
  output: string
  metadata?: Record<string, unknown>
}

const CODE_INDEX_SEARCH_TOOL = "code-index_code_search"

type CodeSearchHookInput = {
  tool: string
  sessionID?: string
}

type CodeSearchHookArgs = {
  args?: Record<string, unknown>
}

export type ProjectCodeContext = {
  type: "project_code"
  path: string
  start_line: number
  end_line: number
  text: string
  lang: string
  score: number
  query?: string
}

function isCodeIndexResult(value: unknown): value is CodeIndexResult {
  if (!value || typeof value !== "object") return false
  const result = value as CodeIndexResult
  return (
    typeof result.path === "string" &&
    typeof result.start_line === "number" &&
    typeof result.end_line === "number" &&
    typeof result.text === "string" &&
    typeof result.lang === "string" &&
    typeof result.score === "number"
  )
}

export function normalizeProjectCodeResults(output: string, query?: string): ProjectCodeContext[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(output)
  } catch {
    return []
  }

  if (!parsed || typeof parsed !== "object") return []
  const results = (parsed as { results?: unknown }).results
  if (!Array.isArray(results)) return []

  return results.filter(isCodeIndexResult).map((result) => ({
    type: "project_code" as const,
    path: result.path as string,
    start_line: result.start_line as number,
    end_line: result.end_line as number,
    text: result.text as string,
    lang: result.lang as string,
    score: result.score as number,
    ...(query ? { query } : {}),
  }))
}

export function addProjectCodeContext(output: ToolOutput, query?: string): void {
  const projectCode = normalizeProjectCodeResults(output.output, query)
  if (projectCode.length === 0) return

  output.metadata = {
    ...(output.metadata ?? {}),
    project_code: projectCode,
  }
}

export const ProjectCodeContext = () => {
  const pendingQueries = new Map<string, string[]>()

  return {
    "tool.execute.before": async (
      input: CodeSearchHookInput,
      output: CodeSearchHookArgs,
    ) => {
      if (input.tool !== CODE_INDEX_SEARCH_TOOL || !input.sessionID) return
      const query = output.args?.query
      if (typeof query !== "string" || query.length === 0) return
      const queries = pendingQueries.get(input.sessionID) ?? []
      queries.push(query)
      pendingQueries.set(input.sessionID, queries)
    },

    "tool.execute.after": async (
      input: CodeSearchHookInput,
      output: ToolOutput,
    ) => {
      if (input.tool !== CODE_INDEX_SEARCH_TOOL) return
      const query = input.sessionID ? pendingQueries.get(input.sessionID)?.shift() : undefined
      if (input.sessionID) {
        const queries = pendingQueries.get(input.sessionID)
        if (!queries?.length) pendingQueries.delete(input.sessionID)
      }
      addProjectCodeContext(output, query)
    },
  }
}
