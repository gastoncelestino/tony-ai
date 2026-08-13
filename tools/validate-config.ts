import { readFileSync, readdirSync, existsSync, statSync } from "node:fs"
import { resolve } from "node:path"

const ROOT = resolve(process.cwd())
const OPENCODE_JSON = resolve(ROOT, "opencode.json")
const PROMPTS_DIR = resolve(ROOT, "prompts/sdd")
const SHARED_DIR = resolve(ROOT, "skills/_shared")

let errors = 0
let warnings = 0

function fail(message: string): void {
  console.error(`\x1b[31m✗ ${message}\x1b[0m`)
  errors++
}

function ok(message: string): void {
  console.log(`\x1b[32m✓ ${message}\x1b[0m`)
}

function warn(message: string): void {
  console.warn(`\x1b[33m⚠ ${message}\x1b[0m`)
  warnings++
}

function checkJsonSyntax(): void {
  try {
    const content = readFileSync(OPENCODE_JSON, "utf-8")
    JSON.parse(content)
    ok("opencode.json: JSON syntax valid")
  } catch (error) {
    fail(`opencode.json: JSON syntax error — ${error}`)
  }
}

function extractFileReferences(
  text: string,
): Array<{ file: string; context: string }> {
  const regex = /\{file:([^}]+)\}/g
  const refs: Array<{ file: string; context: string }> = []
  let match

  while ((match = regex.exec(text)) !== null) {
    refs.push({
      file: match[1],
      context: text.slice(
        Math.max(0, match.index - 30),
        match.index + 50,
      ),
    })
  }

  return refs
}

function extractSharedReferences(
  text: string,
): Array<{ path: string; context: string }> {
  const regex = /(?:skills\/_shared|\.\.\/_shared)\/[^\s)`'"]+/g
  const refs: Array<{ path: string; context: string }> = []
  let match

  while ((match = regex.exec(text)) !== null) {
    refs.push({
      path: match[0],
      context: text.slice(
        Math.max(0, match.index - 30),
        match.index + 50,
      ),
    })
  }

  return refs
}

function extractAgentReferences(
  text: string,
): Array<{ agent: string; context: string }> {
  const regex =
    /agent\.([a-z][a-z0-9_-]*[a-z0-9])(?![a-z0-9_.-])/g

  const refs: Array<{ agent: string; context: string }> = []
  let match

  while ((match = regex.exec(text)) !== null) {
    if (match[1].includes("<") || match[1].includes(">")) continue

    refs.push({
      agent: match[1],
      context: text.slice(
        Math.max(0, match.index - 30),
        match.index + 50,
      ),
    })
  }

  return refs
}

function checkFileReferences(): void {
  let config: Record<string, unknown>

  try {
    const content = readFileSync(OPENCODE_JSON, "utf-8")
    config = JSON.parse(content)
  } catch {
    return
  }

  const allRefs: Array<{ file: string; context: string }> = []
  const agents = (config.agent ?? {}) as Record<
    string,
    { prompt?: string }
  >

  for (const [agentName, agentConfig] of Object.entries(agents)) {
    if (typeof agentConfig.prompt === "string") {
      const refs = extractFileReferences(agentConfig.prompt)

      for (const ref of refs) {
        allRefs.push({
          ...ref,
          context: `agent ${agentName}: ${ref.context}`,
        })
      }
    }
  }

  if (allRefs.length === 0) {
    ok("No {file:...} references found in prompts")
    return
  }

  const uniqueFiles = new Set(allRefs.map((r) => r.file))

  for (const file of uniqueFiles) {
    const fullPath = resolve(ROOT, file)

    if (existsSync(fullPath)) {
      ok(`{file:${file}} exists`)
    } else {
      fail(`{file:${file}} not found at ${fullPath}`)
    }
  }
}

function checkPromptSourceTokens(): void {
  const sourceRoot = resolve(ROOT, "prompts/agents")
  const pending: string[] = []

  const visit = (directory: string): void => {
    for (const entry of readdirSync(directory, {
      withFileTypes: true,
    })) {
      const file = resolve(directory, entry.name)

      if (entry.isDirectory()) {
        visit(file)
      } else if (entry.isFile() && entry.name.endsWith(".md")) {
        const content = readFileSync(file, "utf-8")

        if (content.match(/\{file:[^}]+\}/)) {
          pending.push(file)
        }
      }
    }
  }

  if (!existsSync(sourceRoot)) {
    fail("prompts/agents/ directory not found")
    return
  }

  visit(sourceRoot)

  if (pending.length > 0) {
    for (const file of pending) {
      fail(
        `${file}: native {file:...} token remains in source prompt; use plain documentation`,
      )
    }
  } else {
    ok("Prompt sources contain no native nested {file:...} references")
  }
}

function checkSharedReferences(): void {
  if (!existsSync(PROMPTS_DIR)) {
    fail("prompts/sdd/ directory not found")
    return
  }

  const entries = readdirSync(PROMPTS_DIR)
  const promptFiles = entries.filter(
    (file) => file.endsWith(".md") && !file.endsWith("SKILL.md"),
  )

  const allRefs: Array<{ path: string; context: string }> = []

  for (const file of promptFiles) {
    const content = readFileSync(
      resolve(PROMPTS_DIR, file),
      "utf-8",
    )

    const refs = extractSharedReferences(content)

    for (const ref of refs) {
      allRefs.push({
        ...ref,
        context: `${file}: ${ref.context}`,
      })
    }
  }

  if (allRefs.length === 0) {
    ok("No skills/_shared/ references found in prompts")
    return
  }

  const uniquePaths = new Set(allRefs.map((r) => r.path))

  for (const path of uniquePaths) {
    const fullPath = resolve(ROOT, path)

    if (existsSync(fullPath)) {
      ok(`${path} exists`)
    } else {
      fail(`${path} not found at ${fullPath}`)
    }
  }
}

function checkAgentReferences(): void {
  let config: Record<string, unknown>

  try {
    const content = readFileSync(OPENCODE_JSON, "utf-8")
    config = JSON.parse(content)
  } catch {
    return
  }

  const agents = Object.keys(
    (config.agent ?? {}) as Record<string, unknown>,
  )

  if (agents.length === 0) {
    warn("No agents defined in opencode.json")
    return
  }

  const allRefs: Array<{ agent: string; context: string }> = []
  const agentConfigs = (config.agent ?? {}) as Record<
    string,
    { prompt?: string }
  >

  for (const [agentName, agentConfig] of Object.entries(agentConfigs)) {
    if (typeof agentConfig.prompt === "string") {
      const refs = extractAgentReferences(agentConfig.prompt)

      for (const ref of refs) {
        allRefs.push({
          ...ref,
          context: `agent ${agentName}: ${ref.context}`,
        })
      }
    }
  }

  if (allRefs.length === 0) {
    ok("No agent.xxx references found in prompts")
    return
  }

  const seen = new Set<string>()
  const agentSet = new Set(agents)

  for (const ref of allRefs) {
    if (seen.has(ref.agent)) continue
    seen.add(ref.agent)

    if (ref.agent === "md") continue

    const isPrefix = agents.some(
      (agent) =>
        agent !== ref.agent &&
        agent.startsWith(ref.agent + "-"),
    )

    if (isPrefix) {
      continue
    }

    if (agentSet.has(ref.agent)) {
      ok(`agent.${ref.agent} exists in opencode.json`)
    } else {
      fail(
        `agent.${ref.agent} referenced in prompt but not found in opencode.json`,
      )
    }
  }
}

function checkDefaultAgent(): void {
  let config: Record<string, unknown>

  try {
    const content = readFileSync(OPENCODE_JSON, "utf-8")
    config = JSON.parse(content)
  } catch {
    return
  }

  const defaultAgent = (
    config as { default_agent?: string }
  ).default_agent

  if (!defaultAgent) {
    warn("No default_agent defined in opencode.json")
    return
  }

  const agents = Object.keys(
    (config.agent ?? {}) as Record<string, unknown>,
  )

  if (agents.includes(defaultAgent)) {
    ok(`default_agent "${defaultAgent}" exists in agents`)
  } else {
    fail(
      `default_agent "${defaultAgent}" not found in agents`,
    )
  }
}

function checkPermissions(): void {
  let config: Record<string, unknown>

  try {
    const content = readFileSync(OPENCODE_JSON, "utf-8")
    config = JSON.parse(content)
  } catch {
    return
  }

  if (!config.permission) {
    warn("No permission block defined in opencode.json")
    return
  }

  ok("permission block exists in opencode.json")

  const allowedTools = new Set([
    "bash",
    "edit",
    "read",
    "write",
    "task",
    "question",
  ])

  const agents = (config.agent ?? {}) as Record<
    string,
    {
      permission?: {
        task?: Record<string, string>
      }
    }
  >

  const agentNames = new Set(Object.keys(agents))

  for (const [agentName, agentConfig] of Object.entries(agents)) {
    if (
      agentConfig.permission?.task &&
      typeof agentConfig.permission.task === "object"
    ) {
      const taskPerms = agentConfig.permission.task

      for (const perm of Object.keys(taskPerms)) {
        if (perm === "*") continue

        if (agentNames.has(perm)) continue

        if (
          perm.startsWith("sdd-") ||
          perm.startsWith("review-") ||
          perm.startsWith("jd-") ||
          perm === "explore" ||
          perm === "general"
        ) {
          continue
        }

        if (!allowedTools.has(perm)) {
          warn(
            `agent.${agentName} has unusual task permission: ${perm}`,
          )
        }
      }
    }
  }
}

function checkMcpServers(): void {
  let config: Record<string, unknown>

  try {
    const content = readFileSync(OPENCODE_JSON, "utf-8")
    config = JSON.parse(content)
  } catch {
    return
  }

  if (!config.mcp) {
    warn("No MCP block defined in opencode.json")
    return
  }

  ok("MCP block exists in opencode.json")

  const mcp = config.mcp as Record<
    string,
    Record<string, unknown>
  >

  for (const [serverName, serverConfig] of Object.entries(mcp)) {
    if (!serverConfig.command && !serverConfig.url) {
      fail(
        `MCP server "${serverName}" missing command or url`,
      )
    }
  }
}

function checkSkillsDirectory(): void {
  if (!existsSync(resolve(ROOT, "skills"))) {
    fail("skills/ directory not found")
    return
  }

  ok("skills/ directory exists")

  if (!existsSync(SHARED_DIR)) {
    fail("skills/_shared/ directory not found")
    return
  }

  ok("skills/_shared/ directory exists")
}

function checkPromptsDirectory(): void {
  if (!existsSync(PROMPTS_DIR)) {
    fail("prompts/sdd/ directory not found")
    return
  }

  ok("prompts/sdd/ directory exists")

  const entries = readdirSync(PROMPTS_DIR)
  const promptFiles = entries.filter(
    (file) =>
      file.endsWith(".md") && !file.endsWith("SKILL.md"),
  )

  if (promptFiles.length === 0) {
    warn("No .md files found in prompts/sdd/")
    return
  }

  ok(`Found ${promptFiles.length} prompt files in prompts/sdd/`)
}

function checkScripts(): void {
  const scripts = [
    "scripts/setup.sh",
    "scripts/health.sh",
  ]

  for (const script of scripts) {
    const fullPath = resolve(ROOT, script)

    if (!existsSync(fullPath)) {
      fail(`${script} not found`)
    } else {
      const mode = statSync(fullPath).mode

      if ((mode & 0o111) === 0) {
        warn(`${script} exists but is not executable`)
      } else {
        ok(`${script} exists and executable`)
      }
    }
  }
}

function main(): void {
  console.log("\n=== Tony-AI Configuration Validator ===\n")

  checkJsonSyntax()
  checkSkillsDirectory()
  checkPromptsDirectory()
  checkScripts()
  checkDefaultAgent()
  checkPermissions()
  checkMcpServers()
  checkFileReferences()
  checkPromptSourceTokens()
  checkSharedReferences()
  checkAgentReferences()

  console.log("\n=== Summary ===")

  if (errors === 0) {
    if (warnings === 0) {
      console.log("\x1b[32m✓ All checks passed!\x1b[0m")
    } else {
      console.log(
        `\x1b[32m✓ All checks passed (${warnings} warning(s))\x1b[0m`,
      )
    }

    process.exit(0)
  } else {
    console.log(
      `\x1b[31m✗ ${errors} error(s) found\x1b[0m`,
    )

    if (warnings > 0) {
      console.log(
        `\x1b[33m⚠ ${warnings} warning(s) found\x1b[0m`,
      )
    }

    process.exit(1)
  }
}

main()