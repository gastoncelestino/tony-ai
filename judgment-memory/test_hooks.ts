import { test, expect, beforeEach, afterEach, mkdirSync, rmSync } from "bun:test"
import { join } from "path"
import { tmpdir } from "os"
import {
  runMockPlugin,
  createMockChatMessage,
  createMockChatMessageEmpty,
  createMockTaskOutput,
  createMockTaskOutputObject,
  createMockSystemTransform,
  createMockSessionCreated,
  runHook
} from "./__mocks__/opencode-plugin"
import { startMockServices } from "./__mocks__/http-mock"

import {
  parsePassiveRecord,
  upsertJudgment,
  extractProjectName,
  JD_TRIGGER_RE,
  JD_TERMINAL_RE
} from "./judgment-memory"

let tempDir: string
let dbPath: string
let mockServices: Awaited<ReturnType<typeof startMockServices>>

beforeEach(async () => {
  tempDir = join(tmpdir(), `judgment-test-${Date.now()}`)
  mkdirSync(tempDir, { recursive: true })
  dbPath = join(tempDir, "judgment-memory.db")
  process.env.JUDGMENT_MEMORY_DB = dbPath
  process.env.TONY_OLLAMA_URL = ""
  process.env.TONY_QDRANT_URL = ""
  mockServices = await startMockServices()
  process.env.TONY_OLLAMA_URL = mockServices.ollamaUrl
  process.env.TONY_QDRANT_URL = mockServices.qdrantUrl
})

afterEach(async () => {
  await mockServices.stop()
  rmSync(tempDir, { recursive: true, force: true })
  delete process.env.JUDGMENT_MEMORY_DB
  delete process.env.TONY_OLLAMA_URL
  delete process.env.TONY_QDRANT_URL
})

// ─── Tests de parsePassiveRecord ─────────────────────────────────────────────

test("parsePassiveRecord: extrae APPROVED correctamente", () => {
  const text = `
    Target: optimize query performance
    Judgment Day started...
    JUDGMENT: APPROVED ✅
    Lesson: check execution plan before optimization
  `
  const result = parsePassiveRecord(text, "session-1", "test-project")

  expect(result).not.toBeNull()
  expect(result!.final).toBe("approve")
  expect(result!.task).toContain("optimize query performance")
  expect(result!.lesson).toContain("check execution plan before optimization")
})

test("parsePassiveRecord: extrae ESCALATED correctamente", () => {
  const text = `
    Target: fix race condition in worker pool
    JUDGMENT: ESCALATED ⚠️
    Lesson: need distributed lock for shared state
  `
  const result = parsePassiveRecord(text, "session-2", "test-project")

  expect(result).not.toBeNull()
  expect(result!.final).toBe("escalated")
  expect(result!.task).toContain("fix race condition")
  expect(result!.lesson).toContain("distributed lock")
})

test("parsePassiveRecord: retorna null sin terminal line", () => {
  const text = `
    Some task output
    No judgment here
    Just regular work
  `
  const result = parsePassiveRecord(text, "session-3", "test-project")

  expect(result).toBeNull()
})

test("parsePassiveRecord: task fallback a truncated head sin 'Target:'", () => {
  const text = `JUDGMENT: APPROVED ✅ Some long text that should be truncated...`
  const result = parsePassiveRecord(text, "session-4", "test-project")

  expect(result).not.toBeNull()
  expect(result!.final).toBe("approve")
  expect(result!.task.length).toBeLessThanOrEqual(200)
})

test("parsePassiveRecord: lesson opcional — null sin 'Lesson:' line", () => {
  const text = `
    Target: refactor auth module
    JUDGMENT: APPROVED ✅
  `
  const result = parsePassiveRecord(text, "session-5", "test-project")

  expect(result).not.toBeNull()
  expect(result!.lesson).toBeUndefined()
})

// ─── Tests de JD_TRIGGER_RE ──────────────────────────────────────────────────

test("JD_TRIGGER_RE: detecta 'judgment day'", () => {
  expect(JD_TRIGGER_RE.test("let's run judgment day on this")).toBe(true)
})

test("JD_TRIGGER_RE: detecta 'dual review'", () => {
  expect(JD_TRIGGER_RE.test("need dual review here")).toBe(true)
})

test("JD_TRIGGER_RE: detecta 'adversarial review'", () => {
  expect(JD_TRIGGER_RE.test("adversarial review requested")).toBe(true)
})

test("JD_TRIGGER_RE: detecta 'juzgar'", () => {
  expect(JD_TRIGGER_RE.test("por favor juzgar esto")).toBe(true)
})

test("JD_TRIGGER_RE: no dispara sin keywords", () => {
  expect(JD_TRIGGER_RE.test("just a regular task")).toBe(false)
})

// ─── Tests de JD_TERMINAL_RE ─────────────────────────────────────────────────

test("JD_TERMINAL_RE: detecta APPROVED", () => {
  expect(JD_TERMINAL_RE.test("JUDGMENT: APPROVED ✅")).toBe(true)
})

test("JD_TERMINAL_RE: detecta ESCALATED", () => {
  expect(JD_TERMINAL_RE.test("JUDGMENT: ESCALATED ⚠️")).toBe(true)
})

test("JD_TERMINAL_RE: no dispara sin terminal line", () => {
  expect(JD_TERMINAL_RE.test("some task output")).toBe(false)
})

// ─── Tests de hooks del plugin ───────────────────────────────────────────────

test("chat.message: activa recall con keywords de Judgment Day", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const [input, output] = createMockChatMessage(
    "session-test-1",
    "Necesitamos juzgar este código antes de mergear"
  )

  await runHook(hooks, "chat.message", input, output)

  const [sysInput, sysOutput] = createMockSystemTransform("session-test-1")
  await runHook(hooks, "experimental.chat.system.transform", sysInput, sysOutput)

  const lastSystem = sysOutput.system[sysOutput.system.length - 1]
  expect(lastSystem).toContain("TONYMEM RECALL")
  expect(lastSystem).toContain("prior judgment")
})

test("chat.message: no activa recall sin keywords", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const [input, output] = createMockChatMessage(
    "session-test-2",
    "solo una tarea normal"
  )

  await runHook(hooks, "chat.message", input, output)

  const [sysInput, sysOutput] = createMockSystemTransform("session-test-2")
  await runHook(hooks, "experimental.chat.system.transform", sysInput, sysOutput)

  const lastSystem = sysOutput.system[sysOutput.system.length - 1]
  expect(lastSystem).not.toContain("TONYMEM RECALL")
})

test("tool.execute.after: captura pasiva de Task output con JUDGMENT: APPROVED", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const taskOutput = `
    Target: optimize query performance
    Judgment Day completed.
    JUDGMENT: APPROVED ✅
    Lesson: check execution plan before optimization
  `

  const [input, output] = createMockTaskOutput("session-test-3", taskOutput)
  await runHook(hooks, "tool.execute.after", input, output)

  const { Database } = await import("bun:sqlite")
  const db = new Database(dbPath)
  const rows = db.query("SELECT * FROM judgments WHERE project = 'project'").all()
  db.close()

  expect(rows.length).toBe(1)
  expect(rows[0].final).toBe("approve")
  expect(rows[0].task).toContain("optimize query performance")
})

test("tool.execute.after: captura pasiva con JUDGMENT: ESCALATED", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const taskOutput = `
    Target: fix race condition
    JUDGMENT: ESCALATED ⚠️
    Lesson: need distributed lock
  `

  const [input, output] = createMockTaskOutput("session-test-4", taskOutput)
  await runHook(hooks, "tool.execute.after", input, output)

  const { Database } = await import("bun:sqlite")
  const db = new Database(dbPath)
  const rows = db.query("SELECT * FROM judgments").all()
  db.close()

  expect(rows.length).toBe(1)
  expect(rows[0].final).toBe("escalated")
})

test("tool.execute.after: ignora output sin terminal line", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const [input, output] = createMockTaskOutput("session-test-5", "just regular output")
  await runHook(hooks, "tool.execute.after", input, output)

  const { Database } = await import("bun:sqlite")
  const db = new Database(dbPath)
  const rows = db.query("SELECT * FROM judgments").all()
  db.close()

  expect(rows.length).toBe(0)
})

test("tool.execute.after: ignora tool calls de judgment-memory", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const [input, output] = createMockTaskOutput(
    "session-test-6",
    "JUDGMENT: APPROVED ✅"
  )
  input.tool = "jd_record"

  await runHook(hooks, "tool.execute.after", input, output)

  const { Database } = await import("bun:sqlite")
  const db = new Database(dbPath)
  const rows = db.query("SELECT * FROM judgments").all()
  db.close()

  expect(rows.length).toBe(0)
})

test("tool.execute.after: captura pasiva con output object (no string)", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const [input, output] = createMockTaskOutputObject(
    "session-test-7",
    { result: "JUDGMENT: APPROVED ✅\nLesson: test lesson" }
  )

  await runHook(hooks, "tool.execute.after", input, output)

  const { Database } = await import("bun:sqlite")
  const db = new Database(dbPath)
  const rows = db.query("SELECT * FROM judgments").all()
  db.close()

  expect(rows.length).toBe(1)
})

test("system.transform: inyecta protocol instructions", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const [input, output] = createMockSystemTransform("session-test-8")
  await runHook(hooks, "experimental.chat.system.transform", input, output)

  const lastSystem = output.system[output.system.length - 1]
  expect(lastSystem).toContain("Judgment Day Memory Bridge")
  expect(lastSystem).toContain("jd_recall")
  expect(lastSystem).toContain("jd_record")
})

test("system.transform: consume pendingRecall y lo limpia", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const [chatInput, chatOutput] = createMockChatMessage(
    "session-test-9",
    "judgment day para este código"
  )
  await runHook(hooks, "chat.message", chatInput, chatOutput)

  const [sysInput, sysOutput] = createMockSystemTransform("session-test-9")
  await runHook(hooks, "experimental.chat.system.transform", sysInput, sysOutput)

  const lastSystem = sysOutput.system[sysOutput.system.length - 1]
  expect(lastSystem).toContain("TONYMEM RECALL")

  const [sysInput2, sysOutput2] = createMockSystemTransform("session-test-9")
  await runHook(hooks, "experimental.chat.system.transform", sysInput2, sysOutput2)

  const lastSystem2 = sysOutput2.system[sysOutput2.system.length - 1]
  expect(lastSystem2).not.toContain("TONYMEM RECALL")
})

test("system.transform: no inyecta recall si Qdrant/Ollama no responden", async () => {
  process.env.TONY_OLLAMA_URL = "http://localhost:1"
  process.env.TONY_QDRANT_URL = "http://localhost:1"

  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const [chatInput, chatOutput] = createMockChatMessage(
    "session-test-10",
    "judgment day para este código"
  )
  await runHook(hooks, "chat.message", chatInput, chatOutput)

  const [sysInput, sysOutput] = createMockSystemTransform("session-test-10")
  await runHook(hooks, "experimental.chat.system.transform", sysInput, sysOutput)

  const lastSystem = sysOutput.system[sysOutput.system.length - 1]
  expect(lastSystem).toContain("Judgment Day Memory Bridge")
  expect(lastSystem).not.toContain("TONYMEM RECALL")
})

// ─── Tests de upsertJudgment ─────────────────────────────────────────────────

test("upsertJudgment: upsert por (project, execution_id) — no duplica", () => {
  const rec = {
    executionId: "exec-1",
    project: "test-project",
    task: "test task",
    final: "approve" as const
  }

  upsertJudgment(rec, "point-1")
  upsertJudgment(rec, "point-1")

  const { Database } = require("bun:sqlite")
  const db = new Database(dbPath)
  const rows = db.query("SELECT * FROM judgments WHERE project = 'test-project'").all()
  db.close()

  expect(rows.length).toBe(1)
})

test("upsertJudgment: actualiza task si se re-graba", () => {
  const rec1 = {
    executionId: "exec-2",
    project: "test-project",
    task: "old task",
    final: "approve" as const
  }
  const rec2 = {
    executionId: "exec-2",
    project: "test-project",
    task: "updated task",
    final: "escalated" as const
  }

  upsertJudgment(rec1, null)
  upsertJudgment(rec2, null)

  const { Database } = require("bun:sqlite")
  const db = new Database(dbPath)
  const row = db.query("SELECT * FROM judgments WHERE execution_id = 'exec-2'").get()
  db.close()

  expect(row.task).toBe("updated task")
  expect(row.final).toBe("escalated")
})

// ─── Tests de extractProjectName ─────────────────────────────────────────────

test("extractProjectName: no crashea", () => {
  const result = extractProjectName("/tmp/test-project")
  expect(typeof result).toBe("string")
  expect(result.length).toBeGreaterThan(0)
})

// ─── Tests de integración: flujo completo ────────────────────────────────────

test("flujo completo: recall → captura pasiva → verificación", async () => {
  const hooks = await runMockPlugin(
    async () => {
      const { JudgmentMemory } = await import("./judgment-memory")
      return JudgmentMemory
    },
    { directory: "/test/project" }
  )

  const [chatInput, chatOutput] = createMockChatMessage(
    "session-flow-1",
    "necesito juzgar este código"
  )
  await runHook(hooks, "chat.message", chatInput, chatOutput)

  const [sysInput, sysOutput] = createMockSystemTransform("session-flow-1")
  await runHook(hooks, "experimental.chat.system.transform", sysInput, sysOutput)
  expect(sysOutput.system[sysOutput.system.length - 1]).toContain("TONYMEM RECALL")

  const [taskInput, taskOutput] = createMockTaskOutput(
    "session-flow-1",
    "Target: fix bug\nJUDGMENT: APPROVED ✅\nLesson: check edge cases"
  )
  await runHook(hooks, "tool.execute.after", taskInput, taskOutput)

  const { Database } = await import("bun:sqlite")
  const db = new Database(dbPath)
  const rows = db.query("SELECT * FROM judgments").all()
  db.close()

  expect(rows.length).toBe(1)
  expect(rows[0].final).toBe("approve")
  expect(rows[0].task).toContain("fix bug")
})
