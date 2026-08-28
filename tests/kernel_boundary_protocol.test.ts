import { expect, test } from "bun:test";

import {
  decodeKernelBoundaryResponse,
  encodeKernelBoundaryRequest,
  type KernelBoundaryRequest,
} from "../.opencode/plugins/kernel-boundary-protocol";

test("protocol encodes a Kernel request as JSON without changing its contract", () => {
  const request: KernelBoundaryRequest = {
    phase: "explore",
    status: "pending",
    tasks: [{ id: "A", description: "A", phase: "explore", dependencies: [] }],
    completed: [],
  };

  expect(JSON.parse(encodeKernelBoundaryRequest(request))).toEqual(request);
});

test("protocol decodes an allowed Kernel response", () => {
  const response = decodeKernelBoundaryResponse(
    JSON.stringify({
      allowed: true,
      decision: "proceed",
      reason: "task authorized",
      execution_order: {
        task_id: "A",
        description: "A",
        phase: "explore",
        files: [],
      },
    }),
  );

  expect(response.allowed).toBe(true);
  expect(response.execution_order.task_id).toBe("A");
});

test("protocol decodes a blocked Kernel response", () => {
  const response = decodeKernelBoundaryResponse(
    JSON.stringify({
      allowed: false,
      decision: "blocked",
      reason: "no ready task",
    }),
  );

  expect(response).toEqual({
    allowed: false,
    decision: "blocked",
    reason: "no ready task",
  });
});

test("protocol rejects malformed Kernel responses", () => {
  expect(() => decodeKernelBoundaryResponse(JSON.stringify({ allowed: true }))).toThrow(
    "Invalid Kernel boundary response",
  );
});
