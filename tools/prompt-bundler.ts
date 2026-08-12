import { createHash } from "node:crypto"
import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs"
import { dirname, isAbsolute, relative, resolve } from "node:path"

export const ORCHESTRATOR_SOURCE = "prompts/agents/tony-orchestrator.md"
export const ORCHESTRATOR_BUNDLE = "prompts/generated/tony-orchestrator.md"
export const MANIFEST_SOURCE = "prompts/agents/includes/phase-manifest.json"
export const MANIFEST_OUTPUT = "prompts/generated/prompt-manifest.json"
export const PHASE_OUTPUT_DIR = "prompts/generated/phases"

const INCLUDE_RE = /\{\{include:(.*?)\}\}/g
const NATIVE_FILE_RE = /\{file:[^}]+\}/g
const MAX_INCLUDE_DEPTH = 32

type ManifestEntry = {
  path: string
  sha256: string
}

type PhaseConfig = {
  includes?: string[]
  skills?: string[]
}

type PhaseManifest = {
  version: string
  base_includes?: string[]
  phases?: Record<string, PhaseConfig>
  review_phases?: Record<string, PhaseConfig>
}

export type BuildResult = {
  path: string
  content: string
  dependencies: ManifestEntry[]
}

export type PromptManifest = {
  schema_version: 1
  generated_by: "tools/prompt-bundler.ts"
  source: string
  bundle: string
  bundle_sha256: string
  dependencies: ManifestEntry[]
  files: Record<string, { relative: string; size: number; sha256: string }>
  phases: Record<string, { path: string; sha256: string; dependencies: ManifestEntry[] }>
}

export class PromptBundleError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "PromptBundleError"
  }
}

function sha256(content: string): string {
  return createHash("sha256").update(content, "utf8").digest("hex")
}

function repoPath(root: string, file: string): string {
  return relative(root, file).split("\\").join("/")
}

function isWithin(root: string, candidate: string): boolean {
  const rel = relative(root, candidate)
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel))
}

function resolveWithin(root: string, parentFile: string, requested: string): string {
  const clean = requested.trim()
  if (!clean || clean.includes("{")) {
    throw new PromptBundleError(
      `invalid include path "${requested}" referenced from ${repoPath(root, parentFile)}: dynamic paths are not allowed`,
    )
  }

  const candidate = resolve(dirname(parentFile), clean)
  if (!isWithin(root, candidate)) {
    throw new PromptBundleError(
      `include path escapes repository root: ${requested} from ${repoPath(root, parentFile)}`,
    )
  }
  if (!statSafe(candidate)?.isFile()) {
    throw new PromptBundleError(
      `include not found: ${requested} from ${repoPath(root, parentFile)} (resolved to ${repoPath(root, candidate)})`,
    )
  }
  return candidate
}

function statSafe(file: string) {
  try {
    return statSync(file)
  } catch {
    return undefined
  }
}

function readUtf8(root: string, file: string): string {
  try {
    return readFileSync(file, "utf8")
  } catch (error) {
    throw new PromptBundleError(`cannot read ${repoPath(root, file)}: ${String(error)}`)
  }
}

function addDependency(root: string, file: string, dependencies: Map<string, ManifestEntry>): void {
  const path = repoPath(root, file)
  dependencies.set(path, { path, sha256: sha256(readUtf8(root, file)) })
}

function expandFile(
  root: string,
  file: string,
  dependencies: Map<string, ManifestEntry>,
  stack: string[],
  seen: Set<string>,
): string {
  const normalized = resolve(file)
  if (stack.includes(normalized)) {
    const cycle = [...stack, normalized].map((item) => repoPath(root, item)).join(" -> ")
    throw new PromptBundleError(`include cycle detected: ${cycle}`)
  }
  if (stack.length >= MAX_INCLUDE_DEPTH) {
    throw new PromptBundleError(
      `include depth exceeds ${MAX_INCLUDE_DEPTH}: ${[...stack, normalized]
        .map((item) => repoPath(root, item))
        .join(" -> ")}`,
    )
  }

  addDependency(root, normalized, dependencies)
  const source = readUtf8(root, normalized)
  const nextStack = [...stack, normalized]
  let cursor = 0
  let output = ""
  for (const match of source.matchAll(INCLUDE_RE)) {
    const token = match[0]
    const requested = match[1]
    const index = match.index ?? 0
    output += source.slice(cursor, index)
    const child = resolveWithin(root, normalized, requested)
    if (nextStack.includes(child)) {
      output += expandFile(root, child, dependencies, nextStack, seen)
    } else if (seen.has(child)) {
      output += `<!-- include deduplicated: ${repoPath(root, child)} -->`
    } else {
      seen.add(child)
      output += expandFile(root, child, dependencies, nextStack, seen)
    }
    cursor = index + token.length
  }
  output += source.slice(cursor)
  return output
}

function assertNoRuntimeTokens(root: string, content: string, label: string): void {
  const native = content.match(NATIVE_FILE_RE) ?? []
  const dynamic = content.match(INCLUDE_RE) ?? []
  if (native.length || dynamic.length) {
    throw new PromptBundleError(
      `${label} contains unresolved prompt tokens: ${[...native, ...dynamic].join(", ")}`,
    )
  }
  if (content.includes("{include_1") || content.includes("{phase_name}")) {
    throw new PromptBundleError(`${label} contains unresolved dynamic placeholders`)
  }
}

function loadManifest(root: string): PhaseManifest {
  const file = resolve(root, MANIFEST_SOURCE)
  if (!statSafe(file)?.isFile()) throw new PromptBundleError(`phase manifest not found: ${MANIFEST_SOURCE}`)
  try {
    return JSON.parse(readUtf8(root, file)) as PhaseManifest
  } catch (error) {
    throw new PromptBundleError(`invalid phase manifest ${MANIFEST_SOURCE}: ${String(error)}`)
  }
}

function getPhaseConfig(manifest: PhaseManifest, phase: string): PhaseConfig {
  const config = manifest.phases?.[phase] ?? manifest.review_phases?.[phase]
  if (!config) throw new PromptBundleError(`phase "${phase}" is not present in ${MANIFEST_SOURCE}`)
  return config
}

function expandReferencedFile(
  root: string,
  file: string,
  dependencies: Map<string, ManifestEntry>,
): string {
  const seen = new Set<string>([resolve(file)])
  return expandFile(root, file, dependencies, [], seen)
}

export function buildOrchestrator(root: string): BuildResult {
  const source = resolve(root, ORCHESTRATOR_SOURCE)
  const dependencies = new Map<string, ManifestEntry>()
  const content = expandReferencedFile(root, source, dependencies).trimEnd() + "\n"
  assertNoRuntimeTokens(root, content, ORCHESTRATOR_SOURCE)
  return { path: ORCHESTRATOR_BUNDLE, content, dependencies: [...dependencies.values()] }
}

export function buildPhase(root: string, phase: string): BuildResult {
  const manifest = loadManifest(root)
  const config = getPhaseConfig(manifest, phase)
  const dependencies = new Map<string, ManifestEntry>()
  const includes = [...(manifest.base_includes ?? []), ...(config.includes ?? [])]
  const uniqueIncludes = [...new Set(includes)]
  const uniqueSkills = [...new Set(config.skills ?? [])]
  const sections: string[] = [`# Tony AI — Materialized prompt: ${phase}`, ""]

  for (const name of uniqueIncludes) {
    const file = resolveWithin(root, resolve(root, "prompts/agents/includes/phase-manifest.json"), name)
    sections.push(expandReferencedFile(root, file, dependencies).trimEnd())
  }

  if (uniqueSkills.length) {
    sections.push("## Skills to load before work", "")
    for (const name of uniqueSkills) {
      const skill = resolveWithin(root, resolve(root, "skills/_shared/phase-manifest.json"), name)
      sections.push(expandReferencedFile(root, skill, dependencies).trimEnd())
    }
  }

  const sddPhaseFile = resolve(root, "prompts/sdd", `${phase}.md`)
  const externalPhaseFile = resolve(root, "prompts/agents/phase-prompts", `${phase}.md`)
  const phaseFile = statSafe(sddPhaseFile)?.isFile() ? sddPhaseFile : externalPhaseFile
  if (!statSafe(phaseFile)?.isFile()) {
    throw new PromptBundleError(
      `phase prompt not found: expected ${repoPath(root, sddPhaseFile)} or ${repoPath(root, externalPhaseFile)}`,
    )
  }
  sections.push("## Phase-specific instructions", expandReferencedFile(root, phaseFile, dependencies).trimEnd())
  const content = sections.join("\n\n").trimEnd() + "\n"
  assertNoRuntimeTokens(root, content, `phase ${phase}`)
  return { path: `${PHASE_OUTPUT_DIR}/${phase}.md`, content, dependencies: [...dependencies.values()] }
}

function allPhases(manifest: PhaseManifest): string[] {
  return [...new Set([...Object.keys(manifest.phases ?? {}), ...Object.keys(manifest.review_phases ?? {})])].sort()
}

export function buildAll(root: string): { orchestrator: BuildResult; phases: BuildResult[]; manifest: PromptManifest } {
  const manifest = loadManifest(root)
  const orchestrator = buildOrchestrator(root)
  const phases = allPhases(manifest).map((phase) => buildPhase(root, phase))
  // NOTE: intentionally no absolute filesystem `path` field here. This manifest is
  // committed to the repo and compared byte-for-byte by checkGenerated()/`make
  // check-prompts`. An absolute path is machine-specific (checkout dir differs
  // between a dev's clone, Docker, and CI), so embedding one makes the manifest
  // impossible to reproduce anywhere except the exact machine that generated it.
  const files: Record<string, { relative: string; size: number; sha256: string }> = {}

  // Add orchestrator
  files[repoPath(root, resolve(root, ORCHESTRATOR_BUNDLE))] = {
    relative: repoPath(root, resolve(root, ORCHESTRATOR_BUNDLE)),
    size: Buffer.byteLength(orchestrator.content, "utf8"),
    sha256: sha256(orchestrator.content),
  }

  for (const phase of phases) {
    const absPath = resolve(root, phase.path)
    files[repoPath(root, absPath)] = {
      relative: repoPath(root, absPath),
      size: Buffer.byteLength(phase.content, "utf8"),
      sha256: sha256(phase.content),
    }
  }
  
  const promptManifest: PromptManifest = {
    schema_version: 1,
    generated_by: "tools/prompt-bundler.ts",
    source: ORCHESTRATOR_SOURCE,
    bundle: ORCHESTRATOR_BUNDLE,
    bundle_sha256: sha256(orchestrator.content),
    dependencies: orchestrator.dependencies,
    files,
    phases: Object.fromEntries(
      phases.map((item) => [
        item.path.replace(`${PHASE_OUTPUT_DIR}/`, "").replace(/\.md$/, ""),
        { path: item.path, sha256: sha256(item.content), dependencies: item.dependencies },
      ]),
    ),
  }
  return { orchestrator, phases, manifest: promptManifest }
}

function writeResult(root: string, result: BuildResult): void {
  const target = resolve(root, result.path)
  mkdirSync(dirname(target), { recursive: true })
  writeFileSync(target, result.content, "utf8")
}

export function writeAll(root: string): PromptManifest {
  const built = buildAll(root)
  writeResult(root, built.orchestrator)
  for (const phase of built.phases) writeResult(root, phase)
  const manifestPath = resolve(root, MANIFEST_OUTPUT)
  mkdirSync(dirname(manifestPath), { recursive: true })
  writeFileSync(manifestPath, JSON.stringify(built.manifest, null, 2) + "\n", "utf8")
  return built.manifest
}

function sameFile(root: string, path: string, expected: string): boolean {
  const file = resolve(root, path)
  return statSafe(file)?.isFile() === true && readUtf8(root, file) === expected
}

export function checkGenerated(root: string): string[] {
  const built = buildAll(root)
  const errors: string[] = []
  if (!sameFile(root, built.orchestrator.path, built.orchestrator.content)) {
    errors.push(`${built.orchestrator.path} is missing or stale; run bun run tools/build-prompts.ts`)
  }
  for (const phase of built.phases) {
    if (!sameFile(root, phase.path, phase.content)) {
      errors.push(`${phase.path} is missing or stale; run bun run tools/build-prompts.ts`)
    }
  }
  const manifestText = JSON.stringify(built.manifest, null, 2) + "\n"
  if (!sameFile(root, MANIFEST_OUTPUT, manifestText)) {
    errors.push(`${MANIFEST_OUTPUT} is missing or stale; run bun run tools/build-prompts.ts`)
  }
  return errors
}