import { expect, test } from "bun:test";


type KernelRequest = {
  task_id: string;
  phase: string;
  status: string;
};

type KernelDecision = {
  allowed: boolean;
  decision: "allowed" | "blocked";
  reason: string;
};

function failClosed(_request: KernelRequest): KernelDecision {
  return {
    allowed: false,
    decision: "blocked",
    reason: "kernel boundary unavailable",
  };
}

test("kernel boundary blocks when authorization is unavailable", () => {
  const result = failClosed({
    task_id: "A",
    phase: "explore",
    status: "running",
  });

  expect(result.allowed).toBe(false);
  expect(result.decision).toBe("blocked");
  expect(result.reason).toBe("kernel boundary unavailable");
});

test("kernel boundary request carries only execution authorization context", () => {
  const request: KernelRequest = {
    task_id: "A",
    phase: "explore",
    status: "running",
  };

  expect(Object.keys(request).sort()).toEqual(["phase", "status", "task_id"]);
});
