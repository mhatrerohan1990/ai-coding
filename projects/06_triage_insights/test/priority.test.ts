import { describe, expect, it } from 'vitest';
import { buildApp } from '../src/app.js';
import { applyPlanPriority } from '../src/triage/priority.js';
import { PLANS, SEVERITIES } from '../src/triage/schema.js';

const at = (severity: (typeof SEVERITIES)[number]) => ({ category: 'bug' as const, severity, rationale: 'Because.' });

describe('applyPlanPriority', () => {
  it.each([
    // plan, model severity, expected
    ['enterprise', 'low', 'medium'],
    ['enterprise', 'medium', 'high'],
    ['enterprise', 'high', 'high'],
    ['pro', 'low', 'low'],
    ['pro', 'medium', 'medium'],
    ['pro', 'high', 'high'],
    ['free', 'low', 'low'],
    ['free', 'medium', 'low'],
    ['free', 'high', 'high'],
  ] as const)('%s plan: model %s -> %s', (plan, model, expected) => {
    expect(applyPlanPriority(at(model), plan).severity).toBe(expected);
  });

  it('never lowers an enterprise ticket or raises a free one, so plans stay ordered', () => {
    const rank = (s: string) => SEVERITIES.indexOf(s as never);
    for (const s of SEVERITIES) {
      const [free, pro, ent] = (['free', 'pro', 'enterprise'] as const).map((p) => rank(applyPlanPriority(at(s), p).severity));
      expect(ent).toBeGreaterThanOrEqual(pro!);
      expect(pro).toBeGreaterThanOrEqual(free!);
    }
    expect(PLANS).toHaveLength(3);
  });

  it('keeps category and rationale untouched', () => {
    expect(applyPlanPriority(at('low'), 'enterprise')).toEqual({ category: 'bug', severity: 'medium', rationale: 'Because.' });
  });
});

describe('POST /triage/v1/insights plan priority', () => {
  const payload = { id: 'T-9', subject: 'Reports are slow', body: 'Reports take a minute to load.', customerPlan: 'enterprise' };

  it('raises severity for enterprise and exposes the model severity in a header', async () => {
    const app = buildApp({ triageService: { triage: async () => at('medium') } });
    const res = await app.inject({ method: 'POST', url: '/triage/v1/insights', payload });
    expect(res.json().severity).toBe('high');
    expect(res.headers['x-triage-model-severity']).toBe('medium');
    await app.close();
  });

  it('adds no header when the plan changes nothing', async () => {
    const app = buildApp({ triageService: { triage: async () => at('medium') } });
    const res = await app.inject({ method: 'POST', url: '/triage/v1/insights', payload: { ...payload, customerPlan: 'pro' } });
    expect(res.json().severity).toBe('medium');
    expect(res.headers['x-triage-model-severity']).toBeUndefined();
    await app.close();
  });
});
