/**
 * model-variants
 * Exports per-model variant (effort level) data for gentle-ai.
 *
 * On OpenCode startup, fetches the provider list via the in-process SDK client,
 * extracts variant keys per model, and writes a minimal JSON cache to
 * ~/.gentle-ai/cache/model-variants.json. gentle-ai reads this file
 * to populate the effort level picker without needing a live API connection.
 */

import type { Plugin } from "@opencode-ai/plugin"
import { writeFile, mkdir, rename, rm } from "fs/promises"
import { randomBytes } from "crypto"
import { homedir } from "os"
import path from "path"

const MODEL_VARIANTS_CACHE_FILE = "model-variants.json"
const DEBUG_LOG_PATH = process.env.TONY_DEBUG_LOG ?? path.join(process.cwd(), "tony-debug.log")

function debugLog(message: string, details?: Record<string, unknown>) {
  try {
    const suffix = details ? ` ${JSON.stringify(details)}` : ""
    const line = `[${new Date().toISOString()}] [MODEL_VARIANTS] ${message}${suffix}\n`
    Bun.write(DEBUG_LOG_PATH, line, { create: true, append: true })
  } catch (err) {
    console.error("[model-variants] debug log failed:", err)
  }
}

function isIgnorableFileRace(err: unknown) {
  return typeof err === "object" && err !== null && "code" in err && (err as { code?: string }).code === "ENOENT"
}

async function removeOwnTempFile(tmpPath: string) {
  try {
    await rm(tmpPath, { force: true })
  } catch (err) {
    if (!isIgnorableFileRace(err)) {
      console.error("[model-variants] temp cleanup failed:", err)
    }
  }
}

export const ModelVariantsPlugin: Plugin = async (input) => {
  debugLog("plugin initialized", { directory: input.directory, worktree: input.worktree })

  async function refreshVariantsCache() {
    let tmpPath: string | undefined
    try {
      debugLog("provider.list starting")
      const result = await input.client.provider.list()
      const data = (result as any).data ?? result
      const providerList: any[] = data?.all ?? data?.providers ?? (Array.isArray(data) ? data : [])
      debugLog("provider.list completed", { providers: providerList.length })

      const variants: Record<string, Record<string, string[]>> = {}
      let modelCount = 0
      let variantModelCount = 0
      for (const prov of providerList) {
        for (const [modelId, model] of Object.entries(prov.models ?? {})) {
          modelCount++
          const m = model as any
          if (m.variants && Object.keys(m.variants).length > 0) {
            variantModelCount++
            variants[prov.id] = variants[prov.id] || {}
            variants[prov.id][modelId] = Object.keys(m.variants).sort()
          }
        }
      }
      debugLog("variants extracted", { modelCount, variantModelCount })

      const cacheDir = path.join(homedir(), ".gentle-ai", "cache")
      await mkdir(cacheDir, { recursive: true })

      const finalPath = path.join(cacheDir, MODEL_VARIANTS_CACHE_FILE)
      tmpPath = path.join(cacheDir, `${MODEL_VARIANTS_CACHE_FILE}.${randomBytes(3).toString("hex")}.tmp`)
      debugLog("writing cache", { finalPath, tmpPath })
      await writeFile(tmpPath, JSON.stringify(variants, null, 2))
      await rename(tmpPath, finalPath)
      tmpPath = undefined
      debugLog("cache refresh completed", { finalPath })
    } catch (err) {
      console.error("[model-variants] cache refresh failed:", err)
      debugLog("cache refresh failed", { error: String(err) })
    } finally {
      if (tmpPath) {
        await removeOwnTempFile(tmpPath)
        debugLog("temp cache removed", { tmpPath })
      }
    }
  }

  debugLog("refresh scheduled")
  refreshVariantsCache().catch((err) => {
    console.error("[model-variants] unexpected refresh error:", err)
    debugLog("unexpected refresh error", { error: String(err) })
  })

  return {}
}

export default ModelVariantsPlugin
