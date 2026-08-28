import { expect, test } from "bun:test";

import { adaptTaskExecutionContext } from "../.opencode/plugins/kernel-boundary-adapter";

test("adapter preserves a complete Kernel context without making authorization decisions", () => {
  const result = adaptTaskExecutionContext(
    { sessionID: "session-1", tool: "Task" },
    {
      phase: "explore",
      status: "pending",
      tasks: [{ id: "A", description: "A", phase: "explore", dependencies: [] }],
      completed: [],
    }
  );

  expect(result).toEqual({
    kind: "ready",
    request: {
      phase: "explore",
      status: "pending",
      tasks: [{ id: "A", description: "A", phase: "explore", dependencies: [] }],
      completed: [],
    },
  });
});

test("adapter does not invent missing Kernel context", () => {
  const result = adaptTaskExecutionContext(
    { sessionID: "session-1", tool: "Task" },
    {}
  );

  expect(result).toEqual({
    kind: "unavailable",
    reason: "Kernel execution context is incomplete",
  });
});

test("adapter ignores non-Task tools", () => {
  const result = adaptTaskExecutionContext(
    { sessionID: "session-1", tool: "Read" },
    {}
  );

  expect(result).toEqual({ kind: "ignored" });
});
