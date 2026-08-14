import { existsSync, readFileSync } from "node:fs"
import { execFileSync } from "node:child_process"
import { resolve } from "node:path"

const ROOT = resolve(process.cwd())
const PYTHON = process.env.TONY_PYTHON ?? "python3"
const GREEN = "\x1b[32m"
const RED = "\x1b[31m"
const YELLOW = "\x1b[33m"
const RESET = "\x1b[0m"
let passed = 0
let failed = 0
let skipped = 0

function ok(message: string): void {
  passed++
  console.log(`${GREEN}OK${RESET}   ${message}`)
}

function fail(message: string): void {
  failed++
  console.error(`${RED}FAIL${RESET} ${message}`)
}

function skip(message: string): void {
  skipped++
  console.warn(`${YELLOW}SKIP${RESET} ${message}`)
}

function colorizeTestOutput(output: string): string {
  return output
    .split("\n")
    .map((line) => {
      const trimmed = line.trim()
      if (/^\d+ pass$/.test(trimmed)) return line.replace(/(\d+ pass)/, `${GREEN}$1${RESET}`)
      if (/^\d+ fail$/.test(trimmed)) return line.replace(/(\d+ fail)/, `${RED}$1${RESET}`)
      if (/^\d+ expect\(\) calls$/.test(trimmed)) return line.replace(/(\d+ expect\(\) calls)/, `${YELLOW}$1${RESET}`)
      if (/^tests\/.*\.+\s+\[.*\d+%\]$/.test(trimmed)) return `${GREEN}${line}${RESET}`
      return line
    })
    .join("\n")
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
    const output = execFileSync(command, args, { cwd: ROOT, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] })
    if (output) console.log(colorizeTestOutput(output))
    ok(label)
    return true
  } catch (error) {
    const stdout = typeof error === "object" && error !== null && "stdout" in error ? (error as { stdout?: Buffer | string }).stdout : undefined
    const stderr = typeof error === "object" && error !== null && "stderr" in error ? (error as { stderr?: Buffer | string }).stderr : undefined
    if (stdout) console.log(colorizeTestOutput(String(stdout)))
    if (stderr) console.error(String(stderr))
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
  for (const path of required) exists(path) ? ok(`required file exists: ${path}`) : fail(`missing: ${path}`)
}

function checkOrchestrator(): void {
  const prompt = read("prompts/agents/tony-orchestrator.md")
  const phaseRef = "{file:./phase-capabilities.md}"
  const forbidden = ["prompts/sdd/", "skills/sdd-", "phase-prompts/", "prompts/generated/", "prompt-manifest", "phase-manifest"]
  prompt.includes(phaseRef) ? ok("orchestrator loads only the routing map") : fail("orchestrator does not reference phase-capabilities.md")
  for (const token of forbidden) prompt.includes(token) ? fail(`orchestrator contains executor/legacy reference: ${token}`) : ok(`orchestrator does not contain: ${token}`)
  for (const text of ["Do NOT load executor phase prompts", "Do NOT perform exploration", "Prefer references/paths/topic keys", "platform delegation primitive"]) {
    prompt.includes(text) ? ok(`orchestrator context rule present: ${text}`) : fail(`orchestrator context rule missing: ${text}`)
  }
}

function checkPhaseContract(): void {
  const common = read("skills/_shared/sdd-phase-common.md")
  for (const text of ["Do the assigned phase only", "Never delegate", "Prefer artifact references/topic keys", "mem_search", "mem_get_observation", "mem_save", "status`: success | partial | blocked", "artifacts", "next", "risks"]) {
    common.includes(text) ? ok(`common contract contains: ${text}`) : fail(`common contract missing: ${text}`)
  }
}

function checkApplyVerify(): void {
  const apply = read("prompts/sdd/sdd-apply.md")
  const verify = read("prompts/sdd/sdd-verify.md")
  const applyChecks = [["assigned task slice", "apply has bounded task-slice scope"], ["relevant spec scenarios", "apply retrieves relevant spec only"], ["relevant design decisions", "apply retrieves relevant design only"], ["Do not load proposal, exploration, verify, archive", "apply rejects unrelated phase context"], ["sdd-verify", "apply recommends verify after completion"]] as const
  const verifyChecks = [["Read only the artifacts required", "verify has bounded artifact retrieval"], ["For each spec scenario", "verify checks runtime coverage per scenario"], ["execute it", "verify requires real execution evidence"], ["Run the smallest relevant tests", "verify runs focused validation"], ["Do not load another phase prompt", "verify rejects cross-phase prompt loading"]] as const
  for (const [text, label] of applyChecks) apply.includes(text) ? ok(label) : fail(label)
  for (const [text, label] of verifyChecks) verify.includes(text) ? ok(label) : fail(label)
}

function checkPermissions(): void {
  const config = JSON.parse(read("opencode.json")) as { agent: Record<string, { permission?: Record<string, unknown> }>; permission: Record<string, unknown> }
  const expectedAllows: Record<string, string[]> = {
    "sdd-explore": ["code-index_*", "tonymem_*"], "sdd-design": ["code-index_*", "tonymem_*"], "sdd-apply": ["code-index_*", "tonymem_*"], "sdd-verify": ["code-index_*", "tonymem_*"],
    "sdd-propose": ["tonymem_*"], "sdd-spec": ["tonymem_*"], "sdd-tasks": ["tonymem_*"], "sdd-archive": ["tonymem_*"], "sdd-init": ["tonymem_*"], "sdd-onboard": ["tonymem_*"]
  }
  for (const [agent, allows] of Object.entries(expectedAllows)) {
    const permission = config.agent[agent]?.permission ?? {}
    for (const tool of allows) permission[tool] === "allow" ? ok(`${agent}: ${tool} allowed`) : fail(`${agent}: expected ${tool}=allow, got ${String(permission[tool])}`)
  }
  for (const tool of ["context7_*", "code-index_*", "judgment-memory_*", "tony-kernel_*"]) config.permission[tool] === "deny" ? ok(`global deny: ${tool}`) : fail(`global ${tool} must be deny, got ${String(config.permission[tool])}`)
  const orchestratorTask = (config.agent["tony-orchestrator"]?.permission as { task?: Record<string, string> } | undefined)?.task ?? {}
  orchestratorTask["*"] === "deny" ? ok("orchestrator wildcard task permission denied") : fail("orchestrator wildcard task permission is not deny")
  for (const agent of Object.keys(expectedAllows)) orchestratorTask[agent] === "allow" ? ok(`orchestrator can delegate ${agent}`) : fail(`orchestrator cannot delegate ${agent}`)
}

function checkLegacyArchitecture(): void {
  for (const path of ["prompts/generated", "scripts/generate-opencode-agents.ts", "tests/prompt_bundler.test.ts", "tools/build-prompts.ts", "tools/prompt-bundler.ts", "prompts/agents/includes/phase-manifest.json", "prompts/generated/prompt-manifest.json"]) {
    exists(path) ? fail(`legacy architecture still exists: ${path}`) : ok(`legacy path absent: ${path}`)
  }
  try {
    const output = execFileSync("git", ["grep", "-n", "-I", "-E", "prompt-bundler|prompt_bundler|prompt-manifest|phase-manifest|prompts/generated", "--", ":(exclude)tools/validate-sdd-flow.ts"], { cwd: ROOT, encoding: "utf8" })
    fail(`legacy references found:\n${output}`)
  } catch (error) {
    const exitCode = typeof error === "object" && error !== null && "status" in error ? (error as { status?: number }).status : undefined
    exitCode === 1 ? ok("no tracked references to the removed prompt architecture") : fail("git grep for legacy references could not be completed")
  }
}

function checkGitDiff(): void {
  try {
    execFileSync("git", ["-c", "core.autocrlf=false", "diff", "--check"], { cwd: ROOT, stdio: "inherit" })
    ok("git diff --check")
  } catch {
    fail("git diff --check")
  }
}

function checkConfigValidator(): void { run("bun", ["run", "tools/validate-config.ts"], "repository configuration validator") }
function checkTests(): void { run("bun", ["test"], "Bun test suite"); run(PYTHON, ["-m", "pytest"], "Python pytest suite") }
function checkRuntimeAvailability(): void {
  try { execFileSync("opencode", ["--version"], { cwd: ROOT, stdio: "ignore" }); ok("OpenCode CLI is available for manual runtime smoke testing") }
  catch { skip("OpenCode CLI not available; runtime delegation/MCP enforcement is not executed by this audit") }
}

function main(): void {
  console.log("\n=== Tony AI — SDD Architecture Audit ===\n")
  console.log("This audit checks structure, prompt boundaries, artifact contracts, MCP permissions, legacy cleanup, and test suites.")
  console.log("It does NOT impersonate an agent or execute real delegated SDD work.\n")
  checkRequiredFiles(); checkOrchestrator(); checkPhaseContract(); checkApplyVerify(); checkPermissions(); checkLegacyArchitecture(); checkGitDiff(); checkConfigValidator(); checkTests(); checkRuntimeAvailability()
  console.log("\n=== Result ===")
  console.log(`${GREEN}PASS: ${passed}${RESET}`); console.log(`${RED}FAIL: ${failed}${RESET}`); console.log(`${YELLOW}SKIP: ${skipped}${RESET}`)
  if (failed > 0) { console.error(`${RED}\nSDD architecture audit FAILED.${RESET}`); process.exit(1) }
  console.log(`${GREEN}\nSDD architecture audit PASSED.${RESET}`); process.exit(0)
}
main()
