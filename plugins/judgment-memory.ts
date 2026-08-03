/**
 * judgment-memory.ts — Judgment Day <-> TonyMem Memory Bridge (OpenCode plugin)
 *
 * Closes the loop the user asked for:
 *
 *   Nueva tarea
 *     -> TonyMem Recall           (this plugin, chat.message + system.transform)
 *     -> "Ya vimos un problema parecido"
 *     -> Judgment Day             (skills/judgment-day/SKILL.md, unchanged)
 *     -> Agreement Engine + Ledger (skills/_shared/review-ledger-contract.md, unchanged)
 *     -> jd_record                (judgment-memory/server.py MCP tool, explicit)
 *     -> Qdrant                   (plugins/qdrant.ts)
 *
 * Two complementary write paths, same as TonyMem's own explicit-vs-passive
 * split in plugins/tonymem.ts:
 *   - EXPLICIT: the orchestrator calls `jd_record` (judgment-memory MCP
 *     server) once a lineage reaches a terminal state. This is the
 *     authoritative path — full record, matches schema.json exactly.
 *   - PASSIVE (best-effort): this plugin watches Task tool output for the
 *     Judgment Day Output Contract's terminal line (`JUDGMENT: APPROVED ✅`
 *     / `JUDGMENT: ESCALATED ⚠️`, per judgment-day/SKILL.md) and captures a
 *     lightweight fallback record if the orchestrator forgot to call
 *     jd_record. It only ever fills in what it can parse with confidence —
 *     it does not fabricate judge verdicts or confidence scores it didn't
 *     see in the text.
 *
 * Storage: same SQLite file `judgment-memory/ledger.py` and
 * `judgment-memory/server.py` use (`judgment-memory.db`, WAL mode, same
 * `judgments` table) via `bun:sqlite` — no daemon, no second source of
 * truth, exact same "shared file, shared schema" pattern as
 * tonymem.ts <-> local-memory/server.py.
 *
 * Vector recall/index goes through plugins/qdrant.ts, which talks to the
 * same `jdmem_{project}` Qdrant collection `judgment-memory/ledger.py`
 * writes to — a point written from Python or from here is interchangeable.
 */

import type { Plugin } from "@opencode-ai/plugin"
import { Database } from "bun:sqlite"
import path from "path"
import { fileURLToPath } from "url"
import { collectionName, embedTexts, ensureCollection, semanticSearch, upsertPoints } from "./qdrant"

// ─── Configuration ───────────────────────────────────────────────────────────

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url))
const DB_PATH =
  process.env.JUDGMENT_MEMORY_DB ?? path.join(PLUGIN_DIR, "..", "judgment-memory", "judgment-memory.db")

// Keywords from judgment-day/SKILL.md's own Activation Contract ("judgment
// day, dual review, adversarial review, juzgar") — used only to decide
// when to run a proactive recall, never to gate anything else.
const JD_TRIGGER_RE = /\b(judgment\s*day|dual\s*review|adversarial\s*review|juzgar)\b/i

// Output Contract terminal line, verbatim per judgment-day/SKILL.md.
const JD_TERMINAL_RE = /JUDGMENT:\s*(APPROVED|ESCALATED)/i

const JUDGMENT_MEMORY_TOOLS = new Set(["jd_recall", "jd_record", "jd_history", "jd_stats"])

const RECALL_SCORE_THRESHOLD = parseFloat(
  process.env.TONY_RECALL_SCORE_THRESHOLD ?? "0.5"
)

// Passive capture stats and logging
let passiveCaptureCount = 0
let passiveCaptureErrors = 0
const PASSIVE_CAPTURE_LOG = process.env.JUDGMENT_MEMORY_DEBUG === "1"

const BRIDGE_INSTRUCTIONS = `## Judgment Day Memory Bridge — Protocol

TonyMem's Judgment Day extension persists judgment outcomes so future reviews of
similar targets start with prior context instead of from scratch.

### BEFORE launching Judgment Day (mandatory)

Call \`jd_recall\` with a short description of the target/task before starting
the judge-launch step in judgment-day/SKILL.md. If it returns a close match,
surface its \`lesson\` and \`fix\` to both judges as prior context — it does not
replace their independent read, it informs it.

### AFTER a lineage reaches a terminal state (mandatory)

Once \`review/finalize\` (or the equivalent terminal step) produces \`JUDGMENT:
APPROVED ✅\` or \`JUDGMENT: ESCALATED ⚠️\`, the parent orchestrator — never a
judge, never the fix actor, same rule as review-ledger-contract.md — calls
\`jd_record\` with the full record: execution_id (use the lineageId),
task, judge_a/judge_b verdicts, agreement (confirmed | suspect |
contradiction), final (approve | reject | escalated), fix, and lesson.

The \`lesson\` field is what future \`jd_recall\` calls match against — write it
as a standalone, reusable takeaway ("check execution plan before
optimization"), not a restatement of the task.

This plugin also does best-effort passive capture from Task tool output as a
safety net, but it cannot see judge verdicts or confidence — \`jd_record\` is
the only path that produces a complete record.
`

// ─── SQLite ──────────────────────────────────────────────────────────────────
// Same schema as judgment-memory/ledger.py's init_db(). Both processes use
// IF NOT EXISTS so there's no creation race.

let db: Database | null = null

function getDb(): Database | null {
  if (db) return db
  try {
    const instance = new Database(DB_PATH, { create: true })
    instance.exec("PRAGMA journal_mode = WAL;")
    instance.exec(`
      CREATE TABLE IF NOT EXISTS judgments (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          execution_id      TEXT NOT NULL,
          project           TEXT NOT NULL DEFAULT 'default',
          task              TEXT NOT NULL,
          judge_a_model     TEXT,
          judge_a_decision  TEXT,
          judge_b_model     TEXT,
          judge_b_decision  TEXT,
          agreement         TEXT,
          winner            TEXT,
          confidence        REAL,
          final             TEXT NOT NULL,
          fix               TEXT,
          lesson            TEXT,
          source_lineage_id TEXT,
          point_id          TEXT,
          created_at        TEXT NOT NULL
      );
      CREATE UNIQUE INDEX IF NOT EXISTS idx_project_execution
          ON judgments(project, execution_id);
      CREATE INDEX IF NOT EXISTS idx_judgments_project
          ON judgments(project, created_at DESC);
    `)
    db = instance
    return db
  } catch (err) {
    console.error("[judgment-memory] failed to open DB:", err)
    return null
  }
}

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d+Z$/, "Z")
}

interface PassiveRecord {
  executionId: string
  project: string
  task: string
  final: "approve" | "reject" | "escalated"
  lesson?: string
}

/** Insert-or-update by (project, execution_id) — mirrors
 * judgment-memory/ledger.py's save_judgment() upsert rule exactly, since
 * both processes read/write the same rows. */
function upsertJudgment(rec: PassiveRecord, pointId: string | null): void {
  const conn = getDb()
  if (!conn) return
  try {
    const ts = nowIso()
    const existing = conn
      .query("SELECT id FROM judgments WHERE project = ? AND execution_id = ?")
      .get(rec.project, rec.executionId) as { id: number } | null

    if (existing) {
      conn.run(
        "UPDATE judgments SET task=?, final=?, lesson=?, point_id=COALESCE(?, point_id), created_at=? WHERE id=?",
        [rec.task, rec.final, rec.lesson ?? null, pointId, ts, existing.id]
      )
    } else {
      conn.run(
        `INSERT INTO judgments
          (execution_id, project, task, final, lesson, point_id, created_at)
         VALUES (?,?,?,?,?,?,?)`,
        [rec.executionId, rec.project, rec.task, rec.final, rec.lesson ?? null, pointId, ts]
      )
    }
  } catch (err) {
    console.error("[judgment-memory] passive upsert failed:", err)
  }
}

// ─── Best-effort parsing of Judgment Day output ─────────────────────────────
// Deliberately conservative: only extracts fields the Output Contract in
// judgment-day/SKILL.md guarantees are present in some form. Never invents
// judge verdicts, confidence, or agreement — those only exist in the full
// record jd_record receives from the orchestrator.
// Robust parsing with multiple patterns
function parsePassiveRecord(text: string, sessionId: string, project: string): PassiveRecord | null {
  const terminalMatch = text.match(JD_TERMINAL_RE)
  if (!terminalMatch) return null

  const final = terminalMatch[1].toUpperCase() === "APPROVED" ? "approve" : "escalated"

  // === ROBUST TASK EXTRACTION (NEW) ===
  const targetPatterns = [
    /(?:target(?: identity)?)\s*[:\-]\s*(.+)/i,
    /(?:target|issue|task|bug)\s*[:\-]\s*(.+)/i,
    /(?:reviewing|review)\s*["']?([^"'\n]+)["']?/i,
  ]
  let task: string | null = null
  for (const pattern of targetPatterns) {
    const match = text.match(pattern)
    if (match && match[1]) {
      task = match[1].trim().slice(0, 200)
      break
    }
  }
  if (!task) {
    const lines = text.split("\n").filter(l => l.trim() && !JD_TERMINAL_RE.test(l))
    task = lines.length > 0 ? lines[0].trim().slice(0, 200) : "unknown task"
  }
  if (!task || task.trim().length === 0) {
    if (PASSIVE_CAPTURE_LOG) {
      console.error("[judgment-memory] passive capture: task extraction failed, skipping")
    }
    passiveCaptureErrors++
    return null
  }

  // === ROBUST LESSON EXTRACTION (NEW) ===
  const lessonPatterns = [
    /(?:lesson|learned|takeaway|key takeaway)\s*[:\-]\s*(.+)/i,
    /(?:key insight|insight)\s*[:\-]\s*(.+)/i,
  ]
  let lesson: string | undefined
  for (const pattern of lessonPatterns) {
    const match = text.match(pattern)
    if (match && match[1]) {
      lesson = match[1].trim().slice(0, 500)
      break
    }
  }

  return {
    executionId: `passive/${sessionId}/${Date.now()}`,
    project,
    task,
    final,
    lesson,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function extractProjectName(directory: string): string {
  try {
    const result = Bun.spawnSync(["git", "-C", directory, "remote", "get-url", "origin"])
    if (result.exitCode === 0) {
      const url = result.stdout?.toString().trim()
      if (url) {
        const name = url.replace(/\.git$/, "").split(/[/:]/).pop()
        if (name) return name
      }
    }
  } catch {}
  try {
    const result = Bun.spawnSync(["git", "-C", directory, "rev-parse", "--show-toplevel"])
    if (result.exitCode === 0) {
      const root = result.stdout?.toString().trim()
      if (root) return root.split("/").pop() ?? "unknown"
    }
  } catch {}
  return directory.split("/").pop() ?? "unknown"
}

// ─── Plugin Export ───────────────────────────────────────────────────────────

export const JudgmentMemory: Plugin = async (ctx) => {
  const project = extractProjectName(ctx.directory)

  // sessionID -> formatted recall block, consumed once by the next
  // experimental.chat.system.transform call for that session, then cleared.
  // Bridges chat.message (sees the user's text) and system.transform
  // (builds the system prompt) for the same turn — same pattern tonymem.ts
  // uses for its save nudge.
  const pendingRecall = new Map<string, string>()

  getDb()

  return {
    // ─── Proactive recall: user mentions Judgment Day ──────────────────
    "chat.message": async (input, output) => {
      const sessionId = input.sessionID
      const content = output.parts
        .filter((p) => p.type === "text")
        .map((p) => (p as any).text ?? "")
        .join("\n")
        .trim()

      if (!content || !JD_TRIGGER_RE.test(content)) return

      // Use configurable threshold
      const result = await semanticSearch(project, content, 3)
      if (!result.available || result.hits.length === 0) return

      const lines = result.hits
        .filter((h) => (h.score ?? 0) > RECALL_SCORE_THRESHOLD)
        .map((h) => {
          const p = h.payload as Record<string, any>
          return `- [${p.final ?? "?"}] ${p.task ?? "?"} — lesson: ${p.lesson ?? "(none)"}${p.fix ? `, fix: ${p.fix}` : ""}`
        })
      if (lines.length === 0) return

      pendingRecall.set(
        sessionId,
        `TONYMEM RECALL (Judgment Day): found ${lines.length} prior judgment(s) on similar targets:\n${lines.join("\n")}\n` +
          `Consider this context before launching judges — it does not replace an independent read.`
      )
    },

    // ─── Passive capture: watch Task output for the terminal line ─────
    "tool.execute.after": async (input, output) => {
      if (JUDGMENT_MEMORY_TOOLS.has(input.tool.toLowerCase())) return
      if (input.tool !== "Task" || !output) return

      const sessionId = input.sessionID
      const text = typeof output === "string" ? output : JSON.stringify(output)
      if (!JD_TERMINAL_RE.test(text)) return

      const rec = parsePassiveRecord(text, sessionId ?? "unknown", project)
      if (!rec) return

      // Logging
      if (PASSIVE_CAPTURE_LOG) {
		console.error(`[judgment-memory] passive capture: ${rec.final} for task "${rec.task.slice(0, 50)}..."`)
	  }
	  upsertJudgment(rec, null)
	  passiveCaptureCount++

      try {
        const [vec] = await embedTexts([`task: ${rec.task}\noutcome: ${rec.final}\nlesson: ${rec.lesson ?? ""}`])
        const coll = collectionName(rec.project)
        await ensureCollection(coll, vec.length)
        await upsertPoints(coll, [
          {
            id: `passive-${rec.executionId}`,
            vector: vec,
            payload: { ...rec, execution_id: rec.executionId, source: "passive-capture" },
          },
        ])
        if (PASSIVE_CAPTURE_LOG) {
          console.error("[judgment-memory] passive capture: indexed to Qdrant")
        }
      } catch (err) {
        console.error("[judgment-memory] passive index failed (ledger write still succeeded):", err)
        passiveCaptureErrors++
      }
    },

    // ─── System prompt: protocol instructions + pending recall ────────
    "experimental.chat.system.transform": async (input, output) => {
      const block = BRIDGE_INSTRUCTIONS
      if (output.system.length > 0) {
        output.system[output.system.length - 1] += "\n\n" + block
      } else {
        output.system.push(block)
      }

      // Log stats
      if (PASSIVE_CAPTURE_LOG && passiveCaptureCount > 0) {
		output.system[output.system.length - 1] +=
		  `\n\n[judgment-memory stats] passive captures: ${passiveCaptureCount}, errors: ${passiveCaptureErrors}`
	  }

      const sessionID: string = input.sessionID ?? ""
      const recall = pendingRecall.get(sessionID)
      if (recall) {
        output.system[output.system.length - 1] += "\n\n" + recall
        pendingRecall.delete(sessionID)
      }
    },
  }
}

export default JudgmentMemory

// Export for tests
export {
  parsePassiveRecord,
  upsertJudgment,
  extractProjectName,
  JD_TRIGGER_RE,
  JD_TERMINAL_RE
}