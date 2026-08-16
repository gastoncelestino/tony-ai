/**
 * Convert a normalized OpenCode tool observation into Kernel evidence.
 *
 * The bridge is intentionally conservative: evidence is only produced when
 * the observation has an explicit task identity and a known success outcome.
 */

import type { ToolExecutionObservation } from "./tool-observation"

export interface ToolExecutionEvidence {
  task_id: string
  evidence: {
    type: "command"
    claim: string
    command: string
    exit_code: 0 | 1
    stdout: string | null
    stderr: string | null
    metadata: {
      tool: string
      arguments: Record<string, unknown>
      result: unknown
      error: string | null
    }
  }
}

export function observationToEvidence(
  observation: ToolExecutionObservation,
): ToolExecutionEvidence | null {
  if (observation.task_id === null) return null
  if (observation.success === null) return null

  return {
    task_id: observation.task_id,
    evidence: {
      type: "command",
      claim: observation.success
        ? `Tool ${observation.tool} completed successfully`
        : `Tool ${observation.tool} failed`,
      command: observation.tool,
      exit_code: observation.success ? 0 : 1,
      stdout: null,
      stderr: observation.error,
      metadata: {
        tool: observation.tool,
        arguments: { ...observation.arguments },
        result: observation.result,
        error: observation.error,
      },
    },
  }
}
