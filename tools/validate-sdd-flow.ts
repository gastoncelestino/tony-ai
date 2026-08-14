import { existsSync, readFileSync } from "node:fs"
import { execFileSync } from "node:child_process"
import { resolve } from "node:path"

const ROOT = resolve(process.cwd())
const PYTHON = process.env.TONY_PYTHON ?? "python3"
let passed = 0
let failed = 0
let skipped = 0

function ok(message: string): void {
  passed++
  console.log(`OK   ${message}`)
}

function fail(message: string): void {
  failed++
  console.error(`FAIL ${message}`)
}

function skip(message: string): void {
  skipped++
  console.warn(`SKIP ${message}`)
}

function file(path: string): string {
  return resolve(ROOT, path)
}

function read(path: string): string {
  return readFileSync(file(path), "utf8")
}

function exists(path: string): boolean {
  return existsSync(file(path))
}

function run(command: string, args: string[], label: string): boolean {
  try {
    execFileSync(command, args, { cwd: ROOT, stdio: "inherit" })
    ok(label)
    return true
  } catch {
    fail(`${label} (exit code indicates failure)`)
    return false
  }
}

function checkRequiredFiles(): void {
  const required = [
    "opencode.json",
    "prompts/agents/tony-orchestrator.md",
    "prompts/agents/phase-capabilities.md",
    "skills/_shared/sdd-phase-common.md",
    "prompts/sdd/sdd-init.md",
    "prompts/sdd/sdd-onboard.md",
    "prompts/sdd/sdd-explore.md",
    "prompts/sdd/sdd-propose.md",
    "prompts/sdd/sdd-spec.md",
    "prompts/sdd/sdd-design.md",
    "prompts/sdd/sdd-tasks.md",
    "prompts/sdd/sdd-apply.md",
    "prompts/sdd/sdd-verify.md",
    "prompts/sdd/sdd-archive.md",
  ]

  for (const path of required) {
    exists(path) ? ok(`required file exists: ${path}`) : fail(`missing: ${path}`)
  }
}

function checkOrchestrator(): void {
  const prompt = read("prompts/agents/tony-orchestrator.md")
  const phaseRef = "{file:./phase-capabilities.md}"
  const forbidden = [
    "prompts/sdd/",
    "skills/sdd-",
    "phase-prompts/",
    "prompts/generated/",
    "prompt-manifest",
    "phase-manifest",
  ]

  prompt.includes(phaseRef)
    ? ok("orchestrator loads only the routing map")
    : fail("orchestrator does not reference phase-capabilities.md")

  for (const token of forbidden) {
    prompt.includes(token)
      ? fail(`orchestrator contains executor/legacy reference: ${token}`)
      : ok(`orchestrator does not contain: ${token}`)
  }

  const requiredText = [
    "Do NOT load executor phase prompts",
    "Do NOT perform exploration",
    "Prefer references/paths/topic keys",
    "platform delegation primitive",
  ]

  for (const text of requiredText) {
    prompt.includes(text)
      ? ok(`orchestrator context rule present: ${text}`)
      : fail(`orchestrator context rule missing: ${text}`)
  }
}

function checkPhaseContract(): void {
  const common = read("skills/_shared/sdd-phase-common.md")
  const required = [
    "Do the assigned phase only",
    "Never delegate",
    "Prefer artifact references/topic keys",
    "mem_search",
    "mem_get_observation",
    "mem_save",
    "status`: success | partial | blocked",
    "artifacts",
    "next",
    "risks",
  ]

  for (const text of required) {
    common.includes(text)
      ? ok(`common contract contains: ${text}`)
      : fail(`common contract missing: ${text}`)
  }
}

function checkApplyVerify(): void {
  const apply = read("prompts/sdd/sdd-apply.md")
  const verify = read("prompts/sdd/sdd-verify.md")

  const applyChecks = [
    ["assigned task slice", "apply has bounded task-slice scope"],
    ["relevant spec scenarios", "apply retrieves relevant spec only"],
    ["relevant design decisions", "apply retrieves relevant design only"],
    ["Do not load proposal, exploration, verify, archive", "apply rejects unrelated phase context"],
    ["sdd-verify", "apply recommends verify after completion"],
  ] as const

  const verifyChecks = [
    ["Read only the artifacts required", "verify has bounded artifact retrieval"],
    ["For each spec scenario", "verify checks runtime coverage per scenario"],
    ["execute it", "verify requires real execution evidence"],
    ["Run the smallest relevant tests", "verify runs focused validation"],
    ["Do not load another phase prompt", "verify rejects cross-phase prompt loading"],
  ] as const

  for (const [text, label] of applyChecks) {
    apply.includes(text) ? ok(label) : fail(label)
  }
  for (const [text, label] of verifyChecks) {
    verify.includes(text) ? ok(label) : fail(label)
  }
}

function checkPermissions(): void {
  const config = JSON.parse(read("opencode.json")) as {
    agent: Record<string, { permission?: Record<string, unknown> }>
    permission: Record<string, unknown>
  }

  const expectedAllows: Record<string, string[]> = {
    "sdd-explore": ["code-index_*", "tonymem_*"],
    "sdd-design": ["code-index_*", "tonymem_*"],
    "sdd-apply": ["code-index_*", "tonymem_*"],
    "sdd-verify": ["code-index_*", "tonymem_*"],
    "sdd-propose": ["tonymem_*"],
    "sdd-spec": ["tonymem_*"],
    "sdd-tasks": ["tonymem_*"],
    "sdd-archive": ["tonymem_*"],
    "sdd-init": ["tonymem_*"],
    "sdd-onboard": ["tonymem_*"]
  }

  for (const [agent, allows] of Object.entries(expectedAllows)) {
    const permission = config.agent[agent]?.permission ?? {}
    for (const tool of allows) {
      const actual = permission[tool]
      actual === "allow"
        ? ok(`${agent}: ${tool} allowed`)
        : fail(`${agent}: expected ${tool}=allow, got ${String(actual)}`)
    }
  }

  const global = config.permission
  for (const tool of ["context7_*", "code-index_*", "judgment-memory_*", "tony-kernel_*"]) {
    const actual = global[tool]
    actual === "deny"
      ? ok(`global deny: ${tool}`)
      : fail(`global ${tool} must be deny, got ${String(actual)}`)
  }

  const orchestratorTask = (config.agent["tony-orchestrator"]?.permission as { task?: Record<string, string> } | undefined)?.task ?? {}
  orchestratorTask["*"] === "deny"
    ? ok("orchestrator wildcard task permission denied")
    : fail("orchestrator wildcard task permission is not deny")

  for (const agent of Object.keys(expectedAllows)) {
    orchestratorTask[agent] === "allow"
      ? ok(`orchestrator can delegate ${agent}`)
      : fail(`orchestrator cannot delegate ${agent}`)
  }
}

function checkLegacyArchitecture(): void {
  const forbiddenPaths = [
    "prompts/generated",
    "scripts/generate-opencode-agents.ts",
    "tests/prompt_bundler.test.ts",
    "tools/build-prompts.ts",
    "tools/prompt-bundler.ts",
    "prompts/agents/includes/phase-manifest.json",
    "prompts/generated/prompt-manifest.json",
  ]

  for (const path of forbiddenPaths) {
    exists(path) ? fail(`legacy architecture still exists: ${path}`) : ok(`legacy path absent: ${path}`)
  }

  try {
    const output = execFileSync(
      "git",
      ["grep", "-n", "-I", "-E", "--", ":(exclude)tools/validate-sdd-flow.ts", "prompt-bundler|prompt_bundler|prompt-manifest|phase-manifest|prompts/generated"],
      { cwd: ROOT, encoding: "utf8" },
    )
    fail(`legacy references found:\n${output}`)
  } catch (error) {
    const exitCode = typeof error === "object" && error !== null && "status" in error ? (error as { status?: number }).status : undefined
    exitCode === 1
      ? ok("no tracked references to the removed prompt architecture")
      : fail("git grep for legacy references could not be completed")
  }
}

function checkGitDiff(): void {
  try {
    execFileSync("git", ["diff", "--check"], { cwd: ROOT, stdio: "inherit" })
    ok("git diff --check")
  } catch {
    fail("git diff --check")
  }
}

function checkConfigValidator(): void {
  run("bun", ["run", "tools/validate-config.ts"], "repository configuration validator")
}

function checkTests(): void {
  run("bun", ["test"], "Bun test suite")
  run(PYTHON, ["-m", "pytest"], "Python pytest suite")
}

function checkRuntimeAvailability(): void {
  try {
    execFileSync("opencode", ["--version"], { cwd: ROOT, stdio: "ignore" })
    ok("OpenCode CLI is available for manual runtime smoke testing")
  } catch {
    skip("OpenCode CLI not available; runtime delegation/MCP enforcement is not executed by this audit")
  }
}

function main(): void {
  console.log("\n=== Tony AI — SDD Architecture Audit ===\n")
  console.log("This audit checks structure, prompt boundaries, artifact contracts, MCP permissions, legacy cleanup, and test suites.")
  console.log("It does NOT impersonate an agent or execute real delegated SDD work.\n")

  checkRequiredFiles()
  checkOrchestrator()
  checkPhaseContract()
  checkApplyVerify()
  checkPermissions()
  checkLegacyArchitecture()
  checkGitDiff()
  checkConfigValidator()
  checkTests()
  checkRuntimeAvailability()

  console.log("\n=== Result ===")
  console.log(`PASS: ${passed}`)
  console.log(`FAIL: ${failed}`)
  console.log(`SKIP: ${skipped}`)

  if (failed > 0) {
    console.error("\nSDD architecture audit FAILED.")
    process.exit(1)
  }

  console.log("\nSDD architecture audit PASSED.")
  process.exit(0)
}

main()
