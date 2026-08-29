import { expect, test } from "bun:test";

import {
  createKernelContextProvider,
  parsePersistedState,
} from "../.opencode/plugins/kernel-context-provider";

const context = {
  phase: "apply",
  status: "pending",
  tasks: [
    {
      id: "T1",
      description: "Implement feature",
      phase: "apply",
      dependencies: [],
    },
  ],
  completed: [],
};

test("provider returns available only for complete persisted state", async () => {
  const provider = createKernelContextProvider("/project", {
    readState: async () => ({ available: true, state: context }),
  });

  await expect(
    provider.getContext({ sessionID: "session-1", tool: "Task" }),
  ).resolves.toEqual({ kind: "available", context });
});

test("provider blocks when persisted state is unavailable", async () => {
  const provider = createKernelContextProvider("/project", {
    readState: async () => ({ available: false, reason: "SDD state unavailable" }),
  });

  await expect(
    provider.getContext({ sessionID: "session-1", tool: "Task" }),
  ).resolves.toEqual({
    kind: "unavailable",
    reason: "SDD state unavailable",
  });
});

test("provider blocks incomplete persisted state instead of inventing defaults", async () => {
  const provider = createKernelContextProvider("/project", {
    readState: async () => ({
      available: true,
      state: { phase: "apply", status: "pending", tasks: [], completed: "invalid" },
    }),
  });

  await expect(
    provider.getContext({ sessionID: "session-1", tool: "Task" }),
  ).resolves.toEqual({
    kind: "unavailable",
    reason: "TonyMem SDD state is incomplete",
  });
});

test("provider blocks malformed helper output", () => {
  expect(parsePersistedState("not json")).toEqual({
    kind: "unavailable",
    reason: "Invalid TonyMem SDD state response",
  });
});
