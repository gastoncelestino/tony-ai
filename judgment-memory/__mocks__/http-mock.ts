/**
 * __mocks__/http-mock.ts
 * Mock HTTP server para Ollama/Qdrant, replicando el patrón de test_ledger.py
 * pero en TypeScript usando Bun's built-in server.
 */

interface MockServer {
  port: number
  url: string
  close: () => void
  lastEmbed: () => { model: string; input: string[] } | null
  lastQdrantUpsert: () => { collection: string; points: any[] } | null
  lastQdrantSearch: () => { collection: string; vector: number[] } | null
}

export async function startMockServices(): Promise<MockServer> {
  let lastEmbed: { model: string; input: string[] } | null = null
  let lastUpsert: { collection: string; points: any[] } | null = null
  let lastSearch: { collection: string; vector: number[] } | null = null

  const ollamaServer = Bun.serve({
    port: 0, // random port
    async fetch(req: Request) {
      const url = new URL(req.url)
      if (url.pathname === "/api/embed") {
        const body = await req.json()
        lastEmbed = { model: body.model, input: body.input }
        const embeddings = body.input.map((): number[] => 
          Array.from({ length: 384 }, () => Math.random() * 2 - 1)
        )
        return Response.json({ embeddings })
      }
      return new Response("not found", { status: 404 })
    }
  })

  const qdrantServer = Bun.serve({
    port: 0, // random port
    async fetch(req: Request) {
      const url = new URL(req.url)
      const method = req.method

      if (url.pathname === "/collections/jdmem_test-project") {
        if (method === "GET") return Response.json({ result: { vectors: { size: 384 } } })
        if (method === "PUT") return Response.json({})
      }

      if (url.pathname === "/collections/jdmem_test-project/points") {
        if (method === "PUT") {
          const body = await req.json()
          lastUpsert = { collection: "jdmem_test-project", points: body.points }
          return Response.json({})
        }
      }

      if (url.pathname === "/collections/jdmem_test-project/points/search") {
        if (method === "POST") {
          const body = await req.json()
          lastSearch = { collection: "jdmem_test-project", vector: body.vector }
          return Response.json({
            result: [
              { score: 0.75, id: "test-1", payload: { test: "passive-capture" } }
            ]
          })
        }
      }

      return new Response("not found", { status: 404 })
    }
  })

  return {
    port: ollamaServer.port,
    url: `http://localhost:${ollamaServer.port}`,
    close: () => {
      ollamaServer.stop()
      qdrantServer.stop()
    },
    lastEmbed: () => lastEmbed,
    lastQdrantUpsert: () => lastUpsert,
    lastQdrantSearch: () => lastSearch
  }
}
