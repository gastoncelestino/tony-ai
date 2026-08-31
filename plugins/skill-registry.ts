/**
 * skill-registry
 * Refreshes Gentle AI's project skill registry when OpenCode starts.
 *
 * Codex and Claude Code use native startup hooks for the same command. OpenCode
 * loads plugins at startup, so this plugin provides the equivalent behavior
 * without depending on shell interpolation or command-file parse-time cwd.
 */

import type { Plugin } from "@opencode-ai/plugin"
import { execFile } from "child_process"
import { access, appendFile } from "fs/promises"
import { homedir } from "os"
import { join, parse } from "path"
import { promisify } from "util"

const execFileAsync = promisify(execFile)
const appendFileAsync = promisify(appendFile)
const DEBUG_LOG_PATH = process.env.TONY_DEBUG_LOG ?? join(process.cwd(), "tony-debug.log")

async function debugLog(message: string, details?: Record<string, unknown>) {
  try {
    const suffix = details ? ` ${JSON.stringify(details)}` : ""
    await appendFileAsync(DEBUG_LOG_PATH, `[${new Date().toISOString()}] [SKILL_REGISTRY] ${message}${suffix}\n`, "utf8")
  } catch (err) {
    console.error("[skill-registry] debug log failed:", err)
  }
}

const PROJECT_MARKERS = [".git", ".atl", "skills", ".opencode/skills", ".claude/skills", ".gemini/skills", ".cursor/skills", ".github/skills", ".codex/skills", ".qwen/skills", ".kiro/skills", ".openclaw/skills", ".pi/skills", ".agent/skills", ".agents/skills", ".atl/skills", ".hermes/skills"]

async function pathExists(path: string): Promise<boolean> {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

async function isProjectRoot(cwd: string): Promise<boolean> {
  if (!cwd) return false
  if (cwd === parse(cwd).root) return false
  if (cwd === homedir()) return false
  for (const marker of PROJECT_MARKERS) if (await pathExists(join(cwd, ...marker.split("/")))) return true
  return false
}

export const SkillRegistryPlugin: Plugin = async (input) => {
  await debugLog("plugin initialized", { directory: input.directory, worktree: input.worktree })

  async function refreshSkillRegistry() {
    const cwd = input.worktree || input.directory || process.cwd()
    await debugLog("refresh started", { cwd })

    if (!(await isProjectRoot(cwd))) {
      await debugLog("refresh skipped: not a project root", { cwd })
      console.info("[skill-registry] skipping refresh: not a project root:", cwd)
      return
    }

    try {
      await debugLog("executing gentle-ai skill-registry refresh", { cwd })
      const result = await execFileAsync(
        "gentle-ai",
        ["skill-registry", "refresh", "--quiet", "--no-gitignore", "--cwd", cwd],
        { timeout: 30_000 },
      )
      await debugLog("skill registry refresh completed", { cwd, stdoutLength: result.stdout?.length ?? 0, stderrLength: result.stderr?.length ?? 0 })
    } catch (err) {
      await debugLog("skill registry refresh failed", { cwd, error: String(err) })
      console.error("[skill-registry] refresh failed:", err)
    }
  }

  await debugLog("refresh scheduled")
  refreshSkillRegistry().catch(async (err) => {
    console.error("[skill-registry] unexpected refresh error:", err)
    await debugLog("unexpected refresh error", { error: String(err) })
  })

  return {}
}

export default SkillRegistryPlugin
