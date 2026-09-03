import type { Evidence, EvidenceKind, EvidenceLedger } from "./evidence-ledger"

export type EvidenceClaimType =
  | "file_discovery"
  | "file_content"
  | "search"
  | "command"
  | "modification"

export type EvidenceRequirement = {
  kind: EvidenceKind
  target?: string
  tool?: string
  callId?: string
}

export type EvidenceClaim = {
  id: string
  type: EvidenceClaimType
  statement?: string
  requirements?: EvidenceRequirement[]
  evidenceIds?: string[]
}

export type EvidenceGateResult = {
  allowed: boolean
  claimId: string
  matchedEvidenceIds: string[]
  missing: EvidenceRequirement[]
  reason: string
}

const DEFAULT_REQUIREMENTS: Record<EvidenceClaimType, EvidenceKind> = {
  file_discovery: "FILE_DISCOVERED",
  file_content: "FILE_CONTENT_READ",
  search: "SEARCH_RESULT",
  command: "COMMAND_RESULT",
  modification: "FILE_MODIFIED",
}

function normalizeTarget(value: string | undefined) {
  if (!value) return undefined
  return value.replaceAll("\\", "/").replace(/^\.\//, "").replace(/\/$/, "")
}

function targetMatches(requirement: string | undefined, evidence: string | undefined) {
  const required = normalizeTarget(requirement)
  const actual = normalizeTarget(evidence)

  if (!required) return true
  if (!actual) return false
  if (required === actual) return true

  // Relative requirements may match an absolute repository path, but never the reverse.
  return !required.startsWith("/") && actual.endsWith(`/${required}`)
}

function requirementMatches(requirement: EvidenceRequirement, evidence: Evidence) {
  if (evidence.kind !== requirement.kind) return false
  if (requirement.tool && evidence.tool !== requirement.tool) return false
  if (requirement.callId && evidence.callId !== requirement.callId) return false
  return targetMatches(requirement.target, evidence.target)
}

function requirementsForClaim(claim: EvidenceClaim): EvidenceRequirement[] {
  if (claim.requirements?.length) return claim.requirements

  return [{ kind: DEFAULT_REQUIREMENTS[claim.type] }]
}

function findEvidenceForRequirement(
  requirement: EvidenceRequirement,
  evidence: Evidence[],
  preferredIds?: Set<string>,
) {
  return evidence.find((entry) => {
    if (preferredIds && !preferredIds.has(entry.id)) return false
    return requirementMatches(requirement, entry)
  })
}

function evidenceList(source: EvidenceLedger | Evidence[]) {
  return Array.isArray(source) ? source : source.list()
}

export function evaluateEvidenceClaim(
  source: EvidenceLedger | Evidence[],
  claim: EvidenceClaim,
): EvidenceGateResult {
  const requirements = requirementsForClaim(claim)
  const evidence = evidenceList(source)
  const preferredIds = claim.evidenceIds ? new Set(claim.evidenceIds) : undefined
  const matchedEvidenceIds: string[] = []
  const missing: EvidenceRequirement[] = []

  for (const requirement of requirements) {
    const match = findEvidenceForRequirement(requirement, evidence, preferredIds)
    if (!match) {
      missing.push(requirement)
      continue
    }

    if (!matchedEvidenceIds.includes(match.id)) matchedEvidenceIds.push(match.id)
  }

  if (missing.length === 0) {
    return {
      allowed: true,
      claimId: claim.id,
      matchedEvidenceIds,
      missing: [],
      reason: "All required evidence is present and matches the claim requirements",
    }
  }

  return {
    allowed: false,
    claimId: claim.id,
    matchedEvidenceIds,
    missing,
    reason: `Evidence gate blocked claim '${claim.id}': ${missing.length} requirement(s) are not satisfied`,
  }
}

export function evaluateEvidenceClaims(
  source: EvidenceLedger | Evidence[],
  claims: EvidenceClaim[],
) {
  return claims.map((claim) => evaluateEvidenceClaim(source, claim))
}

export function assertEvidenceClaim(source: EvidenceLedger | Evidence[], claim: EvidenceClaim) {
  const result = evaluateEvidenceClaim(source, claim)
  if (!result.allowed) {
    throw new Error(result.reason)
  }
  return result
}
