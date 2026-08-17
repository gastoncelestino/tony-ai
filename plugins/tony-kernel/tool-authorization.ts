/**
 * Normalize the authorization inputs exposed by OpenCode tool hooks.
 *
 * This adapter is intentionally conservative. It extracts only command/path
 * values that are explicit in a tool invocation; it does not infer paths from
 * arbitrary payloads and does not perform authorization itself.
 */

export interface ToolAuthorizationRequest {
  tool: string
  command: string | null
  paths: string[]
}

function readString(value: unknown): string | null {
  if (typeof value !== "string") return null
  const normalized = value.trim()
  return normalized.length > 0 ? normalized : null
}

function readPaths(arguments_: Record<string, unknown>): string[] {
  const paths = new Set<string>()
  for (const key of ["filePath", "path"]) {
    const value = readString(arguments_[key])
    if (value) paths.add(value)
  }
  const values = arguments_.paths
  if (Array.isArray(values)) {
    for (const value of values) {
      const path = readString(value)
      if (path) paths.add(path)
    }
  }
  return [...paths]
}

export function extractToolAuthorizationRequest(
  tool: string,
  arguments_: Record<string, unknown>,
): ToolAuthorizationRequest {
  return {
    tool,
    command: readString(arguments_.command),
    paths: readPaths(arguments_),
  }
}
