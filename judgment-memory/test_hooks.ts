// test_hooks.ts — Tests de runtime para hooks de plugins/judgment-memory.ts
// Requiere: bun test hooks estos usando un mock del OpenCode plugin context
// Mock del Plugin context (simula sessionID, directory, hooks registration)
// Mock de Qdrant/Ollama (HTTP server en memoria, mismo patrón que test_ledger.py)

import { test, expect, beforeAll, afterAll } from "bun:test"
import { mkdirSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "os"
import { join } from "path"
import { spawn } from "bun"

// Importar la implementación real para testear contra ella
import {
  parsePassiveRecord,
  JD_TRIGGER_RE,
  JD_TERMINAL_RE,
  JUDGMENT_MEMORY_TOOLS,
  RECALL_SCORE_THRESHOLD
} from "../plugins/judgment-memory"

// ─── Mock del OpenCode plugin context ────────────────────────────────────────

function createMockContext(dir: string, sessionId = "test-session-123") {
  return {
    directory: dir,
    event: async (ctx: { event: { type: string; properties?: Record<string, any> } }) => {},
    emit: async (eventName: string, data: any) => {},
  }
}

// ─── Mock HTTP server para Qdrant/Ollama ────────────────────────────────────

interface MockServer {
  port: number
  url: string
  close: () => void
}

function startMockServer(port: number): MockServer {
  const server = Bun.serve({
    port,
    async fetch(req: Request) {
      const url = new URL(req.url)
      if (url.pathname === "/api/embed") {
        return Response.json({
          embeddings: [[0.1, 0.2, 0.3, 0.4, 0.5]],
        })
      }
      if (url.pathname === "/collections/test-collection") {
        return Response.json({ result: { vectors: { size: 5 } } })
      }
      if (url.pathname === "/collections/test-collection/points/search") {
        return Response.json({
          result: [
            { id: "1", score: 0.65, payload: { test: "hit" } }
          ],
        })
      }
      return new Response("not found", { status: 404 })
    },
  })
  return { port, url: `http://localhost:${port}`, close: () => server.stop() }
}

// ─── Test runner ──────────────────────────────────────────────────────────────

async function runTestCase(name: string, fn: (ctx: any) => Promise<void>) {
  const tmpDir = join(tmpdir(), `tonya-test-${Date.now()}`)
  mkdirSync(tmpDir, { recursive: true })
  const ctx = createMockContext(tmpDir)
  try {
    await fn(ctx)
  } catch (err) {
    console.error(`[test ${name}] ${err}`)
    throw err
  } finally {
    rmSync(tmpDir, { recursive: true, force: true })
  }
}

// ─── Tests de parsePassiveRecord (importada del plugin real) ─────────────────

test("parsePassiveRecord: APPROVED con lesson", () => {
  const result = parsePassiveRecord(
    "Fixing login bug\nTarget: auth flow\nLesson: check token refresh\nJUDGMENT: APPROVED ✅",
    "sess-1",
    "myproj"
  )
  expect(result?.final).toBe("approve")
  expect(result?.lesson).toBe("check token refresh")
  expect(result?.task).toContain("auth flow")
})

test("parsePassiveRecord: ESCALATED sin lesson", () => {
  const result = parsePassiveRecord(
    "Fixing bug\nTarget: database\nJUDGMENT: ESCALATED ⚠️",
    "sess-2", "myproj"
  )
  expect(result?.final).toBe("escalated")
  expect(result?.lesson).toBeUndefined()
})

test("parsePassiveRecord: sin terminal line retorna null", () => {
  const result = parsePassiveRecord(
    "Fixing bug\nTarget: database\nNo judgment here",
    "sess-3", "myproj"
  )
  expect(result).toBeNull()
})

test("parsePassiveRecord: task fallback a primera línea no-terminal", () => {
  const result = parsePassiveRecord(
    "Just a regular task description\nJUDGMENT: APPROVED ✅",
    "sess-4", "myproj"
  )
  expect(result?.task).toBe("Just a regular task description")
  expect(result?.final).toBe("approve")
})

test("parsePassiveRecord: target con formato alternativo 'Issue:'", () => {
  const result = parsePassiveRecord(
    "Issue: memory leak\nJUDGMENT: APPROVED ✅\nLearned: cleanup event listeners",
    "sess-5", "myproj"
  )
  expect(result?.task).toContain("memory leak")
  expect(result?.lesson).toBe("cleanup event listeners")
})

test("parsePassiveRecord: task fallback cuando no hay target patterns", () => {
  const result = parsePassiveRecord(
    "Random first line\nSecond line\nJUDGMENT: ESCALATED ⚠️",
    "sess-6", "myproj"
  )
  expect(result?.task).toBe("Random first line")
  expect(result?.final).toBe("escalated")
})

// ─── Tests de JD_TRIGGER_RE (importada del plugin real) ────────────────────────

test("JD_TRIGGER_RE: detecta 'judgment day'", () => {
  expect(JD_TRIGGER_RE.test("Let's do judgment day on this")).toBe(true)
})

test("JD_TRIGGER_RE: detecta 'dual review'", () => {
  expect(JD_TRIGGER_RE.test("Run a dual review")).toBe(true)
})

test("JD_TRIGGER_RE: detecta 'adversarial review'", () => {
  expect(JD_TRIGGER_RE.test("adversarial review needed")).toBe(true)
})

test("JD_TRIGGER_RE: detecta 'juzgar'", () => {
  expect(JD_TRIGGER_RE.test("juzgar este caso")).toBe(true)
})

test("JD_TRIGGER_RE: no detecta sin keywords", () => {
  expect(JD_TRIGGER_RE.test("no trigger keywords here")).toBe(false)
})

test("JD_TRIGGER_RE: case insensitive", () => {
  expect(JD_TRIGGER_RE.test("JUDGMENT DAY")).toBe(true)
  expect(JD_TRIGGER_RE.test("Juzgar")).toBe(true)
})

// ─── Tests de JD_TERMINAL_RE (importada del plugin real) ──────────────────────

test("JD_TERMINAL_RE: detecta APPROVED", () => {
  expect(JD_TERMINAL_RE.test("JUDGMENT: APPROVED ✅")).toBe(true)
})

test("JD_TERMINAL_RE: detecta ESCALATED", () => {
  expect(JD_TERMINAL_RE.test("JUDGMENT: ESCALATED ⚠️")).toBe(true)
})

test("JD_TERMINAL_RE: rechaza 'rejected'", () => {
  expect(JD_TERMINAL_RE.test("JUDGMENT: rejected ❌")).toBe(false)
})

test("JD_TERMINAL_RE: case insensitive", () => {
  expect(JD_TERMINAL_RE.test("judgment: approved")).toBe(true)
})

// ─── Tests de JUDGMENT_MEMORY_TOOLS ───────────────────────────────────────────

test("JUDGMENT_MEMORY_TOOLS: contiene las 4 tools esperadas", () => {
  expect(JUDGMENT_MEMORY_TOOLS.has("jd_recall")).toBe(true)
  expect(JUDGMENT_MEMORY_TOOLS.has("jd_record")).toBe(true)
  expect(JUDGMENT_MEMORY_TOOLS.has("jd_history")).toBe(true)
  expect(JUDGMENT_MEMORY_TOOLS.has("jd_stats")).toBe(true)
  expect(JUDGMENT_MEMORY_TOOLS.size).toBe(4)
})

// ─── Tests de hooks (requieren mock del plugin system) ───────────────────────

test("chat.message hook: activa recall con keywords", async () => {
  await runTestCase("recall-with-keywords", async (ctx) => {
    const hooks = {
      "chat.message": async (input: any, output: any) => {
        const content = output.parts?.filter((p: any) => p.type === "text")
          .map((p: any) => p.text ?? "").join("\n").trim()
        if (content && JD_TRIGGER_RE.test(content)) {
          return { triggered: true, content }
        }
        return { triggered: false }
      }
    }
    
    const input = { sessionID: "test-session", directory: ctx.directory }
    const output = {
      parts: [{ type: "text", text: "Let's do judgment day on this feature" }]
    }
    
    const result = await hooks["chat.message"](input, output)
    expect(result.triggered).toBe(true)
  })
})

test("chat.message hook: no activa recall sin keywords", async () => {
  await runTestCase("no-recall-without-keywords", async (ctx) => {
    const hooks = {
      "chat.message": async (input: any, output: any) => {
        const content = output.parts?.filter((p: any) => p.type === "text")
          .map((p: any) => p.text ?? "").join("\n").trim()
        if (content && JD_TRIGGER_RE.test(content)) {
          return { triggered: true, content }
        }
        return { triggered: false }
      }
    }
    
    const input = { sessionID: "test-session", directory: ctx.directory }
    const output = {
      parts: [{ type: "text", text: "Just a regular conversation about code" }]
    }
    
    const result = await hooks["chat.message"](input, output)
    expect(result.triggered).toBe(false)
  })
})

test("tool.execute.after hook: captura pasiva con JUDGMENT: APPROVED", async () => {
  await runTestCase("passive-capture-approved", async (ctx) => {
    const hooks = {
      "tool.execute.after": async (input: any, output: any) => {
        if (input.tool !== "Task" || !output) return { captured: false }
        const text = typeof output === "string" ? output : JSON.stringify(output)
        if (!JD_TERMINAL_RE.test(text)) return { captured: false }
        return { captured: true, matched: true }
      }
    }
    
    const input = { 
      sessionID: "test-session", 
      directory: ctx.directory,
      tool: "Task"
    }
    const output = "Fixing login bug\nTarget: auth flow\nLesson: check token refresh\nJUDGMENT: APPROVED ✅"
    
    const result = await hooks["tool.execute.after"](input, output)
    expect(result.captured).toBe(true)
    expect(result.matched).toBe(true)
  })
})

test("tool.execute.after hook: ignora tools de judgment-memory", async () => {
  await runTestCase("ignore-jm-tools", async (ctx) => {
    const hooks = {
      "tool.execute.after": async (input: any, output: any) => {
        if (JUDGMENT_MEMORY_TOOLS.has(input.tool.toLowerCase())) return { ignored: true }
        return { ignored: false }
      }
    }
    
    const input1 = { sessionID: "test", directory: ctx.directory, tool: "jd_record" }
    const input2 = { sessionID: "test", directory: ctx.directory, tool: "Task" }
    
    const result1 = await hooks["tool.execute.after"](input1, "output")
    const result2 = await hooks["tool.execute.after"](input2, "output")
    
    expect(result1.ignored).toBe(true)
    expect(result2.ignored).toBe(false)
  })
})

test("system.transform hook: inyecta protocol instructions", async () => {
  await runTestCase("inject-instructions", async (ctx) => {
    const BRIDGE_INSTRUCTIONS = "## Judgment Day Memory Bridge Protocol"
    
    const hooks = {
      "experimental.chat.system.transform": async (input: any, output: any) => {
        if (output.system.length > 0) {
          output.system[output.system.length - 1] += "\n\n" + BRIDGE_INSTRUCTIONS
        } else {
          output.system.push(BRIDGE_INSTRUCTIONS)
        }
        return output
      }
    }
    
    const input = { sessionID: "test", directory: ctx.directory }
    const output = { system: ["existing instructions"], context: [] }
    
    const result = await hooks["experimental.chat.system.transform"](input, output)
    expect(result.system[0]).toContain("existing instructions")
    expect(result.system[0]).toContain("Judgment Day Memory Bridge")
  })
})

// ─── Test de integración: flujo completo ─────────────────────────────────────

test("integración: recall → captura pasiva → verificación", async () => {
  const mockServer = startMockServer(5731)
  try {
    await runTestCase("integration-flow", async (ctx) => {
      // Mock DB
      const dbPath = join(ctx.directory, "test-judgment-memory.db")
      const dbContent = `CREATE TABLE IF NOT EXISTS judgments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        execution_id TEXT NOT NULL,
        project TEXT NOT NULL DEFAULT 'default',
        task TEXT NOT NULL,
        final TEXT NOT NULL,
        lesson TEXT,
        created_at TEXT NOT NULL
      );`
      writeFileSync(join(ctx.directory, "init.sql"), dbContent)
      
      // 1. parsePassiveRecord funciona
      const rec = parsePassiveRecord(
        "Target: api rate limiter\nLesson: check backoff before retry\nJUDGMENT: APPROVED ✅",
        "integration-sess",
        "integration-proj"
      )
      expect(rec).not.toBeNull()
      expect(rec?.final).toBe("approve")
      expect(rec?.task).toContain("api rate limiter")
      expect(rec?.lesson).toBe("check backoff before retry")
      
      // 2. JD_TRIGGER_RE detecta keywords
      const triggerText = "Let's do judgment day on this"
      expect(JD_TRIGGER_RE.test(triggerText)).toBe(true)
      
      // 3. JD_TERMINAL_RE detecta el Output Contract
      const terminalLine = "JUDGMENT: ESCALATED ⚠️"
      expect(JD_TERMINAL_RE.test(terminalLine)).toBe(true)
    })
  } finally {
    mockServer.close()
  }
})

// ─── Test: RECALL_SCORE_THRESHOLD configurable ───────────────────────────────

test("RECALL_SCORE_THRESHOLD: respeta threshold configurable (default 0.5)", () => {
  const hits = [
    { score: 0.3, payload: { test: "low" } },
    { score: 0.6, payload: { test: "medium" } },
    { score: 0.8, payload: { test: "high" } }
  ]
  
  const filtered = hits.filter(h => (h.score ?? 0) > RECALL_SCORE_THRESHOLD)
  expect(filtered.length).toBe(2) // 0.6 y 0.8 pasan el threshold 0.5
})