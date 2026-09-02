import { describe, expect, test } from "bun:test"
import { createEvidenceLedger } from "./evidence-ledger"
import { evaluateEvidenceClaim } from "./evidence-gate"

function record(
  ledger: ReturnType<typeof createEvidenceLedger>,
  input: {
    id: string
    kind: "FILE_DISCOVERED" | "FILE_CONTENT_READ" | "SEARCH_RESULT" | "COMMAND_RESULT" | "FILE_MODIFIED" | "TOOL_ERROR"
    callId: string
    tool: string
    target?: string
    output?: string
  },
) {
  ledger.record({
    id: input.id,
    kind: input.kind,
    sessionId: "session-1",
    callId: input.callId,
    tool: input.tool,
    createdAt: "2026-09-02T00:00:00.000Z",
    target: input.target,
    summary: input.output ?? input.kind,
    output: input.output,
  })
}

describe("evidence gate", () => {
  test("blocks a file-content claim when only discovery evidence exists", () => {
    const ledger = createEvidenceLedger()

    record(ledger, {
      id: "e1",
      kind: "FILE_DISCOVERED",
      callId: "call-glob",
      tool: "glob",
      target: "package.json",
      output: "package.json",
    })

    const result = evaluateEvidenceClaim(ledger, {
      id: "claim-main-entry",
      type: "file_content",
      statement: "package.json declares the main entry point",
      requirements: [
        {
          kind: "FILE_CONTENT_READ",
          target: "package.json",
          tool: "read",
        },
      ],
    })

    expect(result.allowed).toBe(false)
    expect(result.matchedEvidenceIds).toEqual([])
    expect(result.missing).toEqual([
      {
        kind: "FILE_CONTENT_READ",
        target: "package.json",
        tool: "read",
      },
    ])
  })

  test("allows a file-content claim after the file is actually read", () => {
    const ledger = createEvidenceLedger()

    record(ledger, {
      id: "e1",
      kind: "FILE_DISCOVERED",
      callId: "call-glob",
      tool: "glob",
      target: "package.json",
    })
    record(ledger, {
      id: "e2",
      kind: "FILE_CONTENT_READ",
      callId: "call-read",
      tool: "read",
      target: "package.json",
      output: '{"main":"src/index.js"}',
    })

    const result = evaluateEvidenceClaim(ledger, {
      id: "claim-main-entry",
      type: "file_content",
      requirements: [
        {
          kind: "FILE_CONTENT_READ",
          target: "package.json",
          tool: "read",
        },
      ],
    })

    expect(result.allowed).toBe(true)
    expect(result.matchedEvidenceIds).toEqual(["e2"])
    expect(result.missing).toEqual([])
  })

  test("does not let an explicitly selected discovery evidence satisfy a content claim", () => {
    const ledger = createEvidenceLedger()

    record(ledger, {
      id: "e1",
      kind: "FILE_DISCOVERED",
      callId: "call-glob",
      tool: "glob",
      target: "package.json",
    })
    record(ledger, {
      id: "e2",
      kind: "FILE_CONTENT_READ",
      callId: "call-read",
      tool: "read",
      target: "package.json",
    })

    const result = evaluateEvidenceClaim(ledger, {
      id: "claim-main-entry",
      type: "file_content",
      evidenceIds: ["e1"],
      requirements: [
        {
          kind: "FILE_CONTENT_READ",
          target: "package.json",
        },
      ],
    })

    expect(result.allowed).toBe(false)
    expect(result.matchedEvidenceIds).toEqual([])
  })

  test("allows a relative target to match the repository absolute path", () => {
    const ledger = createEvidenceLedger()

    record(ledger, {
      id: "e1",
      kind: "FILE_CONTENT_READ",
      callId: "call-read",
      tool: "read",
      target: "/mnt/c/proyectos/tony-ai/package.json",
    })

    const result = evaluateEvidenceClaim(ledger, {
      id: "claim-package",
      type: "file_content",
      requirements: [
        {
          kind: "FILE_CONTENT_READ",
          target: "package.json",
        },
      ],
    })

    expect(result.allowed).toBe(true)
    expect(result.matchedEvidenceIds).toEqual(["e1"])
  })

  test("blocks a claim when the evidence target does not match", () => {
    const ledger = createEvidenceLedger()

    record(ledger, {
      id: "e1",
      kind: "FILE_CONTENT_READ",
      callId: "call-read",
      tool: "read",
      target: "src/index.ts",
    })

    const result = evaluateEvidenceClaim(ledger, {
      id: "claim-package",
      type: "file_content",
      requirements: [
        {
          kind: "FILE_CONTENT_READ",
          target: "package.json",
        },
      ],
    })

    expect(result.allowed).toBe(false)
    expect(result.missing).toHaveLength(1)
  })

  test("a tool error never satisfies a successful file-content requirement", () => {
    const ledger = createEvidenceLedger()

    record(ledger, {
      id: "e1",
      kind: "TOOL_ERROR",
      callId: "call-read",
      tool: "read",
      target: "package.json",
      output: "permission denied",
    })

    const result = evaluateEvidenceClaim(ledger, {
      id: "claim-package",
      type: "file_content",
      requirements: [
        {
          kind: "FILE_CONTENT_READ",
          target: "package.json",
        },
      ],
    })

    expect(result.allowed).toBe(false)
  })

  test("all requirements must be satisfied", () => {
    const ledger = createEvidenceLedger()

    record(ledger, {
      id: "e1",
      kind: "FILE_CONTENT_READ",
      callId: "call-read",
      tool: "read",
      target: "package.json",
    })

    const result = evaluateEvidenceClaim(ledger, {
      id: "claim-read-and-search",
      type: "search",
      requirements: [
        {
          kind: "FILE_CONTENT_READ",
          target: "package.json",
        },
        {
          kind: "SEARCH_RESULT",
          target: "main",
        },
      ],
    })

    expect(result.allowed).toBe(false)
    expect(result.matchedEvidenceIds).toEqual(["e1"])
    expect(result.missing).toHaveLength(1)
    expect(result.missing[0]?.kind).toBe("SEARCH_RESULT")
  })
})
