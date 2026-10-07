import { finalizeInsight, sanitizeTicket } from './guard.js';
import { applyPlanPriority } from './priority.js';
import type { TriageInsight, TriageRequest } from './schema.js';
import type { TriageService } from './service.js';

export interface TriageOutcome {
  insight: TriageInsight;
  /** Reasons the input was altered before reaching the model; empty when clean. */
  flags: string[];
  /** Severity the model chose, before plan priority was applied. */
  modelSeverity: TriageInsight['severity'];
}

/** sanitize input -> model -> enforce output contract -> apply plan priority. Used by the API and the eval. */
export async function runTriage(service: TriageService, ticket: TriageRequest): Promise<TriageOutcome> {
  const { ticket: clean, flags } = sanitizeTicket(ticket);
  const modelInsight = finalizeInsight(await service.triage(clean));
  return {
    insight: applyPlanPriority(modelInsight, ticket.customerPlan),
    flags,
    modelSeverity: modelInsight.severity,
  };
}
