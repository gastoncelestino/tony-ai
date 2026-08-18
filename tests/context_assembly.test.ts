import { expect, test } from "bun:test"
import { resolve } from "node:path"

import { ContextAssembly, MAX_CONTEXT_CHARS } from "../plugins/context-assembly"

const ROOT = resolve(import.meta.dir, "..")
const CODE = { type: "project_code", path: "src/foo.py", start_line: 42, end_line: 58, text: "def foo():\n    return 42", lang: "python" }
const DOC = { source_id: "python", url: "https://docs.python.org/3.14/", title: "Python 3.14", text: "asyncio docs" }

async function assemble(sessionID: string, metadata: Record<string, unknown>, system = ["Existing system prompt"]) {
  const hooks = ContextAssembly({ worktree: ROOT })
  await hooks["tool.execute.after"]({ tool: metadata.reference ? "context7_query_docs" : "code-index_code_search", sessionID }, { output: "", metadata })
  await hooks["experimental.chat.system.transform"]({ sessionID }, { system })
  return system[0]
}

test("documentation + code both appear in the existing system context", async () => {
  const hooks = ContextAssembly({ worktree: ROOT })
  await hooks["tool.execute.after"]({ tool: "context7_query_docs", sessionID: "both" }, { output: "", metadata: { reference: DOC } })
  await hooks["tool.execute.after"]({ tool: "code-index_code_search", sessionID: "both" }, { output: "", metadata: { project_code: [CODE] } })
  const output = { system: ["task"] }
  await hooks["experimental.chat.system.transform"]({ sessionID: "both" }, output)
  expect(output.system[0]).toContain("Authorized documentation")
  expect(output.system[0]).toContain("Existing project code")
})

test("documentation alone is included", async () => {
  const text = await assemble("docs", { reference: DOC })
  expect(text).toContain("Python 3.14")
  expect(text).toContain("asyncio docs")
})

test("code alone is included", async () => {
  const text = await assemble("code", { project_code: [CODE] })
  expect(text).toContain("src/foo.py:42-58")
  expect(text).toContain("def foo()")
})

test("assembled context preserves documentation provenance", async () => {
  const text = await assemble("doc-provenance", { reference: DOC })
  expect(text).toContain("source: python")
  expect(text).toContain("https://docs.python.org/3.14/")
})

test("assembled context preserves code provenance", async () => {
  const text = await assemble("code-provenance", { project_code: [CODE] })
  expect(text).toContain("source: code-index")
  expect(text).toContain("src/foo.py:42-58")
})

test("unauthorized documentation is rejected", async () => {
  const text = await assemble("bad-doc", { reference: { ...DOC, source_id: "stackoverflow", url: "https://stackoverflow.com/" } })
  expect(text).not.toContain("stackoverflow")
  expect(text).not.toContain("asyncio docs")
})

test("existing system prompt is preserved", async () => {
  const text = await assemble("preserve", { reference: DOC })
  expect(text.startsWith("Existing system prompt")).toBe(true)
})

test("multiple code-index results are all included", async () => {
  const text = await assemble("many-code", { project_code: [CODE, { ...CODE, path: "tests/test_foo.py", start_line: 20, end_line: 37 }] })
  expect(text).toContain("src/foo.py:42-58")
  expect(text).toContain("tests/test_foo.py:20-37")
})

test("invalid metadata does not break context", async () => {
  const text = await assemble("invalid", { project_code: [{ path: "missing-lines" }], reference: { source_id: "python" } })
  expect(text).toBe("Existing system prompt")
})

test("one session does not contaminate another", async () => {
  const hooks = ContextAssembly({ worktree: ROOT })
  await hooks["tool.execute.after"]({ tool: "code-index_code_search", sessionID: "A" }, { output: "", metadata: { project_code: [CODE] } })
  const outputB = { system: ["B"] }
  await hooks["experimental.chat.system.transform"]({ sessionID: "B" }, outputB)
  expect(outputB.system[0]).toBe("B")
  const outputA = { system: ["A"] }
  await hooks["experimental.chat.system.transform"]({ sessionID: "A" }, outputA)
  expect(outputA.system[0]).toContain("src/foo.py:42-58")
})

test("assembled context respects the maximum size", async () => {
  const large = "x".repeat(10_000)
  const projectCode = [0, 1, 2].map((index) => ({
    ...CODE,
    path: `src/large_${index}.py`,
    text: `${large}-${index}`,
  }))
  const text = await assemble("budget", { project_code: projectCode })
  const addedContext = text.slice("Existing system prompt".length)
  expect(addedContext.length).toBeLessThanOrEqual(MAX_CONTEXT_CHARS + 2)
})

test("context budget keeps complete code results", async () => {
  const large = "y".repeat(10_000)
  const projectCode = [
    { ...CODE, path: "src/first.py", text: `${large}-first` },
    { ...CODE, path: "src/second.py", text: `${large}-second` },
    { ...CODE, path: "src/third.py", text: `${large}-third` },
  ]
  const text = await assemble("complete-results", { project_code: projectCode })
  expect(text).toContain("src/first.py:42-58")
  expect(text).toContain("src/second.py:42-58")
  expect(text).not.toContain("src/third.py:42-58")
  expect(text).not.toContain("-third")
})

test("duplicate code results are included only once", async () => {
  const text = await assemble("dedupe-code", { project_code: [CODE, CODE] })
  expect(text.match(/src\/foo\.py:42-58/g)?.length).toBe(1)
})

test("duplicate documentation results are included only once", async () => {
  const text = await assemble("dedupe-doc", { reference: DOC })
  expect(text.match(/### Python 3\.14/g)?.length).toBe(1)
})

test("mixed sources share the context budget", async () => {
  const large = "z".repeat(13_000)
  const hooks = ContextAssembly({ worktree: ROOT })
  await hooks["tool.execute.after"]({ tool: "context7_query_docs", sessionID: "mixed-budget" }, { output: "", metadata: { reference: { ...DOC, text: `${large}-doc` } } })
  await hooks["tool.execute.after"]({ tool: "code-index_code_search", sessionID: "mixed-budget" }, { output: "", metadata: { project_code: [{ ...CODE, text: `${large}-code` }] } })
  const output = { system: ["task"] }
  await hooks["experimental.chat.system.transform"]({ sessionID: "mixed-budget" }, output)
  expect(output.system[0]).toContain("-doc")
  expect(output.system[0]).toContain("-code")
  expect(output.system[0].length).toBeLessThanOrEqual("task".length + 2 + MAX_CONTEXT_CHARS)
})
