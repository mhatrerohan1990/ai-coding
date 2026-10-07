import { describe, expect, it } from 'vitest';
import { DATASET } from '../evals/dataset.js';
import { isOneSentence, score, type CaseResult, type EvalCase } from '../evals/score.js';
import { EXAMPLES } from '../src/triage/prompt.js';
import { CATEGORIES, SEVERITIES, triageRequestSchema } from '../src/triage/schema.js';

const c = (category: EvalCase['expected']['category'], severity: EvalCase['expected']['severity']): EvalCase => ({
  id: `${category}-${severity}`,
  ticket: { id: 'T-1', subject: 't', body: 'd', customerPlan: 'pro' },
  expected: { category, severity },
});
const ok = (k: EvalCase, category = k.expected.category, severity = k.expected.severity): CaseResult => ({
  case: k,
  actual: { category, severity, rationale: 'One sentence.' },
});

describe('score', () => {
  it('computes accuracy, adjacent severity, and counts errors as wrong', () => {
    const results: CaseResult[] = [
      ok(c('bug', 'high')), // exact
      ok(c('bug', 'high'), 'bug', 'medium'), // severity off by one
      ok(c('billing', 'low'), 'other', 'high'), // both wrong, severity off by two
      { case: c('access', 'low'), error: 'boom' }, // service error
    ];
    const r = score(results);
    expect(r.total).toBe(4);
    expect(r.errors).toBe(1);
    expect(r.category).toBe(2 / 4);
    expect(r.severity).toBe(1 / 4);
    expect(r.exact).toBe(1 / 4);
    expect(r.severityWithinOne).toBe(2 / 4);
    expect(r.failures).toHaveLength(3);
  });

  it('fills the confusion matrix as expected -> predicted', () => {
    const r = score([ok(c('bug', 'high'), 'other', 'high'), { case: c('bug', 'low'), error: 'x' }]);
    expect(r.categoryConfusion.bug!.other).toBe(1);
    expect(r.categoryConfusion.bug!.error).toBe(1);
  });

  it('handles an empty run without dividing by zero', () => {
    expect(score([]).category).toBe(0);
  });
});

describe('isOneSentence', () => {
  it.each([
    ['A duplicate charge on invoice #4821 needs a refund.', true],
    ['No terminal punctuation', true],
    ['First sentence. Second sentence.', false],
    ['', false],
  ])('%j -> %s', (text, expected) => expect(isOneSentence(text)).toBe(expected));
});

describe('DATASET', () => {
  it('has unique ids and schema-valid tickets', () => {
    expect(new Set(DATASET.map((d) => d.id)).size).toBe(DATASET.length);
    for (const d of DATASET) expect(triageRequestSchema.safeParse(d.ticket).success, d.id).toBe(true);
  });

  it('covers every category and severity', () => {
    for (const cat of CATEGORIES) expect(DATASET.some((d) => d.expected.category === cat), cat).toBe(true);
    for (const sev of SEVERITIES) expect(DATASET.some((d) => d.expected.severity === sev), sev).toBe(true);
  });

  it('does not reuse the prompt\'s few-shot examples', () => {
    const titles = new Set(EXAMPLES.map((e) => e.ticket.subject));
    for (const d of DATASET) expect(titles.has(d.ticket.subject), d.id).toBe(false);
  });
});
