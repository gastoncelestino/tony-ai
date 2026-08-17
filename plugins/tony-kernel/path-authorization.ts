/**
 * Normalize explicit path authorization inputs for OpenCode tool hooks.
 * Paths are passed to Kernel unchanged except for surrounding whitespace.
 */

export interface PathAuthorizationResult {
  allowed: boolean
  denied: string[]
}

export async function authorizeToolPaths(
  paths: string[],
  authorizePath: (path: string) => Promise<{ allowed: boolean; reason: string }>,
): Promise<PathAuthorizationResult> {
  const denied: string[] = []

  for (const path of paths) {
    const result = await authorizePath(path)
    if (!result.allowed) denied.push(path)
  }

  return { allowed: denied.length === 0, denied }
}
