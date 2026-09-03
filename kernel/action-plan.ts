import type { KernelContext, KernelPhase, KernelTask } from "./protocol"

export type ActionPlan =
  | {
      action: "delegate"
      phase: KernelPhase
      task_id: string
      agent: string
      objective: string
      files: string[]
      allowed_tools: string[]
      max_iterations: number
    }
  | {
      action: "done"
      reason: string
    }

const PHASE_AGENTS: Record<KernelPhase, string> = {
  explore: "sdd-explore",
  propose: "sdd-propose",
  spec: "sdd-spec",
  design: "sdd-design",
  tasks: "sdd-tasks",
  apply: "sdd-apply",
  verify: "sdd-verify",
  archive: "sdd-archive",
}

const PHASE_TOOLS: Record<KernelPhase, string[]> = {
  explore: ["read", "glob", "grep", "batch_read"],
  propose: ["read", "glob", "grep", "batch_read"],
  spec: ["read", "glob", "grep", "batch_read"],
  design: ["read", "glob", "grep", "batch_read"],
  tasks: ["read", "glob", "grep", "batch_read"],
  apply: ["read", "glob", "grep", "batch_read", "edit", "write"],
  verify: ["read", "glob", "grep", "batch_read", "bash"],
  archive: ["read", "glob", "grep", "batch_read"],
}

const MAX_ITERATIONS = 8

function isReady(task: KernelTask, completed: Set<string>) {
  return task.dependencies.every((dependency) => completed.has(dependency))
}

export function resolveActionPlan(context: KernelContext): ActionPlan {
  if (context.tasks.length > 0 && context.tasks.every((task) => context.completed.includes(task.id))) {
    return {
      action: "done",
      reason: "all tasks completed",
    }
  }

  const completed = new Set(context.completed)
  const task = context.tasks.find((candidate) => !completed.has(candidate.id) && isReady(candidate, completed))

  if (!task) {
    throw new Error("[Tony Kernel] no eligible task is available")
  }

  return {
    action: "delegate",
    phase: task.phase,
    task_id: task.id,
    agent: PHASE_AGENTS[task.phase],
    objective: task.description,
    files: task.files ?? [],
    allowed_tools: [...PHASE_TOOLS[task.phase]],
    max_iterations: MAX_ITERATIONS,
  }
}

export function actionPlanPrompt(plan: Extract<ActionPlan, { action: "delegate" }>) {
  return plan.objective
}
