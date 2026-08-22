import { afterAll, beforeAll, beforeEach, expect, test } from "bun:test"
import { Database } from "bun:sqlite"
import { mkdirSync, rmSync } from "node:fs"
import { join } from "node:path"
import { tmpdir } from "node:os"

/**
 * Este test importa el plugin después de configurar el entorno y ejecuta
 * JudgmentMemory(ctx), no una copia local de sus hooks.
 */

type RequestRecord = {
  method: string
  path: string
  body: unknown
}

type MockServices = {
  server: ReturnType<typeof Bun.serve>
  requests: RequestRecord[]
  upserts: unknown[]
  failEmbeddings: boolean
}

type Hook = (input: any, output: any) => Promise<any> | any

type HookSet = {
  "chat.message": Hook
  "tool.execute.after": Hook
  "experimental.chat.system.transform": Hook
}

type PluginContext = {
  directory: string
  event: (_input: unknown) => Promise<void>
  emit: (_eventName: string, _data: unknown) => Promise<void>
}

let rootDir: string
let dbPath: string
let services: MockServices
let JudgmentMemory: (ctx: PluginContext) => Promise<HookSet>
let createJudgmentMemory: any
let parsePassiveRecord: any
let upsertJudgment: any
let JD_TRIGGER_RE: RegExp
let JD_TERMINAL_RE: RegExp
let JUDGMENT_MEMORY_TOOLS: Set<string>
let RECALL_SCORE_THRESHOLD: number

function createMockServices(): MockServices {
  const requests: RequestRecord[] = []
  const upserts: unknown[] = []
  const state: Pick<MockServices, "failEmbeddings"> = {
    failEmbeddings: false,
  }

  const server = Bun.serve({
    port: 0,
    async fetch(request) {
      const url = new URL(request.url)
      let body: unknown = undefined

      if (request.method !== "GET" && request.method !== "HEAD") {
        body = await request.json().catch(() => undefined)
      }

      requests.push({
        method: request.method,
        path: `${url.pathname}${url.search}`,
        body,
      })

      // Ollama-compatible embedding endpoint.
      if (request.method === "POST" && url.pathname === "/api/embed") {
        if (state.failEmbeddings) {
          return Response.json({ error: "embedding service unavailable" }, { status: 503 })
        }

        return Response.json({
          embeddings: [[0.1, 0.2, 0.3, 0.4]],
        })
      }

      // semanticSearch() first checks that the collection exists.
      if (request.method === "GET" && url.pathname.startsWith("/collections/")) {
        return Response.json({
          result: { vectors: { size: 4, distance: "Cosine" } },
        })
      }

      // semanticSearch() searches prior judgments.
      if (
        request.method === "POST" &&
        url.pathname.endsWith("/points/search")
      ) {
        return Response.json({
          result: [
            {
              id: "prior-1",
              score: 0.91,
              payload: {
                final: "approve",
                task: "previous auth review",
                lesson: "check token refresh before retry",
                fix: "refresh the access token",
              },
            },
          ],
        })
      }

      // Passive capture ensures the collection and then upserts one point.
      if (
        request.method === "PUT" &&
        url.pathname.endsWith("/points") &&
        url.searchParams.get("wait") === "true"
      ) {
        upserts.push(body)
        return Response.json({ result: { status: "completed" } })
      }

      return Response.json({ error: "not found" }, { status: 404 })
    },
  })

  return {
    server,
    requests,
    upserts,
    get failEmbeddings() {
      return state.failEmbeddings
    },
    set failEmbeddings(value: boolean) {
      state.failEmbeddings = value
    },
  } as MockServices
}

function createContext(directory: string): PluginContext {
  return {
    directory,
    event: async () => {},
    emit: async () => {},
  }
}

function dbRows(): Array<Record<string, unknown>> {
  const db = new Database(dbPath, { readonly: true })
  try {
    return db
      .query(
        `SELECT execution_id, project, task, final, lesson, point_id
         FROM judgments
         ORDER BY id`,
      )
      .all() as Array<Record<string, unknown>>
  } finally {
    db.close()
  }
}

function clearDb(): void {
  const db = new Database(dbPath)
  try {
    db.exec("DELETE FROM judgments")
  } finally {
    db.close()
  }
}

function projectNameFromContext(): string {
  return rootDir.split("/").pop() ?? rootDir
}

function lastRequest(pathSuffix: string): RequestRecord | undefined {
  return [...services.requests]
    .reverse()
    .find((request) => request.path.endsWith(pathSuffix))
}

beforeAll(async () => {
  rootDir = join(tmpdir(), `tony-ai-jm-hooks-${process.pid}-${Date.now()}`)
  mkdirSync(rootDir, { recursive: true })
  dbPath = join(rootDir, "judgment-memory.db")
  services = createMockServices()

  // Estas variables se leen al cargar los módulos.
  process.env.JUDGMENT_MEMORY_DB = dbPath
  process.env.TONY_OLLAMA_URL = `http://127.0.0.1:${services.server.port}`
  process.env.TONY_QDRANT_URL = `http://127.0.0.1:${services.server.port}`
  process.env.TONY_EMBED_MODEL = "test-embedding-model"
  process.env.TONY_RECALL_SCORE_THRESHOLD = "0.5"
  process.env.JUDGMENT_MEMORY_DEBUG = "0"

  // Import dinámico: se hace después de fijar las variables de entorno.
  // El plugin real queda instanciado en cada test con JudgmentMemory(ctx).
  ;({
    JudgmentMemory,
    createJudgmentMemory,
    parsePassiveRecord,
    upsertJudgment,
    JD_TRIGGER_RE,
    JD_TERMINAL_RE,
    JUDGMENT_MEMORY_TOOLS,
    RECALL_SCORE_THRESHOLD,
  } = await import("../plugins/judgment-memory"))

  // La inicialización del plugin crea la tabla antes de que corra beforeEach.
  await JudgmentMemory(createContext(rootDir))
})

afterAll(() => {
  services.server.stop()
  rmSync(rootDir, { recursive: true, force: true })

  delete process.env.JUDGMENT_MEMORY_DB
  delete process.env.TONY_OLLAMA_URL
  delete process.env.TONY_QDRANT_URL
  delete process.env.TONY_EMBED_MODEL
  delete process.env.TONY_RECALL_SCORE_THRESHOLD
  delete process.env.JUDGMENT_MEMORY_DEBUG
})

beforeEach(() => {
  services.requests.length = 0
  services.upserts.length = 0
  services.failEmbeddings = false
  clearDb()
})

test("parsePassiveRecord real: cubre formatos, límites y entradas inválidas", () => {
  const longTask = "x".repeat(260)
  const longLesson = "l".repeat(520)
  const cases = [
    {
      text: " Target - unicode ✓\nLesson:  reusable insight \nJUDGMENT: APPROVED ✅",
      expectedTask: "unicode ✓",
      expectedFinal: "approve",
      expectedLesson: "reusable insight",
    },
    {
      text: "Target: first target\nTarget: second target\nJUDGMENT: ESCALATED ⚠️",
      expectedTask: "first target",
      expectedFinal: "escalated",
      expectedLesson: undefined,
    },
    {
      text: "Review \"security boundary\"\nJUDGMENT: APPROVED ✅",
      expectedTask: "security boundary",
      expectedFinal: "approve",
      expectedLesson: undefined,
    },
    {
      text: "JUDGMENT: APPROVED ✅",
      expectedTask: "unknown task",
      expectedFinal: "approve",
      expectedLesson: undefined,
    },
  ]

  for (const item of cases) {
    const result = parsePassiveRecord(item.text, "parser-session", "parser-project")
    expect(result?.task).toBe(item.expectedTask)
    expect(result?.final).toBe(item.expectedFinal)
    expect(result?.lesson).toBe(item.expectedLesson)
  }

  const bounded = parsePassiveRecord(
    `Target: ${longTask}\nLesson: ${longLesson}\nJUDGMENT: APPROVED ✅`,
    "parser-limits",
    "parser-project",
  )
  expect(bounded?.task.length).toBe(200)
  expect(bounded?.lesson?.length).toBe(500)
  expect(parsePassiveRecord("Target: no terminal", "s", "p")).toBeNull()
  expect(parsePassiveRecord("Target: rejected\nJUDGMENT: REJECTED ❌", "s", "p")).toBeNull()
})

test("upsertJudgment real: no duplica project + execution_id y actualiza el registro", () => {
  const first = parsePassiveRecord(
    "Target: same execution\nLesson: first\nJUDGMENT: APPROVED ✅",
    "stable-session",
    "stable-project",
  )
  expect(first).not.toBeNull()

  upsertJudgment(first, "point-a")
  upsertJudgment(
    { ...first, final: "escalated", lesson: "second" },
    "point-b",
  )

  const rows = dbRows()
  expect(rows).toHaveLength(1)
  expect(rows[0].final).toBe("escalated")
  expect(rows[0].lesson).toBe("second")
  expect(rows[0].point_id).toBe("point-b")
})

test("createJudgmentMemory: permite inyectar semanticSearch sin mocks globales", async () => {
  const calls: string[] = []
  const hooks = await createJudgmentMemory(createContext(rootDir), {
    semanticSearch: async () => {
      calls.push("semanticSearch")
      return {
        available: true,
        hits: [
          {
            id: "injected-hit",
            score: 0.99,
            payload: { final: "approve", task: "injected task", lesson: "injected lesson" },
          },
        ],
      }
    },
  })

  await hooks["chat.message"](
    { sessionID: "session-injected" },
    { parts: [{ type: "text", text: "judgment day for injected dependency" }] },
  )
  const output = { system: ["base"] }
  await hooks["experimental.chat.system.transform"](
    { sessionID: "session-injected" },
    output,
  )

  expect(calls).toEqual(["semanticSearch"])
  expect(output.system[0]).toContain("injected task")
  expect(services.requests).toHaveLength(0)
})

test("chat.message real: recall se guarda y luego se inyecta una sola vez", async () => {
  const hooks = await JudgmentMemory(createContext(rootDir))
  const input = { sessionID: "session-recall" }
  const message = {
    parts: [
      { type: "text", text: "Let's do judgment day on the auth flow" },
    ],
  }

  await hooks["chat.message"](input, message)

  const transformed = { system: ["base system prompt"], context: [] }
  await hooks["experimental.chat.system.transform"](input, transformed)

  expect(transformed.system[0]).toContain("Judgment Day Memory Bridge")
  expect(transformed.system[0]).toContain("previous auth review")
  expect(transformed.system[0]).toContain("check token refresh before retry")

  // El recall es consumible: la siguiente transformación no debe repetirlo.
  const transformedAgain = { system: ["base system prompt"] }
  await hooks["experimental.chat.system.transform"](input, transformedAgain)
  expect(transformedAgain.system[0]).not.toContain("previous auth review")

  expect(lastRequest("/api/embed")).toBeDefined()
  expect(lastRequest("/points/search")).toBeDefined()
})

test("chat.message real: no llama servicios externos sin keyword", async () => {
  const hooks = await JudgmentMemory(createContext(rootDir))

  await hooks["chat.message"](
    { sessionID: "session-no-recall" },
    { parts: [{ type: "text", text: "A regular conversation about code" }] },
  )

  expect(services.requests).toHaveLength(0)
})

test("tool.execute.after real: captura Task, persiste en SQLite e indexa en Qdrant", async () => {
  const hooks = await JudgmentMemory(createContext(rootDir))
  const output = [
    "Fixing login bug",
    "Target: auth flow",
    "Lesson: check token refresh",
    "JUDGMENT: APPROVED ✅",
  ].join("\n")

  await hooks["tool.execute.after"](
    {
      sessionID: "session-capture",
      tool: "Task",
    },
    output,
  )

  const rows = dbRows()
  expect(rows).toHaveLength(1)
  expect(rows[0].project).toBe(projectNameFromContext())
  expect(rows[0].task).toBe("auth flow")
  expect(rows[0].final).toBe("approve")
  expect(rows[0].lesson).toBe("check token refresh")

  expect(services.upserts).toHaveLength(1)
  const upsert = services.upserts[0] as {
    points: Array<{ vector: number[]; payload: Record<string, unknown> }>
  }
  expect(upsert.points).toHaveLength(1)
  expect(upsert.points[0].vector).toEqual([0.1, 0.2, 0.3, 0.4])
  expect(upsert.points[0].payload.source).toBe("passive-capture")
  expect(upsert.points[0].payload.task).toBe("auth flow")
})

test("tool.execute.after real: ignora tools distintas de Task y texto sin terminal", async () => {
  const hooks = await JudgmentMemory(createContext(rootDir))

  await hooks["tool.execute.after"](
    { sessionID: "session-other-tool", tool: "Read" },
    "Target: should not be recorded\nJUDGMENT: APPROVED ✅",
  )
  await hooks["tool.execute.after"](
    { sessionID: "session-no-terminal", tool: "Task" },
    "Target: no terminal line",
  )

  expect(dbRows()).toHaveLength(0)
  expect(services.requests).toHaveLength(0)
})

test("tool.execute.after real: ignora las herramientas internas de judgment-memory", async () => {
  const hooks = await JudgmentMemory(createContext(rootDir))

  await hooks["tool.execute.after"](
    { sessionID: "session-internal", tool: "JD_RECORD" },
    "Target: should not be recorded\nJUDGMENT: APPROVED ✅",
  )

  expect(dbRows()).toHaveLength(0)
  expect(services.requests).toHaveLength(0)
})

test("tool.execute.after real: conserva el ledger aunque falle el indexado", async () => {
  services.failEmbeddings = true
  const hooks = await JudgmentMemory(createContext(rootDir))
  const loggedErrors: string[] = []
  const originalConsoleError = console.error
  console.error = (...args: unknown[]) => {
    loggedErrors.push(args.map(String).join(" "))
  }

  try {
    await hooks["tool.execute.after"](
      { sessionID: "session-degraded", tool: "Task" },
      "Target: rate limiter\nLesson: use exponential backoff\nJUDGMENT: ESCALATED ⚠️",
    )
  } finally {
    console.error = originalConsoleError
  }

  const rows = dbRows()
  expect(rows).toHaveLength(1)
  expect(rows[0].task).toBe("rate limiter")
  expect(rows[0].final).toBe("escalated")
  expect(services.upserts).toHaveLength(0)
  expect(loggedErrors.some((line) => line.includes("passive index failed"))).toBe(true)
})

test("experimental.chat.system.transform real: agrega el protocolo incluso sin recall", async () => {
  const hooks = await JudgmentMemory(createContext(rootDir))
  const output = { system: [], context: [] }

  await hooks["experimental.chat.system.transform"](
    { sessionID: "session-system" },
    output,
  )

  expect(output.system).toHaveLength(1)
  expect(output.system[0]).toContain("Judgment Day Memory Bridge")
  expect(output.system[0]).toContain("jd_recall")
})

test("JD_TRIGGER_RE real: detecta las variantes judgment day, dual review, adversarial review y juzgar", () => {
  expect(JD_TRIGGER_RE.test("Let's do judgment day on this")).toBe(true)
  expect(JD_TRIGGER_RE.test("Run a dual review")).toBe(true)
  expect(JD_TRIGGER_RE.test("adversarial review needed")).toBe(true)
  expect(JD_TRIGGER_RE.test("juzgar este caso")).toBe(true)
})

test("JD_TRIGGER_RE real: rechaza mensajes sin keywords", () => {
  expect(JD_TRIGGER_RE.test("regular conversation without a review trigger")).toBe(false)
})

test("JD_TRIGGER_RE real: es case-insensitive", () => {
  expect(JD_TRIGGER_RE.test("JUDGMENT DAY")).toBe(true)
  expect(JD_TRIGGER_RE.test("Juzgar este caso")).toBe(true)
})

test("JD_TERMINAL_RE real: acepta APPROVED y ESCALATED, pero rechaza REJECTED", () => {
  expect(JD_TERMINAL_RE.test("JUDGMENT: APPROVED ✅")).toBe(true)
  expect(JD_TERMINAL_RE.test("JUDGMENT: ESCALATED ⚠️")).toBe(true)
  expect(JD_TERMINAL_RE.test("JUDGMENT: REJECTED ❌")).toBe(false)
  expect(JD_TERMINAL_RE.test("judgment: approved")).toBe(true)
})

test("JUDGMENT_MEMORY_TOOLS real: contiene las cuatro tools protegidas", () => {
  expect(JUDGMENT_MEMORY_TOOLS.size).toBe(4)
  expect(JUDGMENT_MEMORY_TOOLS.has("jd_recall")).toBe(true)
  expect(JUDGMENT_MEMORY_TOOLS.has("jd_record")).toBe(true)
  expect(JUDGMENT_MEMORY_TOOLS.has("jd_history")).toBe(true)
  expect(JUDGMENT_MEMORY_TOOLS.has("jd_stats")).toBe(true)
})

test("parsePassiveRecord real: reconoce Issue y Learned como aliases", () => {
  const result = parsePassiveRecord(
    "Issue: memory leak\nJUDGMENT: APPROVED ✅\nLearned: cleanup event listeners",
    "alias-session",
    "alias-project",
  )

  expect(result?.task).toBe("memory leak")
  expect(result?.lesson).toBe("cleanup event listeners")
  expect(result?.final).toBe("approve")
})

test("chat.message real: filtra hits por RECALL_SCORE_THRESHOLD", async () => {
  const calls: string[] = []
  const hooks = await createJudgmentMemory(createContext(rootDir), {
    semanticSearch: async () => {
      calls.push("semanticSearch")
      return {
        available: true,
        hits: [
          { score: 0.3, payload: { task: "low", lesson: "ignore low score" } },
          { score: 0.6, payload: { task: "medium", lesson: "keep medium score" } },
          { score: 0.8, payload: { task: "high", lesson: "keep high score" } },
        ],
      }
    },
  })

  await hooks["chat.message"](
    { sessionID: "session-threshold" },
    { parts: [{ type: "text", text: "judgment day threshold review" }] },
  )
  const transformed = { system: ["base"] }
  await hooks["experimental.chat.system.transform"](
    { sessionID: "session-threshold" },
    transformed,
  )

  expect(RECALL_SCORE_THRESHOLD).toBe(0.5)
  expect(calls).toEqual(["semanticSearch"])
  expect(transformed.system[0]).toContain("medium")
  expect(transformed.system[0]).toContain("high")
  expect(transformed.system[0]).not.toContain("ignore low score")
})

test("chat.message real: no inyecta recall cuando todos los hits están debajo del threshold", async () => {
  const hooks = await createJudgmentMemory(createContext(rootDir), {
    semanticSearch: async () => ({
      available: true,
      hits: [
        { score: 0.1, payload: { task: "low only", lesson: "not relevant" } },
      ],
    }),
  })

  await hooks["chat.message"](
    { sessionID: "session-low-only" },
    { parts: [{ type: "text", text: "dual review with no useful match" }] },
  )
  const transformed = { system: ["base"] }
  await hooks["experimental.chat.system.transform"](
    { sessionID: "session-low-only" },
    transformed,
  )

  expect(transformed.system[0]).toContain("Judgment Day Memory Bridge")
  expect(transformed.system[0]).not.toContain("TONYMEM RECALL")
  expect(transformed.system[0]).not.toContain("low only")
})

test("chat.message real: concatena múltiples partes textuales y activa recall una sola vez", async () => {
  const calls: string[] = []
  const hooks = await createJudgmentMemory(createContext(rootDir), {
    semanticSearch: async (_project: string, content: string) => {
      calls.push(content)
      return {
        available: true,
        hits: [
          {
            score: 0.9,
            payload: { task: "multipart review", lesson: "preserve all text parts" },
          },
        ],
      }
    },
  })

  await hooks["chat.message"](
    { sessionID: "session-multipart" },
    {
      parts: [
        { type: "image", data: "ignored" },
        { type: "text", text: "dual" },
        { type: "text", text: "review this multipart input" },
      ],
    },
  )
  const transformed = { system: ["base"] }
  await hooks["experimental.chat.system.transform"](
    { sessionID: "session-multipart" },
    transformed,
  )

  expect(calls).toHaveLength(1)
  expect(calls[0]).toBe("dual\nreview this multipart input")
  expect(transformed.system[0]).toContain("multipart review")
})

test("tool.execute.after real: acepta output objeto serializable y conserva el ledger", async () => {
  const hooks = await JudgmentMemory(createContext(rootDir))

  await hooks["tool.execute.after"](
    { sessionID: "session-object-output", tool: "Task" },
    {
      Target: "object output target",
      Lesson: "object output lesson",
      JUDGMENT: "APPROVED",
    },
  )

  const rows = dbRows()
  expect(rows).toHaveLength(1)
  expect(rows[0].final).toBe("approve")
  expect(String(rows[0].task)).toContain("object output target")
})

test("tool.execute.after real: ignora todas las tools internas y outputs vacíos", async () => {
  const hooks = await JudgmentMemory(createContext(rootDir))
  const terminalOutput = "Target: internal should be ignored\nJUDGMENT: APPROVED ✅"

  for (const tool of JUDGMENT_MEMORY_TOOLS) {
    await hooks["tool.execute.after"](
      { sessionID: `session-${tool}`, tool },
      terminalOutput,
    )
  }
  await hooks["tool.execute.after"](
    { sessionID: "session-empty-task", tool: "Task" },
    "",
  )

  expect(dbRows()).toHaveLength(0)
  expect(services.requests).toHaveLength(0)
})

test("chat.message real: no inyecta recall cuando semanticSearch no está disponible", async () => {
  const hooks = await createJudgmentMemory(createContext(rootDir), {
    semanticSearch: async () => ({ available: false, hits: [] }),
  })

  await hooks["chat.message"](
    { sessionID: "session-unavailable" },
    { parts: [{ type: "text", text: "adversarial review unavailable backend" }] },
  )
  const transformed = { system: ["base"] }
  await hooks["experimental.chat.system.transform"](
    { sessionID: "session-unavailable" },
    transformed,
  )

  expect(transformed.system[0]).toContain("Judgment Day Memory Bridge")
  expect(transformed.system[0]).not.toContain("TONYMEM RECALL")
})

test("chat.message real: no inyecta recall cuando semanticSearch devuelve hits vacíos", async () => {
  const hooks = await createJudgmentMemory(createContext(rootDir), {
    semanticSearch: async () => ({ available: true, hits: [] }),
  })

  await hooks["chat.message"](
    { sessionID: "session-empty-hits" },
    { parts: [{ type: "text", text: "juzgar este caso sin historial" }] },
  )
  const transformed = { system: ["base"] }
  await hooks["experimental.chat.system.transform"](
    { sessionID: "session-empty-hits" },
    transformed,
  )

  expect(transformed.system[0]).toContain("Judgment Day Memory Bridge")
  expect(transformed.system[0]).not.toContain("TONYMEM RECALL")
})

test("experimental.chat.system.transform real: conserva instrucciones existentes y agrega el bridge", async () => {
  const hooks = await JudgmentMemory(createContext(rootDir))
  const output = { system: ["existing instructions"], context: [] }

  await hooks["experimental.chat.system.transform"](
    { sessionID: "session-existing-system" },
    output,
  )

  expect(output.system).toHaveLength(1)
  expect(output.system[0]).toContain("existing instructions")
  expect(output.system[0]).toContain("Judgment Day Memory Bridge")
})
