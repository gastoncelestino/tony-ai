import { expect, test } from "bun:test"
import { extractToolAuthorizationRequest } from "../plugins/tony-kernel/tool-authorization"

test("extracts a bash command without inventing paths", () => {
  expect(extractToolAuthorizationRequest("bash", {
    command: "git status",
  })).toEqual({
    tool: "bash",
    command: "git status",
    paths: [],
  })
})

test("extracts explicit file paths from edit and write style arguments", () => {
  expect(extractToolAuthorizationRequest("edit", {
    filePath: "src/app.ts",
    oldString: "old",
    newString: "new",
  })).toEqual({
    tool: "edit",
    command: null,
    paths: ["src/app.ts"],
  })

  expect(extractToolAuthorizationRequest("write", {
    path: "README.md",
    content: "hello",
  })).toEqual({
    tool: "write",
    command: null,
    paths: ["README.md"],
  })
})

test("accepts explicit path collections without accepting arbitrary values", () => {
  expect(extractToolAuthorizationRequest("custom", {
    paths: ["a.ts", "", 42, "b.ts"],
    unrelated: "not-a-path",
  })).toEqual({
    tool: "custom",
    command: null,
    paths: ["a.ts", "b.ts"],
  })
})
