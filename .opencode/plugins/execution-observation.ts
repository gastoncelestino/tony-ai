export type ExecutionResultObservation = {
  title: string
  output: string
  metadata: unknown
}

export type ExecutionObservation = {
  projectId: string
  sessionId: string
  callId: string
  taskId: string
  phase: string
  status: "running" | "succeeded" | "failed" | "incomplete"
  startedAt: string
  finishedAt?: string
  result?: ExecutionResultObservation
}

export type ExecutionObservationStore = {
  start: (input: Omit<ExecutionObservation, "status" | "startedAt"> & { startedAt?: string }) => ExecutionObservation
  succeed: (callId: string, result: ExecutionResultObservation, finishedAt?: string) => ExecutionObservation
  fail: (callId: string, result: ExecutionResultObservation, finishedAt?: string) => ExecutionObservation
  incomplete: (callId: string, finishedAt?: string) => ExecutionObservation
  get: (callId: string) => ExecutionObservation | undefined
}

export function createExecutionObservationStore(now: () => string = currentTime): ExecutionObservationStore {
  const running = new Map<string, ExecutionObservation>()

  const get = (callId: string) => running.get(callId)

  function finish(
    callId: string,
    status: "succeeded" | "failed" | "incomplete",
    finishedAt: string,
    result?: ExecutionResultObservation,
  ): ExecutionObservation {
    const attempt = running.get(callId)
    if (!attempt) throw new Error(`Unknown execution callID: ${callId}`)

    if ((status === "succeeded" || status === "failed") && !result) {
      throw new Error(`${status} execution requires a result`)
    }

    const finished: ExecutionObservation = {
      ...attempt,
      status,
      finishedAt,
      ...(result ? { result } : {}),
    }
    running.delete(callId)
    return finished
  }

  return {
    start(input) {
      if (running.has(input.callId)) throw new Error(`Execution callID already running: ${input.callId}`)
      const attempt: ExecutionObservation = {
        ...input,
        status: "running",
        startedAt: input.startedAt ?? now(),
      }
      running.set(attempt.callId, attempt)
      return attempt
    },
    succeed(callId, result, finishedAt = now()) {
      return finish(callId, "succeeded", finishedAt, result)
    },
    fail(callId, result, finishedAt = now()) {
      return finish(callId, "failed", finishedAt, result)
    },
    incomplete(callId, finishedAt = now()) {
      return finish(callId, "incomplete", finishedAt)
    },
    get,
  }
}

function currentTime(): string {
  return new Date().toISOString()
}
