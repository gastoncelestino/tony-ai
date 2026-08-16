/**
 * Convert a normalized OpenCode tool observation into Kernel evidence.
 *
 * The bridge is intentionally conservative: evidence is only produced when
 * the observation has an explicit task identity and a known success outcome.
 */

import type { ToolExecutionObservation } from "./tool-observation"

export interface ToolExecutionEvidence {
  task_id: string
  tool: string
  claim: string
  success: boolean
  metadata: {
    arguments: Record<string, unknown>
    result: unknown
    error: string | null
  }
}

export function observationToEvidence(
  observation: ToolExecutionObservation,
): ToolExecutionEvidence | null {
  if (observation.task_id === null) return null
  if (observation.success === null) return null

  return {
    task_id: observation.task_id,
    tool: observation.tool,
    claim: observation.success
      ? `Tool ${observation.tool} completed successfully`
      : `Tool ${observation.tool} failed`,
    success: observation.success,
    metadata: {
      arguments: { ...observation.arguments },
      result: observation.result,
      error: observation.error,
    },
  }
}
