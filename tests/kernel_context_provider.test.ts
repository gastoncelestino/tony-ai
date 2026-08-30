import { expect, test } from "bun:test";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  createKernelContextProvider,
  parseCanonicalContext,
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

test("parser returns available only for complete canonical context", () => {
  expect(parseCanonicalContext(JSON.stringify({ available: true, state: context }))).toEqual({
    kind: "available",
    context,
  });
});

test("parser preserves unavailable state without inventing defaults", () => {
  expect(
    parseCanonicalContext(JSON.stringify({ available: false, reason: "SDD state unavailable" })),
  ).toEqual({
    kind: "unavailable",
    reason: "SDD state unavailable",
  });
});

test("parser blocks incomplete canonical context", () => {
  expect(
    parseCanonicalContext(
      JSON.stringify({
        available: true,
        state: { phase: "apply", status: "pending", tasks: [], completed: "invalid" },
      }),
    ),
  ).toEqual({
    kind: "unavailable",
    reason: "Canonical TaskSet context is incomplete",
  });
});

test("provider does not load TaskSet context for non-Task tools", async () => {
  const directory = mkdtempSync(join(tmpdir(), "tony-kernel-provider-"));
  const script = join(directory, "context.sh");
  const marker = join(directory, "called.txt");

  writeFileSync(
    script,
    `#!/bin/sh\nprintf '%s' called > "${marker}"\nprintf '%s\\n' '${JSON.stringify({ available: true, state: context })}'\n`,
  );
  chmodSync(script, 0o755);

  try {
    const provider = createKernelContextProvider(directory, { pythonCommand: script });
    await expect(
      provider.getContext({ sessionID: "session-1", tool: "read" }),
    ).resolves.toEqual({
      kind: "unavailable",
      reason: "Kernel context requested for non-Task tool",
    });

    expect(() => readFileSync(marker, "utf8")).toThrow();
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("provider invokes the context script with the project-local database path", async () => {
  const directory = mkdtempSync(join(tmpdir(), "tony-kernel-provider-"));
  const script = join(directory, "context.sh");
  const argsFile = join(directory, "args.txt");
  const dbPath = join(directory, "local-memory", "memory.db");

  writeFileSync(
    script,
    `#!/bin/sh\nprintf '%s\\n' "$@" > "${argsFile}"\nprintf '%s\\n' '${JSON.stringify({ available: true, state: context })}'\n`,
  );
  chmodSync(script, 0o755);

  try {
    const provider = createKernelContextProvider(directory, {
      pythonCommand: script,
      contextScript: "context-script.py",
      dbPath,
    });

    await expect(
      provider.getContext({ sessionID: "session-1", tool: "Task" }),
    ).resolves.toEqual({ kind: "available", context });

    const args = readFileSync(argsFile, "utf8").trim().split("\n");
    expect(args).toEqual([
      "--get",
      "--project",
      directory,
      "--session-id",
      "session-1",
      "--db-path",
      dbPath,
    ]);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
