import { serve } from "bun"

export interface MockServices {
  ollamaUrl: string
  qdrantUrl: string
  stop: () => Promise<void>
  lastEmbed: () => { model: string; input: string[] } | null
  lastQdrantUpsert: () => { collection: string; points: any[] } | null
  lastQdrantSearch: () => { collection: string; vector: number[] } | null
}

export async function startMockServices(): Promise<MockServices> {
  let lastEmbed: { model: string; input: string[] } | null = null
  let lastUpsert: { collection: string; points: any[] } | null = null
  let lastSearch: { collection: string; vector: number[] } | null = null

  const ollamaServer = serve({
    port: 0,
    async fetch(req) {
      const url = new URL(req.url)

      if (url.pathname === "/api/embed" && req.method === "POST") {
        const body = await req.json()
        lastEmbed = { model: body.model, input: body.input }

        const embeddings = body.input.map((_: string, i: number) =>
          Array.from({ length: 8 }, (_, j) => (i + j + 1) / 10)
        )
        return new Response(JSON.stringify({ embeddings }), {
          headers: { "Content-Type": "application/json" }
        })
      }

      return new Response("Not found", { status: 404 })
    }
  })

  const qdrantServer = serve({
    port: 0,
    async fetch(req) {
      const url = new URL(req.url)
      const pathParts = url.pathname.split("/").filter(Boolean)

      if (req.method === "GET" && pathParts[0] === "collections" && pathParts.length === 2) {
        return new Response(JSON.stringify({
          result: {
            vectors: { size: 8, distance: "Cosine" }
          }
        }), { headers: { "Content-Type": "application/json" } })
      }

      if (req.method === "PUT" && pathParts[0] === "collections" && pathParts.length === 2) {
        const body = await req.json()
        return new Response(JSON.stringify({
          result: {
            vectors: { size: body.vectors.size, distance: body.vectors.distance }
          }
        }), { headers: { "Content-Type": "application/json" } })
      }

      if (req.method === "PUT" && pathParts[0] === "collections" && pathParts[2] === "points") {
        const collection = pathParts[1]
        const body = await req.json()
        lastUpsert = { collection, points: body.points || [] }
        return new Response(JSON.stringify({ result: true }), {
          headers: { "Content-Type": "application/json" }
        })
      }

      if (req.method === "POST" && pathParts[0] === "collections" && pathParts[2] === "points" && pathParts[3] === "search") {
        const collection = pathParts[1]
        const body = await req.json()
        lastSearch = { collection, vector: body.vector }

        return new Response(JSON.stringify({
          result: [
            {
              id: "mock-point-1",
              score: 0.85,
              payload: {
                execution_id: "test-exec-1",
                task: "optimize query performance",
                final: "approve",
                fix: "added index on user_id column",
                lesson: "check execution plan before optimization"
              }
            },
            {
              id: "mock-point-2",
              score: 0.72,
              payload: {
                execution_id: "test-exec-2",
                task: "fix memory leak in worker",
                final: "approve",
                fix: "cleared event listener references",
                lesson: "always remove event listeners in cleanup"
              }
            }
          ]
        }), { headers: { "Content-Type": "application/json" } })
      }

      return new Response("Not found", { status: 404 })
    }
  })

  const ollamaUrl = `http://localhost:${ollamaServer.port}`
  const qdrantUrl = `http://localhost:${qdrantServer.port}`

  return {
    ollamaUrl,
    qdrantUrl,
    stop: async () => {
      ollamaServer.stop()
      qdrantServer.stop()
    },
    lastEmbed: () => lastEmbed,
    lastQdrantUpsert: () => lastUpsert,
    lastQdrantSearch: () => lastSearch
  }
}
