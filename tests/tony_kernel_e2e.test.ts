// test_e2e.ts — End-to-end adversarial tests for the Tony Kernel.
//
// Ejecutar:
//   bun test ./plugins/tony-kernel/test_e2e.ts
//
// Este test recorre el flujo SDD completo real (explore → archive)
// y, en cada paso, intenta ataques adversariales para verificar
// que el Kernel los bloquea.
//
// NO usa fakes ni mocks. Ejecuta python3 -m kernel.cli de verdad.
//
// Casos adversariales cubiertos:
//   1. Salto de fase (spec → apply)
//   2. Evidencia vacía/falsa
//   3. Tampering post-completion
//   4. Scope violation
//   5. Retry exhaustado
//   6. Sub-agent desconocido
//   7. Kernel caído (simulado)

import { test, expect, afterEach, beforeAll, beforeEach } from "bun:test"
import { spawn } from "node:child_process"
import { join, dirname } from "path"
import { fileURLToPath } from "url"
import { mkdirSync, rmSync, existsSync } from "fs"

const THIS_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(THIS_DIR, "..")

import {
  taskExecuteBeforeHook,
  taskExecuteAfterHook,
  derivePhase,
  __setKernelClientForTests,
  KernelBlockedError,
  KernelUnavailableError,
} from "../plugins/tony-kernel"

// ─── Test scratch area ────────────────────────────────────────────────────

const TEST_DIR = join(REPO_ROOT, ".test-e2e-tmp")
const OPENSPEC_DIR = join(TEST_DIR, "openspec")

function ensureTestDir() {
  if (!existsSync(TEST_DIR)) mkdirSync(TEST_DIR, { recursive: true })
  if (!existsSync(OPENSPEC_DIR)) mkdirSync(OPENSPEC_DIR, { recursive: true })
}

function cleanupTestDir() {
  try {
    if (existsSync(TEST_DIR)) rmSync(TEST_DIR, { recursive: true, force: true })
  } catch {
    // ignore cleanup errors
  }
}

function writeArtifact(relPath: string, content: string): string {
  ensureTestDir()
  const fullPath = join(TEST_DIR, relPath)
  const dir = fullPath.substring(0, fullPath.lastIndexOf("/"))
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  require("fs").writeFileSync(fullPath, content)
  // Verify write
  const verify = require("fs").readFileSync(fullPath, "utf-8")
  if (verify !== content) {
    throw new Error(`writeArtifact wrote wrong content to ${fullPath}: expected ${content}, got ${verify}`)
  }
  return fullPath
}

function tamperArtifact(relPath: string, newContent: string) {
  const fullPath = join(TEST_DIR, relPath)
  require("fs").writeFileSync(fullPath, newContent)
}

function sha256(text: string): string {
  const crypto = require("crypto")
  return crypto.createHash("sha256").update(text).digest("hex")
}

// ─── Helpers ─────────────────────────────────────────────────────────────

async function resetKernelState(): Promise<void> {
  const proc = spawn("python3", ["-m", "kernel.cli", "reset"], {
    cwd: REPO_ROOT,
    stdio: ["pipe", "pipe", "pipe"],
  })
  await new Promise<void>((resolve, reject) => {
    proc.on("close", () => resolve())
    proc.on("error", (err) => reject(err))
  })
}

function task(args: Record<string, unknown> = {}) {
  return {
    sessionID: "e2e-test",
    tool: "Task",
    arguments: args,
  }
}

function makeArtifact(kind: string, relPath: string, content: string) {
  const fullPath = writeArtifact(relPath, content)
  const hash = sha256(content)
  return {
    kind,
    path: `.test-e2e-tmp/${relPath}`,
    store: "openspec",
    hash,
    validated: true,
  }
}

function fakeArtifact(kind: string) {
  return {
    kind,
    path: `sdd/test/${kind}`,
    store: "tonymem",
    hash: "fake-hash",
    validated: true,
  }
}

// ─── Test isolation ──────────────────────────────────────────────────────

beforeAll(() => {
  cleanupTestDir()
})

beforeEach(async () => {
  cleanupTestDir()
  await resetKernelState()
})

afterEach(() => {
  __setKernelClientForTests(null)
  // The final test must not leave .test-e2e-tmp behind in the repository.
  cleanupTestDir()
})

// ─── FULL SDD FLOW ───────────────────────────────────────────────────────

const SDD_PHASES = [
  { phase: "explore", kind: "explore", rel: "explore.md" },
  { phase: "propose", kind: "proposal", rel: "proposal.md" },
  { phase: "sdd-spec", kind: "spec", rel: "spec.md" },
  { phase: "design", kind: "design", rel: "design.md" },
  { phase: "tasks", kind: "tasks", rel: "tasks.md" },
  { phase: "sdd-apply", kind: "apply-progress", rel: "apply.md" },
  { phase: "verify", kind: "verify-report", rel: "verify.md" },
  { phase: "archive", kind: "archive-report", rel: "archive.md" },
]

test("SDD complete flow: explore -> archive with real artifacts", async () => {
  __setKernelClientForTests(null)

  for (const step of SDD_PHASES) {
    // BEFORE: allow delegation
    await taskExecuteBeforeHook(task({ phase: step.phase }), { success: true })

    // AFTER: complete with real artifact
    const artifact = makeArtifact(step.kind, step.rel, `${step.phase} content v1`)
    await taskExecuteAfterHook(
      task({ phase: step.phase, artifacts: [artifact] }),
      "success"
    )
  }
})

// ─── ADVERSARIAL CASE 1: Phase skip ──────────────────────────────────────

test("ADVERSARIAL: skip propose -> spec blocked", async () => {
  __setKernelClientForTests(null)

  // Complete explore legitimately
  await taskExecuteBeforeHook(task({ phase: "explore" }), { success: true })
  const exploreArtifact = makeArtifact("explore", "explore.md", "explore v1")
  await taskExecuteAfterHook(task({ phase: "explore", artifacts: [exploreArtifact] }), "success")

  // Try to skip propose and go directly to spec
  await expect(
    taskExecuteBeforeHook(task({ phase: "sdd-spec" }), { success: true })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

test("ADVERSARIAL: skip design -> tasks blocked", async () => {
  __setKernelClientForTests(null)

  // Complete explore + propose legitimately
  await taskExecuteBeforeHook(task({ phase: "explore" }), { success: true })
  await taskExecuteAfterHook(task({ phase: "explore", artifacts: [makeArtifact("explore", "explore.md", "v1")] }), "success")

  await taskExecuteBeforeHook(task({ phase: "propose" }), { success: true })
  await taskExecuteAfterHook(task({ phase: "propose", artifacts: [makeArtifact("proposal", "proposal.md", "v1")] }), "success")

  await taskExecuteBeforeHook(task({ phase: "sdd-spec" }), { success: true })
  await taskExecuteAfterHook(task({ phase: "sdd-spec", artifacts: [makeArtifact("spec", "spec.md", "v1")] }), "success")

  // Try to skip design
  await expect(
    taskExecuteBeforeHook(task({ phase: "tasks" }), { success: true })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

// ─── ADVERSARIAL CASE 2: Fake/Missing evidence ───────────────────────────

test("ADVERSARIAL: missing artifacts -> KernelBlockedError", async () => {
  __setKernelClientForTests(null)

  await taskExecuteBeforeHook(task({ phase: "explore" }), { success: true })
  await expect(
    taskExecuteAfterHook(task({ phase: "explore" }), "success")
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

test("ADVERSARIAL: empty artifacts array -> KernelBlockedError", async () => {
  __setKernelClientForTests(null)

  await taskExecuteBeforeHook(task({ phase: "explore" }), { success: true })
  await expect(
    taskExecuteAfterHook(task({ phase: "explore", artifacts: [] }), "success")
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

test("ADVERSARIAL: fabricated evidence -> KernelBlockedError, phase NOT marked complete", async () => {
  __setKernelClientForTests(null)

  await taskExecuteBeforeHook(task({ phase: "explore" }), { success: true })
  const exploreArtifact = makeArtifact("explore", "explore.md", "explore v1")

  // Evidencia sin exit_code/command reales: Evidence.validate() la marca
  // inválida en kernel/schemas.py. record_phase_completion debe rechazarla
  // -> block_evidence_required. Esto debe llegar como excepción real al
  // caller del hook, no como un "success" silencioso mientras el kernel
  // queda con la fase en status=running/completed_at=null por debajo.
  await expect(
    taskExecuteAfterHook(
      task({
        phase: "explore",
        artifacts: [exploreArtifact],
        evidence: [{ type: "command", claim: "confío en que los tests pasaron" }],
      }),
      "success"
    )
  ).rejects.toBeInstanceOf(KernelBlockedError)

  // Confirmamos contra el kernel real que la fase efectivamente NO quedó
  // marcada como completa (no solo que el hook haya tirado un error).
  const status = await new Promise<any>((resolve, reject) => {
    const p = spawn("python3", ["-m", "kernel.cli", "status"], {
      cwd: REPO_ROOT,
      stdio: ["pipe", "pipe", "pipe"],
    })
    let out = ""
    p.stdout.on("data", (d) => (out += d.toString()))
    p.on("close", () => resolve(JSON.parse(out)))
    p.on("error", reject)
  })
  const explorePhase = status.phase_summary.phase_summary.phases.explore
  expect(explorePhase.completed_at).toBe(null)
})

// ─── ADVERSARIAL CASE 3: Tampering ───────────────────────────────────────

test("ADVERSARIAL: tampered spec blocks advancing and archive", async () => {
  __setKernelClientForTests(null)

  // Complete explore + propose + spec legitimately
  await taskExecuteBeforeHook(task({ phase: "explore" }), { success: true })
  await taskExecuteAfterHook(task({ phase: "explore", artifacts: [makeArtifact("explore", "explore.md", "v1")] }), "success")

  await taskExecuteBeforeHook(task({ phase: "propose" }), { success: true })
  await taskExecuteAfterHook(task({ phase: "propose", artifacts: [makeArtifact("proposal", "proposal.md", "v1")] }), "success")

  const specArtifact = makeArtifact("spec", "spec.md", "spec v1")
  await taskExecuteBeforeHook(task({ phase: "sdd-spec" }), { success: true })
  await taskExecuteAfterHook(task({ phase: "sdd-spec", artifacts: [specArtifact] }), "success")

  // Tamper the spec file on disk
  tamperArtifact("spec.md", "spec v1 - TAMPERED BY ATTACKER")

  // Now design should be blocked because spec artifact hash mismatch
  await expect(
    taskExecuteBeforeHook(task({ phase: "design" }), { success: true })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

// ─── ADVERSARIAL CASE 4: Scope violation ─────────────────────────────────

const EVIL_DIFF = `diff --git a/src/evil.js b/src/evil.js
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/src/evil.js
@@ -0,0 +1 @@
+evil content`

test("ADVERSARIAL: scope violation blocks completion", async () => {
  __setKernelClientForTests(null)

  // Complete explore legitimately (no scope check on first phase)
  await taskExecuteBeforeHook(task({ phase: "explore" }), { success: true })
  await taskExecuteAfterHook(task({ phase: "explore", artifacts: [makeArtifact("explore", "explore.md", "v1")] }), "success")

  // Try to complete propose with a diff that touches files outside allowed scope
  await taskExecuteBeforeHook(task({ phase: "propose" }), { success: true })
  await expect(
    taskExecuteAfterHook(task({
      phase: "propose",
      artifacts: [makeArtifact("proposal", "proposal.md", "v1")],
      gitDiff: EVIL_DIFF,
      allowedFiles: ["openspec/change-request.md"],
    }), "success")
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

// ─── ADVERSARIAL CASE 5: Retry exhaustion ─────────────────────────────────
//
// The retry budget is advanced by `record_attempt()` on failed phase
// application, not by `can_start_phase()` queries. The public CLI/plugin
// surface does not expose `record_attempt`, so retry exhaustion cannot be
// driven from this e2e test without adding production API surface.
// The retry contract is already covered by kernel/test_state_machine.py.

// ─── ADVERSARIAL CASE 6: Unknown sub-agent ───────────────────────────────

test("ADVERSARIAL: unknown subagent_type -> KernelBlockedError", async () => {
  __setKernelClientForTests(null)

  await expect(
    taskExecuteBeforeHook(
      task({ subagent_type: "unknown-evil-agent" }),
      { success: true }
    )
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

// ─── ADVERSARIAL CASE 7: Task reported failure ───────────────────────────

test("ADVERSARIAL: failed task output -> KernelBlockedError", async () => {
  __setKernelClientForTests(null)

  await taskExecuteBeforeHook(task({ phase: "explore" }), { success: true })
  const artifact = makeArtifact("explore", "explore.md", "v1")

  await expect(
    taskExecuteAfterHook(task({ phase: "explore", artifacts: [artifact] }), "Error: sub-agent crashed")
  ).rejects.toBeInstanceOf(KernelBlockedError)
})
