import { expect, test } from "bun:test"

import { callKernelBoundary } from "../.opencode/plugins/kernel-boundary-transport"
import type { KernelBoundaryRequest } from "../.opencode/plugins/kernel-boundary-protocol"

const request: KernelBoundaryRequest = {
  phase: "explore",
  status: "pending",
  tasks: [{ id: "A", description: "A", phase: "explore", dependencies: [] }],
  completed: [],
}

test("transport exchanges JSON with the Python Kernel boundary", async () => {
  const response = await callKernelBoundary(request)

  expect(response.allowed).toBe(true)
  if (response.allowed) expect(response.execution_order.task_id).toBe("A")
})

test("transport fails closed when the Python process is unavailable", async () => {
  const response = await callKernelBoundary(request, {
    command: "definitely-not-a-python-command",
  })

  expect(response).toEqual({
    allowed: false,
    decision: "blocked",
    reason: "Kernel boundary process unavailable",
    execution_order: null,
  })
})

test("transport fails closed on malformed process output", async () => {
  const response = await callKernelBoundary(request, {
    command: "python3",
    args: ["-c", "print('not-json')"],
  })

  expect(response.allowed).toBe(false)
  expect(response.decision).toBe("blocked")
})
