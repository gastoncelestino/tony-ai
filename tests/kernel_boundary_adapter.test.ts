import { expect, test } from "bun:test";

import { adaptTaskExecutionContext } from "../.opencode/plugins/kernel-boundary-adapter";

const context = {
  phase: "explore",
  status: "pending",
  tasks: [{ id: "A", description: "A", phase: "explore", dependencies: [] }],
  completed: [],
};

test("adapter preserves a complete Kernel context without making authorization decisions", () => {
  const result = adaptTaskExecutionContext(
    { sessionID: "session-1", tool: "Task" },
    context,
  );

  expect(result).toEqual({
    kind: "ready",
    request: context,
  });
});

test("adapter accepts the lowercase tool name emitted by OpenCode hooks", () => {
  const result = adaptTaskExecutionContext(
    { sessionID: "session-1", tool: "task" },
    context,
  );

  expect(result).toEqual({
    kind: "ready",
    request: context,
  });
});

test("adapter does not invent missing Kernel context", () => {
  const result = adaptTaskExecutionContext(
    { sessionID: "session-1", tool: "Task" },
    {},
  );

  expect(result).toEqual({
    kind: "unavailable",
    reason: "Kernel execution context is incomplete",
  });
});

test("adapter ignores non-Task tools", () => {
  const result = adaptTaskExecutionContext(
    { sessionID: "session-1", tool: "Read" },
    {},
  );

  expect(result).toEqual({ kind: "ignored" });
});
