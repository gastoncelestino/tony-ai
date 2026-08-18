import { expect, test } from "bun:test"
import { resolve } from "node:path"

import {
  addDocumentationProvenance,
  Context7Allowlist,
  isAllowedLibraryId,
} from "../plugins/context7-allowlist"

const ROOT = resolve(import.meta.dir, "..")
const ALLOWED = new Set([
  "/websites/python_3_14",
  "/websites/fastapi_tiangolo",
  "/reactjs/react.dev",
  "/supabase/postgres",
])

test("Context7 policy allows only the configured library IDs", () => {
  expect(isAllowedLibraryId("/websites/python_3_14", ALLOWED)).toBe(true)
  expect(isAllowedLibraryId("/websites/fastapi_tiangolo", ALLOWED)).toBe(true)
  expect(isAllowedLibraryId("/reactjs/react.dev", ALLOWED)).toBe(true)
  expect(isAllowedLibraryId("/supabase/postgres", ALLOWED)).toBe(true)
  expect(isAllowedLibraryId("/stackoverflow", ALLOWED)).toBe(false)
  expect(isAllowedLibraryId("/random-blog", ALLOWED)).toBe(false)
  expect(isAllowedLibraryId(undefined, ALLOWED)).toBe(false)
})

test("Context7 hook fails closed for unauthorized documentation", async () => {
  const hooks = await Context7Allowlist({ worktree: ROOT })
  const before = hooks["tool.execute.before"]

  await expect(
    before(
      { tool: "context7_query_docs" },
      { args: { libraryId: "/websites/python_3_14", query: "asyncio" } },
    ),
  ).resolves.toBeUndefined()

  await expect(
    before(
      { tool: "context7_query_docs" },
      { args: { libraryId: "/stackoverflow", query: "anything" } },
    ),
  ).rejects.toThrow("Documentation source is not authorized")

  await expect(
    before(
      { tool: "context7_query_docs" },
      { args: { query: "anything" } },
    ),
  ).rejects.toThrow("Documentation source is not authorized")
})

test("Context7 hook blocks open-ended library resolution", async () => {
  const hooks = await Context7Allowlist({ worktree: ROOT })

  await expect(
    hooks["tool.execute.before"](
      { tool: "context7_resolve_library_id" },
      { args: { libraryName: "stackoverflow", query: "anything" } },
    ),
  ).rejects.toThrow("Library resolution is disabled")
})

test("Context7 documentation results preserve provenance", () => {
  const sources = new Map([
    [
      "/websites/python_3_14",
      {
        id: "python",
        name: "Python 3.14",
        library_id: "/websites/python_3_14",
        url: "https://docs.python.org/3.14/",
        enabled: true,
      },
    ],
  ])
  const output: { output: string; metadata?: Record<string, unknown> } = {
    output: "asyncio documentation fragment",
  }

  addDocumentationProvenance("/websites/python_3_14", output, sources)

  expect(output.metadata?.reference).toEqual({
    source_id: "python",
    url: "https://docs.python.org/3.14/",
    title: "Python 3.14",
    text: "asyncio documentation fragment",
  })
})

test("Context7 hook does not affect code-index", async () => {
  const hooks = await Context7Allowlist({ worktree: ROOT })

  await expect(
    hooks["tool.execute.before"](
      { tool: "code-index_code_search" },
      { args: { query: "knowledge sources" } },
    ),
  ).resolves.toBeUndefined()
})
