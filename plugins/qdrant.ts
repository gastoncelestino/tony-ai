/**
 * qdrant.ts — thin Qdrant + embeddings (llama-server/llama-swap) REST client for OpenCode plugins.
 *
 * Not a Plugin itself — a small library `judgment-memory.ts` (and any
 * future plugin) imports. Mirrors the exact contract `code-index/core.py`
 * and `judgment-memory/ledger.py` already use on the Python side (same
 * collection-naming rule, same point shape, same distance metric), so a
 * point written from Bun and one written from Python are interchangeable —
 * this is a second client for the same store, not a separate one.
 *
 * Uses Bun's built-in `fetch`, no npm install.
 */

// ─── Configuration ───────────────────────────────────────────────────────────
// Same env var names as code-index/core.py and judgment-memory/ledger.py —
// one source of truth across Python and TS callers. TONY_EMBEDDINGS_URL now
// points at llama-swap (default port 8080), which serves the embedding
// models declared in config.yaml the same way it serves chat models.

export const EMBEDDINGS_URL = process.env.TONY_EMBEDDINGS_URL ?? "http://localhost:8080"
export const EMBED_MODEL = process.env.TONY_EMBED_MODEL ?? "nomic-embed-text"
export const QDRANT_URL = process.env.TONY_QDRANT_URL ?? "http://localhost:6333"

// ─── Types ────────────────────────────────────────────────────────────────────

export interface QdrantPoint {
  id: string
  vector: number[]
  payload: Record<string, unknown>
}

export interface QdrantHit {
  id: string
  score: number
  payload: Record<string, unknown>
}

// ─── Embeddings (llama-server, OpenAI-compatible /v1/embeddings) ──────────────

export async function embedTexts(
  texts: string[],
  model: string = EMBED_MODEL,
  baseUrl: string = EMBEDDINGS_URL,
): Promise<number[][]> {
  if (texts.length === 0) return []
  const res = await fetch(`${baseUrl}/v1/embeddings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, input: texts }),
  }).catch((err) => {
    throw new Error(
      `Could not reach llama-server/llama-swap at ${baseUrl} for embeddings (model=${model}): ${err}. ` +
        `Is llama-swap running with '${model}' declared in config.yaml?`,
    )
  })
  if (!res.ok) {
    throw new Error(`llama-server /v1/embeddings failed (${res.status}): ${await res.text()}`)
  }
  // OpenAI-compatible response shape: { data: [{ embedding: [...], index: 0 }, ...] }
  const body = (await res.json()) as { data?: { embedding: number[]; index: number }[] }
  if (!body.data || body.data.length === 0) {
    throw new Error(`llama-server returned no embeddings for model=${model}`)
  }
  return [...body.data].sort((a, b) => a.index - b.index).map((item) => item.embedding)
}

// ─── Qdrant REST ────────────────────────────────────────────────────────────

async function qdrantRequest(
  method: string,
  path: string,
  body: unknown,
  baseUrl: string,
): Promise<any> {
  const res = await fetch(`${baseUrl}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).catch((err) => {
    throw new Error(
      `Could not reach Qdrant at ${baseUrl}${path}: ${err}. Is Qdrant running? ` +
        `(docker run -p 6333:6333 qdrant/qdrant)`,
    )
  })
  const text = await res.text()
  if (!res.ok) {
    throw new Error(`Qdrant ${method} ${path} failed (${res.status}): ${text}`)
  }
  return text ? JSON.parse(text) : {}
}

/** Same naming rule as code-index/core.py's collection_name(), separate
 * prefix so judgment memory never collides with a code-index collection. */
export function collectionName(project: string): string {
  const safe = project.replace(/[^a-zA-Z0-9_-]/g, "-")
  return `jdmem_${safe}`
}

export async function ensureCollection(
  collection: string,
  dim: number,
  baseUrl: string = QDRANT_URL,
): Promise<void> {
  try {
    await qdrantRequest("GET", `/collections/${collection}`, undefined, baseUrl)
    return
  } catch {
    // doesn't exist yet — fall through to create
  }
  await qdrantRequest(
    "PUT",
    `/collections/${collection}`,
    { vectors: { size: dim, distance: "Cosine" } },
    baseUrl,
  )
}

export async function upsertPoints(
  collection: string,
  points: QdrantPoint[],
  baseUrl: string = QDRANT_URL,
): Promise<void> {
  if (points.length === 0) return
  await qdrantRequest("PUT", `/collections/${collection}/points?wait=true`, { points }, baseUrl)
}

export async function searchPoints(
  collection: string,
  vector: number[],
  limit: number = 5,
  baseUrl: string = QDRANT_URL,
): Promise<QdrantHit[]> {
  const result = await qdrantRequest(
    "POST",
    `/collections/${collection}/points/search`,
    { vector, limit, with_payload: true },
    baseUrl,
  )
  return result.result ?? []
}

// ─── Convenience: embed one text + search in one call ──────────────────────

export async function semanticSearch(
  project: string,
  query: string,
  limit: number = 5,
  opts: { embedModel?: string; embeddingsUrl?: string; qdrantUrl?: string } = {},
): Promise<{ available: boolean; error?: string; hits: QdrantHit[] }> {
  const embedModel = opts.embedModel ?? EMBED_MODEL
  const embeddingsUrl = opts.embeddingsUrl ?? EMBEDDINGS_URL
  const qdrantUrl = opts.qdrantUrl ?? QDRANT_URL
  try {
    const [vec] = await embedTexts([query], embedModel, embeddingsUrl)
    const hits = await searchPoints(collectionName(project), vec, limit, qdrantUrl)
    return { available: true, hits }
  } catch (err) {
    // Degrade gracefully — embeddings server/Qdrant being down should never
    // break the agent turn, only skip the recall step (same contract as
    // judgment-memory/ledger.py's recall()).
    return { available: false, error: String(err), hits: [] }
  }
}
