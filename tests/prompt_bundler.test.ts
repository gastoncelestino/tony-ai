import { afterEach, beforeEach, describe, expect, test } from "bun:test"
import { createHash } from "node:crypto"
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { tmpdir } from "node:os"
import {
  buildAll,
  buildOrchestrator,
  buildPhase,
  checkGenerated,
  ORCHESTRATOR_BUNDLE,
  PromptBundleError,
  writeAll,
} from "../tools/prompt-bundler"

const repoRoot = resolve(import.meta.dir, "..")
let fixtureRoot = ""

function writeFixtureFile(path: string, content: string): void {
  mkdirSync(join(fixtureRoot, path, ".."), { recursive: true })
  writeFileSync(join(fixtureRoot, path), content, "utf8")
}

function createFixture(): string {
  fixtureRoot = mkdtempSync(join(tmpdir(), "tony-prompt-bundler-"))
  mkdirSync(join(fixtureRoot, "prompts/agents/includes"), { recursive: true })
  mkdirSync(join(fixtureRoot, "prompts/sdd"), { recursive: true })
  mkdirSync(join(fixtureRoot, "skills/_shared"), { recursive: true })
  writeFixtureFile("prompts/agents/tony-orchestrator.md", "ROOT\n{{include:./includes/a.md}}\n{{include:./includes/a.md}}\n")
  writeFixtureFile("prompts/agents/includes/a.md", "A\n{{include:./nested/b.md}}\n")
  writeFixtureFile("prompts/agents/includes/nested/b.md", "B\n")
  writeFixtureFile(
    "prompts/agents/includes/phase-manifest.json",
    JSON.stringify(
      {
        version: "test",
        base_includes: ["a.md"],
        phases: { demo: { includes: [], skills: ["demo.md"] } },
        review_phases: {},
      },
      null,
      2,
    ) + "\n",
  )
  writeFixtureFile("prompts/sdd/demo.md", "DEMO\n")
  writeFixtureFile("skills/_shared/demo.md", "SKILL\n")
  return fixtureRoot
}

beforeEach(() => {
  createFixture()
})

afterEach(() => {
  if (fixtureRoot) rmSync(fixtureRoot, { recursive: true, force: true })
  fixtureRoot = ""
})

describe("prompt bundler", () => {
  test("expands nested includes relative to the containing file", () => {
    const result = buildOrchestrator(fixtureRoot)
    expect(result.content).toContain("ROOT")
    expect(result.content).toContain("A")
    expect(result.content).toContain("B")
    expect(result.content).not.toContain("{{include:")
    expect(result.content).not.toContain("{file:")
  })

  test("deduplicates an include referenced more than once", () => {
    const result = buildOrchestrator(fixtureRoot)
    expect(result.content.match(/^A$/gm)?.length).toBe(1)
    expect(result.content).toContain("include deduplicated")
  })

  test("fails with the full chain for a missing include", () => {
    writeFixtureFile("prompts/agents/tony-orchestrator.md", "ROOT\n{{include:./includes/missing.md}}\n")
    expect(() => buildOrchestrator(fixtureRoot)).toThrow(/include not found.*missing\.md/)
  })

  test("fails on include cycles", () => {
    writeFixtureFile("prompts/agents/includes/nested/b.md", "B\n{{include:../a.md}}\n")
    expect(() => buildOrchestrator(fixtureRoot)).toThrow(/include cycle detected/)
  })

  test("rejects path traversal outside the repository root", () => {
    writeFixtureFile("prompts/agents/tony-orchestrator.md", "ROOT\n{{include:../../../../outside.md}}\n")
    expect(() => buildOrchestrator(fixtureRoot)).toThrow(/escapes repository root/)
  })

  test("rejects dynamic filenames", () => {
    writeFixtureFile("prompts/agents/tony-orchestrator.md", "ROOT\n{{include:./includes/{phase}.md}}\n")
    expect(() => buildOrchestrator(fixtureRoot)).toThrow(/dynamic paths are not allowed/)
  })

  test("materializes a phase from manifest includes, skills, and phase instructions", () => {
    const result = buildPhase(fixtureRoot, "demo")
    expect(result.path).toBe("prompts/generated/phases/demo.md")
    expect(result.content).toContain("A")
    expect(result.content).toContain("B")
    expect(result.content).toContain("SKILL")
    expect(result.content).toContain("DEMO")
    expect(result.content).not.toContain("{{include:")
  })

  test("writes deterministic generated outputs and detects drift", () => {
    writeAll(fixtureRoot)
    expect(checkGenerated(fixtureRoot)).toEqual([])
    writeFixtureFile("prompts/agents/includes/nested/b.md", "B changed\n")
    expect(() => checkGenerated(fixtureRoot)).not.toThrow()
    expect(checkGenerated(fixtureRoot).some((item) => item.includes("stale"))).toBe(true)
    writeAll(fixtureRoot)
    expect(checkGenerated(fixtureRoot)).toEqual([])
  })

  test("produces byte-identical output for unchanged inputs", () => {
    const first = buildAll(fixtureRoot)
    const second = buildAll(fixtureRoot)
    expect(first.orchestrator.content).toBe(second.orchestrator.content)
    expect(JSON.stringify(first.manifest)).toBe(JSON.stringify(second.manifest))
  })

  test("records dependency and bundle hashes", () => {
    const built = buildAll(fixtureRoot)
    const expected = createHash("sha256").update(built.orchestrator.content, "utf8").digest("hex")
    expect(built.manifest.bundle_sha256).toBe(expected)
    expect(built.manifest.dependencies.map((item) => item.path)).toContain("prompts/agents/includes/a.md")
  })
})

describe("repository prompt bundle contract", () => {
  test("the checked-in repository bundle is current and fully materialized", () => {
    expect(checkGenerated(repoRoot)).toEqual([])
    const bundle = readFileSync(join(repoRoot, ORCHESTRATOR_BUNDLE), "utf8")
    expect(bundle).not.toMatch(/\{\{include:/)
    expect(bundle).not.toMatch(/\{file:[^}]+\}/)
  })

  test("all manifest phases have generated bundles and generated config pointers", () => {
    const built = buildAll(repoRoot)
    const config = JSON.parse(readFileSync(join(repoRoot, "opencode.json"), "utf8")) as {
      agent: Record<string, { prompt?: string }>
    }
    expect(Object.keys(built.manifest.phases)).toHaveLength(18)
    for (const phase of Object.keys(built.manifest.phases)) {
      expect(config.agent[phase]?.prompt).toBe(`{file:./prompts/generated/phases/${phase}.md}`)
    }
  })

  test("source prompts use bundler directives instead of nested native config references", () => {
    const source = readFileSync(join(repoRoot, "prompts/agents/tony-orchestrator.md"), "utf8")
    expect(source).toMatch(/\{\{include:.*\}\}/)
    expect(source).not.toMatch(/\{file:[^}]+\}/)
  })
})
