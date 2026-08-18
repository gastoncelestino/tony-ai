import { expect, test } from "bun:test"

import {
  addProjectCodeContext,
  normalizeProjectCodeResults,
  ProjectCodeContext,
} from "../plugins/project-code-context"

test("code-index results become project_code context", () => {
  const output = {
    output: JSON.stringify({
      results: [
        {
          path: "src/foo.py",
          start_line: 42,
          end_line: 58,
          text: "def foo():\n    return 42",
          lang: "python",
        },
      ],
      count: 1,
    }),
  }

  addProjectCodeContext(output)

  expect(output.metadata?.project_code).toEqual([
    {
      type: "project_code",
      path: "src/foo.py",
      start_line: 42,
      end_line: 58,
      text: "def foo():\n    return 42",
      lang: "python",
    },
  ])
})

test("multiple code-index results are preserved", () => {
  const contexts = normalizeProjectCodeResults(
    JSON.stringify({
      results: [
        { path: "a.py", start_line: 1, end_line: 3, text: "a", lang: "python" },
        { path: "b.ts", start_line: 10, end_line: 15, text: "b", lang: "typescript" },
      ],
    }),
  )

  expect(contexts).toHaveLength(2)
  expect(contexts[0].path).toBe("a.py")
  expect(contexts[1].path).toBe("b.ts")
})

test("invalid results are ignored without inventing context", () => {
  expect(
    normalizeProjectCodeResults(
      JSON.stringify({ results: [{ path: "a.py", text: "missing lines" }] }),
    ),
  ).toEqual([])
  expect(normalizeProjectCodeResults("not json")).toEqual([])
})

test("project code hook only handles code-index search", async () => {
  const hooks = ProjectCodeContext()
  const output = { output: JSON.stringify({ results: [] }) }

  await expect(
    hooks["tool.execute.after"]({ tool: "code-index_code_search" }, output),
  ).resolves.toBeUndefined()

  await expect(
    hooks["tool.execute.after"]({ tool: "context7_query_docs" }, output),
  ).resolves.toBeUndefined()
})
