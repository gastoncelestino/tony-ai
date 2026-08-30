import { describe, expect, test } from "bun:test"
import { createExecutionObservationStore } from "../.opencode/plugins/execution-observation"

const result = {
  title: "Task",
  output: "done",
  metadata: { exit_code: 0 },
}

describe("execution observation", () => {
  test("before starts a running attempt correlated by callID", () => {
    const observations = createExecutionObservationStore(() => "2026-08-29T10:00:00.000Z")
    const attempt = observations.start({
      projectId: "project",
      sessionId: "session",
      callId: "call-1",
      taskId: "T1",
      phase: "apply",
    })

    expect(attempt.status).toBe("running")
    expect(attempt.callId).toBe("call-1")
    expect(attempt.result).toBeUndefined()
    expect(observations.hasRunningSession("session")).toBe(true)
    expect(observations.hasRunningSession("other-session")).toBe(false)
  })

  test("completed after transitions the same callID to succeeded with Result", () => {
    const observations = createExecutionObservationStore(() => "2026-08-29T10:00:00.000Z")
    observations.start({
      projectId: "project",
      sessionId: "session",
      callId: "call-1",
      taskId: "T1",
      phase: "apply",
    })

    const finished = observations.succeed("call-1", result, "2026-08-29T10:00:01.000Z")

    expect(finished.status).toBe("succeeded")
    expect(finished.result).toEqual(result)
    expect(finished.finishedAt).toBe("2026-08-29T10:00:01.000Z")
    expect(observations.get("call-1")).toBeUndefined()
    expect(observations.hasRunningSession("session")).toBe(false)
  })

  test("error after transitions the same callID to failed with an error Result", () => {
    const observations = createExecutionObservationStore(() => "2026-08-29T10:00:00.000Z")
    observations.start({
      projectId: "project",
      sessionId: "session",
      callId: "call-1",
      taskId: "T1",
      phase: "apply",
    })

    const finished = observations.fail(
      "call-1",
      { title: "Task execution error", output: "boom", metadata: { status: "error" } },
    )

    expect(finished.status).toBe("failed")
    expect(finished.result?.output).toBe("boom")
  })

  test("a running attempt cannot be finalized successfully without a Result", () => {
    const observations = createExecutionObservationStore(() => "2026-08-29T10:00:00.000Z")
    observations.start({
      projectId: "project",
      sessionId: "session",
      callId: "call-1",
      taskId: "T1",
      phase: "apply",
    })

    expect(() => observations.succeed("call-1", undefined as never)).toThrow(
      "succeeded execution requires a result",
    )
  })

  test("missing finalization can be represented explicitly as incomplete", () => {
    const observations = createExecutionObservationStore(() => "2026-08-29T10:00:00.000Z")
    observations.start({
      projectId: "project",
      sessionId: "session",
      callId: "call-1",
      taskId: "T1",
      phase: "apply",
    })

    const incomplete = observations.incomplete("call-1", "2026-08-29T10:00:02.000Z")

    expect(incomplete.status).toBe("incomplete")
    expect(incomplete.result).toBeUndefined()
    expect(observations.hasRunningSession("session")).toBe(false)
  })
})
