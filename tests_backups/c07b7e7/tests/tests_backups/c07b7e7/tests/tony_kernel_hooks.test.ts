// test_hooks.ts — Enforcement contract tests for plugins/tony-kernel.
//
// Ejecutar:
//   bun test plugins/tony-kernel/test_hooks.ts
//
// Estos tests NO ejecutan Python ni el Kernel real.
// Usan __setKernelClientForTests() para inyectar un Kernel falso.
//
// Contrato:
//   ALLOW + recordDelegation confirmado -> continúa
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
} from "../plugins/tony-kernel"

// ─── Fake Kernel ─────────────────────────────────────────────────────────

interface FakeOptions {
  allowed?: boolean
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
    canStartPhase: [] as string[],
    recordDelegation: [] as string[],
    recordPhaseCompletion: [] as string[],
    checkScope: [] as Array<{ gitDiff: string; allowedFiles: string[] }>,
    getStatus: 0,
  }

  const client: KernelClientLike = {
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

  expect(calls.canStartPhase).toEqual(["apply"])
  expect(calls.recordDelegation).toEqual(["apply"])
})

test("herramienta distinta de Task -> no toca el Kernel", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await taskExecuteBeforeHook(nonTask(), {
    success: true,
  })

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
    allowed: true,
    recordDelegationThrows: new Error("kernel write failed"),
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(task(), {
      success: true,
    })
  ).rejects.toBeInstanceOf(KernelUnavailableError)

  expect(calls.recordDelegation).toEqual(["apply"])
})

// ─── PHASE DERIVATION ───────────────────────────────────────────────────

test("phase explícita tiene prioridad sobre subagent_type", () => {
  expect(
    derivePhase({
      phase: "verify",
      subagent_type: "sdd-apply",
    })
  ).toBe("verify")
})

test("subagent conocido -> deriva la fase correcta", () => {
  expect(
    derivePhase({
      subagent_type: "sdd-spec",
    })
  ).toBe("spec")

  expect(
    derivePhase({
      subagent_type: "sdd-design",
    })
  ).toBe("design")

  expect(
    derivePhase({
      subagent_type: "sdd-verify",
    })
  ).toBe("verify")
})

test("subagent desconocido -> KernelBlockedError", () => {
  expect(() =>
    derivePhase({
      subagent_type: "algo-desconocido",
    })
  ).toThrow(KernelBlockedError)
})

test("sin phase ni subagent_type -> KernelBlockedError", () => {
  expect(() => derivePhase({})).toThrow(KernelBlockedError)
})

test("subagent desconocido NO cae silenciosamente en apply", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await expect(
    taskExecuteBeforeHook(
      task({
        subagent_type: "algo-desconocido",
      }),
      {
        success: true,
      }
    )
  ).rejects.toBeInstanceOf(KernelBlockedError)

  expect(calls.canStartPhase).toEqual([])
})

// ─── AFTER HOOK ──────────────────────────────────────────────────────────

test("after hook con artifacts -> registra completion", async () => {
  const { client, calls } = makeFakeClient({
    statusPhase: "spec",
  })
  __setKernelClientForTests(client)

  await taskExecuteAfterHook(
    task({
      subagent_type: "sdd-spec",
      artifacts: artifacts(),
    }),
    "success"
  )

  expect(calls.recordPhaseCompletion).toEqual(["spec"])
  expect(calls.getStatus).toBe(1)
})

test("after hook sin artifacts -> KernelBlockedError", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(
      task({
        subagent_type: "sdd-spec",
      }),
      "success"
    )
  ).rejects.toBeInstanceOf(KernelBlockedError)

  expect(calls.recordPhaseCompletion).toEqual([])
})

test("after hook con artifacts vacíos -> KernelBlockedError", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(
      task({
        subagent_type: "sdd-spec",
        artifacts: [],
      }),
      "success"
    )
  ).rejects.toBeInstanceOf(KernelBlockedError)

  expect(calls.recordPhaseCompletion).toEqual([])
})

test("after hook con task fallida -> KernelBlockedError", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(
      task({
        subagent_type: "sdd-spec",
        artifacts: artifacts(),
      }),
      "Error: sub-agent failed"
    )
  ).rejects.toBeInstanceOf(KernelBlockedError)

  expect(calls.recordPhaseCompletion).toEqual([])
})

test("recordPhaseCompletion falla -> KernelUnavailableError", async () => {
  const { client, calls } = makeFakeClient({
    completionThrows: new Error("kernel write failed"),
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(
      task({
        subagent_type: "sdd-spec",
        artifacts: artifacts(),
      }),
      "success"
    )
  ).rejects.toBeInstanceOf(KernelUnavailableError)

  expect(calls.recordPhaseCompletion).toEqual(["spec"])
})

test("post-phase validation incorrecta -> KernelBlockedError", async () => {
  const { client, calls } = makeFakeClient({
    statusPhase: "explore",
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(
      task({
        subagent_type: "sdd-spec",
        artifacts: artifacts(),
      }),
      "success"
    )
  ).rejects.toBeInstanceOf(KernelBlockedError)

  expect(calls.recordPhaseCompletion).toEqual(["spec"])
  expect(calls.getStatus).toBe(1)
})

// ─── SCOPE GUARD (gap #3: checkScope was defined but never called) ───────

test("after hook sin gitDiff -> no llama a checkScope (opt-in, compat hacia atrás)", async () => {
  const { client, calls } = makeFakeClient()
  __setKernelClientForTests(client)

  await taskExecuteAfterHook(
    task({
      subagent_type: "sdd-spec",
      artifacts: artifacts(),
    }),
    "success"
  )

  expect(calls.checkScope).toEqual([])
  expect(calls.recordPhaseCompletion).toEqual(["spec"])
})

test("after hook con gitDiff dentro de scope -> procede y registra completion", async () => {
  const { client, calls } = makeFakeClient({ scopeAllowed: true })
  __setKernelClientForTests(client)

  await taskExecuteAfterHook(
    task({
      subagent_type: "sdd-spec",
      artifacts: artifacts(),
      gitDiff: "+++ b/openspec/spec.md\n",
      allowedFiles: ["openspec/*"],
    }),
    "success"
  )

  expect(calls.checkScope).toEqual([
    { gitDiff: "+++ b/openspec/spec.md\n", allowedFiles: ["openspec/*"] },
  ])
  expect(calls.recordPhaseCompletion).toEqual(["spec"])
})

test("after hook con gitDiff fuera de scope -> KernelBlockedError, NO registra completion", async () => {
  const { client, calls } = makeFakeClient({
    scopeAllowed: false,
    scopeViolations: ["kernel/schemas.py"],
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(
      task({
        subagent_type: "sdd-spec",
        artifacts: artifacts(),
        gitDiff: "+++ b/kernel/schemas.py\n",
        allowedFiles: ["openspec/*"],
      }),
      "success"
    )
  ).rejects.toBeInstanceOf(KernelBlockedError)

  // La violación de scope debe bloquear ANTES de tocar recordPhaseCompletion.
  expect(calls.checkScope.length).toBe(1)
  expect(calls.recordPhaseCompletion).toEqual([])
})

test("checkScope falla (Kernel caído) -> KernelUnavailableError", async () => {
  const { client, calls } = makeFakeClient({
    checkScopeThrows: new Error("kernel process failed"),
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(
      task({
        subagent_type: "sdd-spec",
        artifacts: artifacts(),
        gitDiff: "+++ b/openspec/spec.md\n",
        allowedFiles: ["openspec/*"],
      }),
      "success"
    )
  ).rejects.toBeInstanceOf(KernelUnavailableError)

  expect(calls.recordPhaseCompletion).toEqual([])
})

test("recordPhaseCompletion bloqueado por evidencia inválida -> KernelBlockedError (no 'success' silencioso)", async () => {
  const { client, calls } = makeFakeClient({
    completionAllowed: false,
    completionMissingEvidence: ["command claim without exit_code"],
  })
  __setKernelClientForTests(client)

  await expect(
    taskExecuteAfterHook(
      task({
        subagent_type: "sdd-spec",
        artifacts: artifacts(),
        evidence: [{ type: "command", claim: "confío en que anduvo" }],
      }),
      "success"
    )
  ).rejects.toBeInstanceOf(KernelBlockedError)

  expect(calls.recordPhaseCompletion).toEqual(["spec"])
})
