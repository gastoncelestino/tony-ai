/**
 * verify-qdrant.ts — smoke test for plugins/qdrant.ts against REAL local
 * Ollama + Qdrant. Not a mock-based regression test like test_ledger.py —
 * this exists specifically to close the gap that one doesn't cover: the
 * TS/Bun HTTP client was only type-checked (tsc), never executed against
 * anything. This script executes every exported function in qdrant.ts
 * against the real services once, so you get a pass/fail before trusting
 * plugins/judgment-memory.ts inside an actual OpenCode session.
 *
 * Prereqs (see TONY-AI-INSTALL.md section 7 and 10):
 *   - `ollama serve` running, with `ollama pull nomic-embed-text` done
 *   - Qdrant reachable (`docker run -p 6333:6333 qdrant/qdrant`)
 *   - Bun installed (ships with OpenCode's plugin runtime already)
 *
 * Run from the judgment-memory/ directory (or anywhere, paths below are
 * relative to this file):
 *
 *   bun run judgment-memory/scripts/verify-qdrant.ts
 *
 * Uses a throwaway project name (`__verify_qdrant_ts__`) and collection so
 * it never touches real judgment data, and deletes the collection at the
 * end regardless of pass/fail.
 */

import {
  collectionName,
  embedTexts,
  ensureCollection,
  OLLAMA_URL,
  QDRANT_URL,
  searchPoints,
  semanticSearch,
  upsertPoints,
} from "../../plugins/qdrant"

const PROJECT = "__verify_qdrant_ts__"
const COLLECTION = collectionName(PROJECT)

let failures = 0

function assert(cond: boolean, msg: string) {
  if (cond) {
    console.log(`  ok — ${msg}`)
  } else {
    failures++
    console.error(`  FAIL — ${msg}`)
  }
}

async function cleanup() {
  try {
    await fetch(`${QDRANT_URL}/collections/${COLLECTION}`, { method: "DELETE" })
    console.log(`\ncleaned up collection ${COLLECTION}`)
  } catch (err) {
    console.error(`cleanup failed (delete ${COLLECTION} manually if it lingers):`, err)
  }
}

async function main() {
  console.log(`Ollama:  ${OLLAMA_URL}`)
  console.log(`Qdrant:  ${QDRANT_URL}`)
  console.log(`Collection: ${COLLECTION}\n`)

  console.log("--- 1. embedTexts ---")
  const vectors = await embedTexts(["check execution plan before optimization", "missing validation layer"])
  assert(vectors.length === 2, "returned 2 vectors for 2 inputs")
  assert(vectors[0].length > 0 && vectors[0].length === vectors[1].length, "vectors are non-empty and same dimension")
  const dim = vectors[0].length
  console.log(`  embedding dimension: ${dim}`)

  console.log("\n--- 2. ensureCollection ---")
  await ensureCollection(COLLECTION, dim)
  const getRes = await fetch(`${QDRANT_URL}/collections/${COLLECTION}`)
  assert(getRes.ok, "collection exists after ensureCollection")
  // calling it again should be a no-op, not throw
  await ensureCollection(COLLECTION, dim)
  assert(true, "calling ensureCollection twice does not throw")

  console.log("\n--- 3. upsertPoints ---")
  await upsertPoints(COLLECTION, [
    {
      id: "11111111-1111-1111-1111-111111111111",
      vector: vectors[0],
      payload: {
        execution_id: "verify-001",
        task: "optimize query",
        final: "reject",
        lesson: "check execution plan before optimization",
      },
    },
    {
      id: "22222222-2222-2222-2222-222222222222",
      vector: vectors[1],
      payload: {
        execution_id: "verify-002",
        task: "refactor API",
        final: "approve",
        lesson: "missing validation layer",
      },
    },
  ])
  assert(true, "upsert did not throw")

  console.log("\n--- 4. searchPoints ---")
  const hits = await searchPoints(COLLECTION, vectors[0], 5)
  assert(hits.length >= 1, `search returned ${hits.length} hit(s)`)
  assert(
    hits[0]?.payload?.execution_id === "verify-001",
    `top hit is the closest match (verify-001), got ${hits[0]?.payload?.execution_id}`
  )

  console.log("\n--- 5. semanticSearch (embed + search in one call) ---")
  const result = await semanticSearch(PROJECT, "speed up a slow query")
  assert(result.available === true, "semanticSearch reports available=true when services are up")
  assert(result.hits.length >= 1, `semanticSearch returned ${result.hits.length} hit(s)`)

  console.log("\n--- 6. graceful degradation against an unreachable Qdrant ---")
  const deadResult = await semanticSearch(PROJECT, "anything", 5, { qdrantUrl: "http://127.0.0.1:1" })
  assert(deadResult.available === false, "semanticSearch reports available=false, doesn't throw, when Qdrant is down")
  assert(deadResult.hits.length === 0, "hits is empty on failure, not undefined/null")

  console.log(`\n${failures === 0 ? "ALL CHECKS PASSED" : `${failures} CHECK(S) FAILED`}`)
  await cleanup()
  process.exit(failures === 0 ? 0 : 1)
}

main().catch(async (err) => {
  console.error("\nSCRIPT ERRORED (not a normal assertion failure):", err)
  await cleanup()
  process.exit(1)
})
