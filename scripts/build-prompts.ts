import { readFileSync, writeFileSync, existsSync, statSync, mkdirSync } from "node:fs"
import { resolve, dirname, basename } from "node:path"

const ROOT = resolve(dirname(new URL(import.meta.url).pathname), "..")

export interface ResolveOptions {
  root: string
  onInclude?: (filePath: string) => void
}

export interface ResolveResult {
  content: string
  manifest: PromptManifest
  pendingTokens: string[]
}

export interface PromptManifest {
  generatedAt: string
  root: string
  files: Record<string, FileEntry>
}

export interface FileEntry {
  path: string
  relative: string
  size: number
  sha256: string
}

function createIncludeRegex(): RegExp {
  return /\{file:([^}]+)\}/g
}

function isPlaceholder(path: string): boolean {
  return path.includes("{") || path.includes("}")
}

function sha256Of(text: string): string {
  const crypto = require("crypto")
  return crypto.createHash("sha256").update(text, "utf8").digest("hex")
}

export function resolvePrompt(filePath: string, options: ResolveOptions): ResolveResult {
  const root = resolve(options.root)
  const resolved = resolve(filePath)

  if (!resolved.startsWith(root)) {
    throw new Error(`Path traversal detected: ${resolved} is outside root ${root}`)
  }

  const files: Record<string, FileEntry> = {}
  const pendingTokens: string[] = []

  function readFile(filePath: string): string {
    if (!existsSync(filePath)) {
      throw new Error(`Include not found: ${filePath}`)
    }
    const content = readFileSync(filePath, "utf-8")
    const stat = statSync(filePath)
    const relative = resolve(filePath).replace(root + "/", "")
    files[resolve(filePath)] = {
      path: resolve(filePath),
      relative,
      size: stat.size,
      sha256: sha256Of(content),
    }
    if (options.onInclude) {
      options.onInclude(filePath)
    }
    return content
  }

  function expand(content: string, currentFile: string, stack: string[]): string {
    let result = content
    const replacements: Array<{ match: string; replacement: string }> = []
    const includeRe = createIncludeRegex()

    let match
    while ((match = includeRe.exec(result)) !== null) {
      const rawPath = match[1].trim()

      if (isPlaceholder(rawPath)) {
        continue
      }

      const absolute = resolve(dirname(currentFile), rawPath)
      const normalized = resolve(absolute)

      if (stack.includes(normalized)) {
        const cycle = [...stack, normalized].map((f) => basename(f)).join(" → ")
        throw new Error(`Include cycle detected: ${cycle}`)
      }

      if (!normalized.startsWith(root)) {
        throw new Error(`Path traversal detected: ${normalized} is outside root ${root}`)
      }

      if (!existsSync(normalized)) {
        throw new Error(`Include not found: ${normalized} (referenced from ${currentFile})`)
      }

      replacements.push({
        match: match[0],
        replacement: expand(readFile(normalized), normalized, [...stack, normalized]),
      })
    }

    for (const rep of replacements) {
      result = result.replace(rep.match, rep.replacement)
    }

    return result
  }

  const content = readFile(resolved)
  const expanded = expand(content, resolved, [resolved])

  const pendingRe = createIncludeRegex()
  let remaining
  while ((remaining = pendingRe.exec(expanded)) !== null) {
    pendingTokens.push(remaining[0])
  }

  const manifest: PromptManifest = {
    generatedAt: new Date().toISOString(),
    root,
    files,
  }

  return { content: expanded, manifest, pendingTokens }
}

export function writeBundle(outputPath: string, result: ResolveResult): void {
  const outDir = resolve(outputPath, "..")
  if (!existsSync(outDir)) {
    mkdirSync(outDir, { recursive: true })
  }
  writeFileSync(outputPath, result.content, "utf-8")
  const manifestPath = outputPath + ".manifest.json"
  writeFileSync(manifestPath, JSON.stringify(result.manifest, null, 2), "utf-8")
}

function checkBundles(root: string): boolean {
  const manifestPath = resolve(root, "prompt-manifest.json")
  if (!existsSync(manifestPath)) {
    console.error("✗ prompt-manifest.json not found")
    return false
  }

  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"))
  const expectedHashes: Record<string, string> = {}

  for (const [relPath, entry] of Object.entries(manifest.files)) {
    expectedHashes[relPath] = (entry as { sha256: string }).sha256
  }

  for (const [relPath, expectedHash] of Object.entries(expectedHashes)) {
    const absPath = resolve(root, relPath)
    if (!existsSync(absPath)) {
      console.error(`✗ Missing file: ${relPath}`)
      return false
    }
    const content = readFileSync(absPath, "utf-8")
    const crypto = require("crypto")
    const actualHash = crypto.createHash("sha256").update(content, "utf8").digest("hex")
    if (actualHash !== expectedHash) {
      console.error(`✗ Drift detected: ${relPath}`)
      return false
    }
  }

  return true
}

const args = process.argv.slice(2)
if (args.includes("--check")) {
  if (checkBundles(ROOT)) {
    console.log("✓ Prompt bundles are up to date")
    process.exit(0)
  } else {
    console.error("✗ Prompt bundles are out of date. Run: make build-prompts")
    process.exit(1)
  }
}

if (args.includes("--build") || args.length === 0) {
  const manifestPath = resolve(ROOT, "prompts/agents/includes/phase-manifest.json")
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"))
  const includesDir = resolve(ROOT, "prompts/agents/includes")
  const skillsDir = resolve(ROOT, "skills/_shared")
  const sddDir = resolve(ROOT, "prompts/sdd")
  const outDir = resolve(ROOT, "prompts/generated")
  const phasesDir = resolve(outDir, "phases")

  mkdirSync(phasesDir, { recursive: true })

  const allFiles: Record<string, FileEntry> = {}

  function registerFile(absPath: string): string {
    const content = readFileSync(absPath, "utf-8")
    const stat = statSync(absPath)
    const rel = resolve(absPath).replace(ROOT + "/", "")
    const hash = sha256Of(content)
    allFiles[rel] = {
      path: resolve(absPath),
      relative: rel,
      size: stat.size,
      sha256: hash,
    }
    return content
  }

  function resolveInclude(name: string): string {
    const candidates = [
      resolve(includesDir, name),
      resolve(skillsDir, name),
    ]
    for (const candidate of candidates) {
      if (existsSync(candidate)) {
        return registerFile(candidate)
      }
    }
    if (!name.endsWith(".md")) {
      return resolveInclude(name + ".md")
    }
    throw new Error(`Include not found: ${name}`)
  }

  function buildPhaseBundle(phase: string, config: { includes: string[]; skills: string[] }): string {
    const parts: string[] = []

    for (const inc of config.includes) {
      parts.push(resolveInclude(inc))
    }

    if (config.skills.length > 0) {
      parts.push("\n## Skills to load before work\n")
      for (const skill of config.skills) {
        parts.push(resolveInclude(skill))
      }
    }

    const phaseFile = resolve(sddDir, phase + ".md")
    if (existsSync(phaseFile)) {
      parts.push("\n## Phase-Specific Instructions\n")
      parts.push(registerFile(phaseFile))
    }

    return parts.join("\n\n")
  }

  const phases = [
    ...Object.entries(manifest.phases || {}),
    ...Object.entries(manifest.review_phases || {}),
  ]

  for (const [phase, config] of phases) {
    const content = buildPhaseBundle(phase, config as { includes: string[]; skills: string[] })
    const bundlePath = resolve(phasesDir, `${phase}.md`)
    writeFileSync(bundlePath, content, "utf-8")
    const stat = statSync(bundlePath)
    allFiles[resolve(bundlePath).replace(ROOT + "/", "")] = {
      path: resolve(bundlePath),
      relative: resolve(bundlePath).replace(ROOT + "/", ""),
      size: stat.size,
      sha256: sha256Of(content),
    }
  }

  const promptManifest: PromptManifest = {
    generatedAt: new Date().toISOString(),
    root: ROOT,
    files: allFiles,
  }
  writeFileSync(resolve(outDir, "prompt-manifest.json"), JSON.stringify(promptManifest, null, 2) + "\n", "utf-8")
  console.log(`✓ Built ${phases.length} phase bundles`)
}
