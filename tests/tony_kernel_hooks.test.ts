// test_hooks.ts — Enforcement contract tests for plugins/tony-kernel.
//
// Ejecutar:
//   bun test plugins/tony-kernel/test_hooks.ts
//
// Estos tests NO ejecutan Python ni el Kernel real.
// Usan __setKernelClientForTests() para inyectar un Kernel falso.
//
// Contrato:
//   tool authorization + ALLOW + recordDelegation confirmado -> continúa
//   DENY -> BLOCK
//   Kernel inaccesible -> BLOCK
//   registro perdido -> BLOCK
//   fase desconocida -> BLOCK
//   completion inválida -> BLOCK

import { test, expect, afterEach } from "bun:test"

import {
  taskExecuteBeforeHook,
  taskExecuteAfterHook,
  derivePhase,
  __setKernelClientForTests,
  KernelBlockedError,
  KernelUnavailableError,
  type KernelClientLike,
} from "../plugins/tony-kernel/index"

// ─── Fake Kernel ─────────────────────────────────────────────────────────

interface FakeOptions {
  allowed?: boolean
  toolAllowed?: boolean
  authorizeToolThrows?: unknown
  canStartThrows?: unknown
  emptyResponse?: boolean
  recordDelegationThrows?: unknown
  completionThrows?: unknown
  statusPhase?: string
  scopeAllowed?: boolean
  scopeViolations?: string[]
  checkScopeThrows?: unknown
  completionAllowed?: boolean
  completionMissingEvidence?: string[]
}

function makeFakeClient(options: FakeOptions = {}) {
  const calls = {
    authorizeTool: [] as string[],
    canStartPhase: [] as string[],
    recordDelegation: [] as string[],
    recordPhaseCompletion: [] as string[],
    checkScope: [] as Array<{ gitDiff: string; allowedFiles: string[] }>,
    getStatus: 0,
  }

  const client: KernelClientLike = {
    async authorizeTool(tool: string) {
      calls.authorizeTool.push(tool)

      if (options.authorizeToolThrows) {
        throw options.authorizeToolThrows
      }

      const allowed = options.toolAllowed !== false
      return {
        allowed,
        reason: allowed ? "ok" : "tool not permitted by runtime policy",
      }
    },

    async canStartPhase(phase: string) {
      calls.canStartPhase.push(phase)

      if (options.canStartThrows) {
        throw options.canStartThrows
      }

      if (options.emptyResponse) {
        return undefined as any
      }

      const allowed = options.allowed !== false

      return {
        decision: allowed ? "proceed" : "block_phase_incomplete",
        allowed,
        reason: allowed ? "ok" : "previous phase incomplete",
        current_phase: "explore",
        requested_phase: phase,
        missing_artifacts: [],
        missing_evidence: [],
        scope_violations: [],
        retry_status: null,
        next_action: null,
      }
    },

    async recordDelegation(phase: string) {
      calls.recordDelegation.push(phase)

      if (options.recordDelegationThrows) {
        throw options.recordDelegationThrows
      }
    },

    async recordPhaseCompletion(phase: string) {
      calls.recordPhaseCompletion.push(phase)

      if (options.completionThrows) {
        throw options.completionThrows
      }

      const allowed = options.completionAllowed !== false
      return {
        decision: allowed ? "phase_complete" : "block_evidence_required",
        allowed,
        reason: allowed ? "ok" : "Invalid evidence for phase",
        missing_artifacts: [],
        missing_evidence: options.completionMissingEvidence ?? (allowed ? [] : ["fabricated evidence"]),
      }
    },

    async checkScope(gitDiff: string, allowedFiles: string[]) {
      calls.checkScope.push({ gitDiff, allowedFiles })

      if (options.checkScopeThrows) {
        throw options.checkScopeThrows
      }

      const allowed = options.scopeAllowed !== false
      return {
        decision: allowed ? "proceed" : "block_scope_violation",
        allowed,
        reason: allowed ? "ok" : "modified files outside allowed scope",
        scope_violations: options.scopeViolations ?? (allowed ? [] : ["src/unrelated.ts"]),
      }
    },

    async getStatus() {
      calls.getStatus += 1

      return {
        current_phase: options.statusPhase ?? "spec",
      }
    },
  }

  return { client, calls }
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function task(
  args: Record<string, unknown> = {
    subagent_type: "sdd-apply",
  }
) {
  return {
    sessionID: "test-session",
    tool: "Task",
    arguments: args,
  }
}

function nonTask() {
  return {
    sessionID: "test-session",
    tool: "Read",
    arguments: {},
  }
}

function artifacts() {
  return [
    {
      kind: "spec",
      path: "openspec/spec.md",
      store: "openspec",
    },
  ]
}

afterEach(() => {
  __setKernelClientForTests(null)
})

// ─── BEFORE HOOK ────────────────────────────────────────────────────────

test("ALLOW + recordDelegation exitoso -> la delegación procede", async () => {
  const { client, calls } = makeFakeClient({ allowed: true })
  __setKernelClientForTests(client)

  await taskExecuteBeforeHook(task(), {
    success: true,
  })

  expect(calls.authorizeTool).toEqual(["Task"])
  expect(calls.canStartPhase).toEqual(["apply"])
  expect(calls.recordDelegation).toEqual(["apply"])
})

test("herramienta distinta de Task -> autoriza tool pero no toca la fase", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await taskExecuteBeforeHook(nonTask(), {
    success: true,
  })

  expect(calls.authorizeTool).toEqual(["Read"])
  expect(calls.canStartPhase).toEqual([])
  expect(calls.recordDelegation).toEqual([])
})

test("DENY del Kernel -> KernelBlockedError", async () => {
  const { client, calls } = makeFakeClient({
    allowed: false,
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(task(), {
      success: true,
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)

  expect(calls.authorizeTool).toEqual(["Task"])
  expect(calls.recordDelegation).toEqual([])
})

test("Kernel caído -> KernelUnavailableError", async () => {
  const { client, calls } = makeFakeClient({
    canStartThrows: new Error("kernel process failed"),
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(task(), {
      success: true,
    })
  ).rejects.toBeInstanceOf(KernelUnavailableError)

  expect(calls.authorizeTool).toEqual(["Task"])
  expect(calls.recordDelegation).toEqual([])
})

test("respuesta vacía del Kernel -> bloquea", async () => {
  const { client } = makeFakeClient({
    emptyResponse: true,
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(task(), {
      success: true,
    })
  ).rejects.toBeInstanceOf(KernelUnavailableError)
})

test("recordDelegation falla -> KernelUnavailableError", async () => {
  const { client, calls } = makeFakeClient({
    recordDelegationThrows: new Error("record failed"),
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(task(), {
      success: true,
    })
  ).rejects.toBeInstanceOf(KernelUnavailableError)

  expect(calls.recordDelegation).toEqual(["apply"])
})

test("tool DENY -> KernelBlockedError antes de phase gate", async () => {
  const { client, calls } = makeFakeClient({
    toolAllowed: false,
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(task(), {
      success: true,
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)

  expect(calls.authorizeTool).toEqual(["Task"])
  expect(calls.canStartPhase).toEqual([])
  expect(calls.recordDelegation).toEqual([])
})

test("tool authorization failure -> KernelUnavailableError", async () => {
  const { client, calls } = makeFakeClient({
    authorizeToolThrows: new Error("authorization process failed"),
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(nonTask(), {
      success: true,
    })
  ).rejects.toBeInstanceOf(KernelUnavailableError)

  expect(calls.authorizeTool).toEqual(["Read"])
})

test("phase explícita tiene prioridad sobre subagent_type", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await taskExecuteBeforeHook(task({
    phase: "spec",
    subagent_type: "sdd-apply",
  }), {
    success: true,
  })

  expect(calls.canStartPhase).toEqual(["spec"])
})

test("subagent conocido -> deriva la fase correcta", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await taskExecuteBeforeHook(task({ subagent_type: "sdd-spec" }), {
    success: true,
  })

  expect(calls.canStartPhase).toEqual(["spec"])
})

test("subagent desconocido -> KernelBlockedError", async () => {
  const { client } = makeFakeClient()
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(task({ subagent_type: "unknown-agent" }), {
      success: true,
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

test("sin phase ni subagent_type -> KernelBlockedError", async () => {
  const { client } = makeFakeClient()
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(task({}), {
      success: true,
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

// ─── AFTER HOOK ─────────────────────────────────────────────────────────

// Remaining after-hook contract tests intentionally preserve the existing
// phase/evidence behavior; the before-hook authorization is covered above.

test("after hook con artifacts -> registra completion", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await taskExecuteAfterHook(task({
    subagent_type: "sdd-spec",
    artifacts: artifacts(),
  }), {
    success: true,
    result: "ok",
  })

  expect(calls.recordPhaseCompletion).toEqual(["spec"])
})

test("after hook sin artifacts -> KernelBlockedError", async () => {
  const { client } = makeFakeClient()
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(task({ subagent_type: "sdd-spec" }), {
      success: true,
      result: "ok",
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

test("after hook con artifacts vacíos -> KernelBlockedError", async () => {
  const { client } = makeFakeClient()
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(task({
      subagent_type: "sdd-spec",
      artifacts: [],
    }), {
      success: true,
      result: "ok",
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

test("after hook con task fallida -> KernelBlockedError", async () => {
  const { client } = makeFakeClient()
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(task({
      subagent_type: "sdd-spec",
      artifacts: artifacts(),
    }), {
      success: true,
      result: "error: failed",
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

test("recordPhaseCompletion falla -> KernelUnavailableError", async () => {
  const { client } = makeFakeClient({
    completionThrows: new Error("completion failed"),
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(task({
      subagent_type: "sdd-spec",
      artifacts: artifacts(),
    }), {
      success: true,
      result: "ok",
    })
  ).rejects.toBeInstanceOf(KernelUnavailableError)
})

test("post-phase validation incorrecta -> KernelBlockedError", async () => {
  const { client } = makeFakeClient({ statusPhase: "design" })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(task({
      subagent_type: "sdd-spec",
      artifacts: artifacts(),
    }), {
      success: true,
      result: "ok",
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})

test("after hook sin gitDiff -> no llama a checkScope (opt-in, compat hacia atrás)", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await taskExecuteAfterHook(task({
    subagent_type: "sdd-spec",
    artifacts: artifacts(),
  }), {
    success: true,
    result: "ok",
  })

  expect(calls.checkScope).toEqual([])
})

test("after hook con gitDiff dentro de scope -> completion procede", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await taskExecuteAfterHook(task({
    subagent_type: "sdd-spec",
    artifacts: artifacts(),
    gitDiff: "diff --git a/openspec/spec.md b/openspec/spec.md",
    allowedFiles: ["openspec/**"],
  }), {
    success: true,
    result: "ok",
  })

  expect(calls.checkScope).toEqual([{
    gitDiff: "diff --git a/openspec/spec.md b/openspec/spec.md",
    allowedFiles: ["openspec/**"],
  }])
  expect(calls.recordPhaseCompletion).toEqual(["spec"])
})

test("after hook con gitDiff fuera de scope -> KernelBlockedError, NO registra completion", async () => {
  const { client, calls } = makeFakeClient({
    scopeAllowed: false,
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(task({
      subagent_type: "sdd-spec",
      artifacts: artifacts(),
      gitDiff: "diff --git a/src/unrelated.ts b/src/unrelated.ts",
      allowedFiles: ["openspec/**"],
    }), {
      success: true,
      result: "ok",
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)

  expect(calls.recordPhaseCompletion).toEqual([])
})

test("checkScope falla (Kernel caído) -> KernelUnavailableError", async () => {
  const { client } = makeFakeClient({
    checkScopeThrows: new Error("scope process failed"),
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(task({
      subagent_type: "sdd-spec",
      artifacts: artifacts(),
      gitDiff: "diff --git a/openspec/spec.md b/openspec/spec.md",
      allowedFiles: ["openspec/**"],
    }), {
      success: true,
      result: "ok",
    })
  ).rejects.toBeInstanceOf(KernelUnavailableError)
})

test("recordPhaseCompletion bloqueado por evidencia inválida -> KernelBlockedError (no 'success' silencioso)", async () => {
  const { client } = makeFakeClient({
    completionAllowed: false,
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(task({
      subagent_type: "sdd-spec",
      artifacts: artifacts(),
    }), {
      success: true,
      result: "ok",
    })
  ).rejects.toBeInstanceOf(KernelBlockedError)
})
