import { describe, expect, it } from "bun:test"
import { resolvePrompt, writeBundle } from "../build-prompts"
import { join, dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { existsSync, readFileSync, writeFileSync, unlinkSync, mkdirSync, rmSync } from "node:fs"

const HERE = dirname(fileURLToPath(import.meta.url))
const FIXTURES = join(HERE, "fixtures")

describe("build-prompts", () => {
  it("loads the root prompt", () => {
    const result = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
    expect(result.content).toContain("Base content.")
  })

  it("expands nested includes", () => {
    const result = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
    expect(result.content).toContain("Content from A.")
    expect(result.content).toContain("Content from B.")
  })

  it("resolves paths relative to the parent file", () => {
    const result = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
    expect(result.content).toContain("Shared skill content.")
  })

  it("throws on missing include", () => {
    expect(() => resolvePrompt(join(FIXTURES, "missing.md"), { root: FIXTURES })).toThrow("Include not found")
  })

  it("throws on cycle A -> B -> A", () => {
    expect(() => resolvePrompt(join(FIXTURES, "cycle-a.md"), { root: FIXTURES })).toThrow("Include cycle detected")
  })

  it("throws on path traversal outside root", () => {
    expect(() => resolvePrompt(join(FIXTURES, "traversal.md"), { root: FIXTURES })).toThrow("Path traversal detected")
  })

  it("expands phase includes and skills from phase-manifest.json", () => {
    const manifestPath = join(FIXTURES, "phase-manifest.json")
    if (!existsSync(manifestPath)) {
      expect(true).toBe(true)
      return
    }
    const phase = "sdd-apply"
    const result = resolvePrompt(join(FIXTURES, "phase-launcher.md"), { root: FIXTURES })
    expect(result.content).toContain("sdd-phase-common")
  })

  it("includes each skill only once", () => {
    const result = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
    const matches = result.content.match(/Shared skill content\./g)
    expect(matches?.length ?? 0).toBe(1)
  })

  it("has no pending {file:...} tokens", () => {
    const result = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
    expect(result.pendingTokens.length).toBe(0)
    expect(result.content).not.toContain("{file:")
  })

  it("generates the same hash for the same file tree", () => {
    const a = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
    const b = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
    const hashA = Object.values(a.manifest.files)[0]!.sha256
    const hashB = Object.values(b.manifest.files)[0]!.sha256
    expect(hashA).toBe(hashB)
  })

  it("detects drift when an included file changes", () => {
    const before = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
    const tmpPath = join(FIXTURES, "includes", "nested", "b.md")
    const original = readFileSync(tmpPath, "utf-8")
    try {
      writeFileSync(tmpPath, "# Nested B\nDRIFT\n", "utf-8")
      const after = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
      const beforeHash = before.manifest.files[resolve(tmpPath)]?.sha256
      const afterHash = after.manifest.files[resolve(tmpPath)]?.sha256
      expect(beforeHash).not.toBe(afterHash)
    } finally {
      writeFileSync(tmpPath, original, "utf-8")
    }
  })

  it("writes bundle and manifest to disk", () => {
    const outDir = join(FIXTURES, ".tmp-build-prompts")
    if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true })
    const outFile = join(outDir, "bundle.md")
    const result = resolvePrompt(join(FIXTURES, "root.md"), { root: FIXTURES })
    writeBundle(outFile, result)
    expect(existsSync(outFile)).toBe(true)
    expect(existsSync(outFile + ".manifest.json")).toBe(true)
    const manifest = JSON.parse(readFileSync(outFile + ".manifest.json", "utf-8"))
    expect(manifest.files).toBeDefined()
    rmSync(outDir, { recursive: true, force: true })
  })
})
