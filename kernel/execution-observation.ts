export type ExecutionResultObservation = { title: string; output: string; metadata: unknown }
export type ExecutionObservation = {
  projectId: string; sessionId: string; callId: string; taskId: string; phase: string
  status: "running" | "succeeded" | "failed" | "incomplete"
  startedAt: string; finishedAt?: string; result?: ExecutionResultObservation
}
export type ExecutionObservationStore = {
  start: (input: Omit<ExecutionObservation, "status" | "startedAt"> & { startedAt?: string }) => ExecutionObservation
  succeed: (callId: string, result: ExecutionResultObservation, finishedAt?: string) => ExecutionObservation
  fail: (callId: string, result: ExecutionResultObservation, finishedAt?: string) => ExecutionObservation
  incomplete: (callId: string, finishedAt?: string) => ExecutionObservation
  get: (callId: string) => ExecutionObservation | undefined
  hasRunningSession: (sessionId: string) => boolean
}

export function createExecutionObservationStore(now: () => string = () => new Date().toISOString()): ExecutionObservationStore {
  const running = new Map<string, ExecutionObservation>()
  const sessions = new Map<string, number>()
  const get = (callId: string) => running.get(callId)
  const hasRunningSession = (sessionId: string) => (sessions.get(sessionId) ?? 0) > 0
  const finish = (callId: string, status: "succeeded" | "failed" | "incomplete", finishedAt: string, result?: ExecutionResultObservation) => {
    const attempt = running.get(callId)
    if (!attempt) throw new Error(`Unknown execution callID: ${callId}`)
    if ((status === "succeeded" || status === "failed") && !result) throw new Error(`${status} execution requires a result`)
    running.delete(callId)
    const count = (sessions.get(attempt.sessionId) ?? 1) - 1
    if (count <= 0) sessions.delete(attempt.sessionId); else sessions.set(attempt.sessionId, count)
    return { ...attempt, status, finishedAt, ...(result ? { result } : {}) }
  }
  return {
    start(input) {
      if (!input.callId || !input.sessionId || !input.taskId || !input.phase) throw new Error("Execution observation requires callId, sessionId, taskId, and phase")
      if (running.has(input.callId)) throw new Error(`Execution callID already running: ${input.callId}`)
      const attempt = { ...input, status: "running" as const, startedAt: input.startedAt ?? now() }
      running.set(attempt.callId, attempt)
      sessions.set(attempt.sessionId, (sessions.get(attempt.sessionId) ?? 0) + 1)
      return attempt
    },
    succeed(callId, result, finishedAt = now()) { return finish(callId, "succeeded", finishedAt, result) },
    fail(callId, result, finishedAt = now()) { return finish(callId, "failed", finishedAt, result) },
    incomplete(callId, finishedAt = now()) { return finish(callId, "incomplete", finishedAt) },
    get, hasRunningSession,
  }
}
