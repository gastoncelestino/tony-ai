export type ExecutionGraphNodeKind = "session" | "task" | "tool"

export type ExecutionGraphNode = {
  id: string
  kind: ExecutionGraphNodeKind
  parentId?: string
  sessionId: string
  callId?: string
  taskId?: string
  tool?: string
  status: "running" | "succeeded" | "failed" | "blocked" | "completed"
  startedAt: string
  finishedAt?: string
  result?: {
    title: string
    output: string
    metadata: unknown
  }
}

export type ExecutionGraph = {
  sessionCreated: (input: { sessionId: string; parentSessionId?: string; startedAt?: string }) => ExecutionGraphNode
  taskStarted: (input: { sessionId: string; callId: string; taskId: string; agent?: string; startedAt?: string }) => ExecutionGraphNode
  taskFinished: (input: { callId: string; status: ExecutionGraphNode["status"]; finishedAt?: string; result?: ExecutionGraphNode["result"] }) => ExecutionGraphNode | undefined
  toolStarted: (input: { sessionId: string; callId: string; tool: string; startedAt?: string }) => ExecutionGraphNode
  toolFinished: (input: { callId: string; status: ExecutionGraphNode["status"]; finishedAt?: string; result?: ExecutionGraphNode["result"] }) => ExecutionGraphNode | undefined
  get: (id: string) => ExecutionGraphNode | undefined
  getByCallId: (callId: string) => ExecutionGraphNode | undefined
  getChildren: (id: string) => ExecutionGraphNode[]
  getTaskForChildSession: (childSessionId: string) => ExecutionGraphNode | undefined
}

export function createExecutionGraph(now: () => string = () => new Date().toISOString()): ExecutionGraph {
  const nodes = new Map<string, ExecutionGraphNode>()
  const callIndex = new Map<string, string>()
  const sessionIndex = new Map<string, string>()
  const pendingTasks = new Map<string, string[]>()
  const taskChildren = new Map<string, string>()

  const get = (id: string) => nodes.get(id)
  const getByCallId = (callId: string) => {
    const id = callIndex.get(callId)
    return id ? nodes.get(id) : undefined
  }
  const getChildren = (id: string) => [...nodes.values()].filter((node) => node.parentId === id)

  const sessionCreated = (input: { sessionId: string; parentSessionId?: string; startedAt?: string }) => {
    const existing = sessionIndex.get(input.sessionId)
    if (existing) return nodes.get(existing)!

    const node: ExecutionGraphNode = {
      id: `session:${input.sessionId}`,
      kind: "session",
      ...(input.parentSessionId ? { parentId: `session:${input.parentSessionId}` } : {}),
      sessionId: input.sessionId,
      status: "running",
      startedAt: input.startedAt ?? now(),
    }
    nodes.set(node.id, node)
    sessionIndex.set(input.sessionId, node.id)

    if (input.parentSessionId) {
      const queue = pendingTasks.get(input.parentSessionId) ?? []
      const taskCallId = queue.shift()
      if (queue.length) pendingTasks.set(input.parentSessionId, queue)
      else pendingTasks.delete(input.parentSessionId)
      if (taskCallId) {
        taskChildren.set(taskCallId, input.sessionId)
        const task = getByCallId(taskCallId)
        const child = nodes.get(node.id)
        if (task && child) child.parentId = task.id
      }
    }

    return node
  }

  const taskStarted = (input: { sessionId: string; callId: string; taskId: string; agent?: string; startedAt?: string }) => {
    const existing = getByCallId(input.callId)
    if (existing) return existing

    const parentSession = sessionIndex.get(input.sessionId)
    const node: ExecutionGraphNode = {
      id: `task:${input.callId}`,
      kind: "task",
      ...(parentSession ? { parentId: parentSession } : {}),
      sessionId: input.sessionId,
      callId: input.callId,
      taskId: input.taskId,
      tool: input.agent,
      status: "running",
      startedAt: input.startedAt ?? now(),
    }
    nodes.set(node.id, node)
    callIndex.set(input.callId, node.id)

    const queue = pendingTasks.get(input.sessionId) ?? []
    queue.push(input.callId)
    pendingTasks.set(input.sessionId, queue)
    return node
  }

  const taskFinished = (input: { callId: string; status: ExecutionGraphNode["status"]; finishedAt?: string; result?: ExecutionGraphNode["result"] }) => {
    const node = getByCallId(input.callId)
    if (!node || node.kind !== "task") return undefined
    node.status = input.status
    node.finishedAt = input.finishedAt ?? now()
    if (input.result) node.result = input.result
    const queue = pendingTasks.get(node.sessionId)
    if (queue) {
      const remaining = queue.filter((callId) => callId !== input.callId)
      if (remaining.length) pendingTasks.set(node.sessionId, remaining)
      else pendingTasks.delete(node.sessionId)
    }
    return node
  }

  const toolStarted = (input: { sessionId: string; callId: string; tool: string; startedAt?: string }) => {
    const existing = getByCallId(input.callId)
    if (existing) return existing

    const parentSession = sessionIndex.get(input.sessionId)
    const task = getTaskForChildSession(input.sessionId)
    const node: ExecutionGraphNode = {
      id: `tool:${input.callId}`,
      kind: "tool",
      ...(task ? { parentId: task.id } : parentSession ? { parentId: parentSession } : {}),
      sessionId: input.sessionId,
      callId: input.callId,
      tool: input.tool,
      status: "running",
      startedAt: input.startedAt ?? now(),
    }
    nodes.set(node.id, node)
    callIndex.set(input.callId, node.id)
    return node
  }

  const toolFinished = (input: { callId: string; status: ExecutionGraphNode["status"]; finishedAt?: string; result?: ExecutionGraphNode["result"] }) => {
    const node = getByCallId(input.callId)
    if (!node || node.kind !== "tool") return undefined
    node.status = input.status
    node.finishedAt = input.finishedAt ?? now()
    if (input.result) node.result = input.result
    return node
  }

  const getTaskForChildSession = (childSessionId: string) => {
    const callId = [...taskChildren.entries()].find(([, sessionId]) => sessionId === childSessionId)?.[0]
    return callId ? getByCallId(callId) : undefined
  }

  return { sessionCreated, taskStarted, taskFinished, toolStarted, toolFinished, get, getByCallId, getChildren, getTaskForChildSession }
}
