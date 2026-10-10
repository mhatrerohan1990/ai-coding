import type { GapExplanation, GapInput } from "./types.js";

const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export function computeFailureReason(input: GapInput, now: Date): GapExplanation["failureReason"] {
  if (input.integrationStatus === "error") return "integration_error";
  if (input.evidence === null) return "missing_evidence";

  const collectedAt = Date.parse(input.evidence.collectedAt);
  if (Number.isNaN(collectedAt) || now.getTime() - collectedAt > STALE_AFTER_MS) {
    return "stale_evidence";
  }

  return "requirement_not_met";
}
