import { SEVERITIES, type TriageInsight, type TriageRequest } from './schema.js';

/**
 * Plan priority: enterprise > pro > free. Applied in code, after the model, so the LLM only judges
 * the ticket on its merits and the adjustment is testable and auditable.
 * - enterprise: severity up one level (capped at high)
 * - pro: unchanged
 * - free: medium drops to low; high is never demoted (data loss and security stay high on any plan)
 */
export function applyPlanPriority(insight: TriageInsight, plan: TriageRequest['customerPlan']): TriageInsight {
  const i = SEVERITIES.indexOf(insight.severity);
  let next = i;
  if (plan === 'enterprise') next = Math.min(i + 1, SEVERITIES.length - 1);
  else if (plan === 'free' && insight.severity === 'medium') next = 0;
  return { ...insight, severity: SEVERITIES[next]! };
}
