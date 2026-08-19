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

export type ProjectCodeContext = {
  type: "project_code"
  path: string
  start_line: number
  end_line: number
  text: string
  lang: string
  score: number
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

export function normalizeProjectCodeResults(output: string): ProjectCodeContext[] {
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
  }))
}

export function addProjectCodeContext(output: ToolOutput): void {
  const projectCode = normalizeProjectCodeResults(output.output)
  if (projectCode.length === 0) return

  output.metadata = {
    ...(output.metadata ?? {}),
    project_code: projectCode,
  }
}

export const ProjectCodeContext = () => ({
  "tool.execute.after": async (
    input: { tool: string },
    output: ToolOutput,
  ) => {
    if (input.tool !== CODE_INDEX_SEARCH_TOOL) return
    addProjectCodeContext(output)
  },
})
