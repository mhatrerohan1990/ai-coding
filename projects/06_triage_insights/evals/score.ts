import { CATEGORIES, SEVERITIES, type TriageInsight, type TriageRequest } from '../src/triage/schema.js';

export interface EvalCase {
  id: string;
  ticket: TriageRequest;
  expected: Pick<TriageInsight, 'category' | 'severity'>;
  tags?: string[];
}

export interface CaseResult {
  case: EvalCase;
  actual?: TriageInsight;
  /** Set when the service threw; counted as wrong on every metric. */
  error?: string;
}

type Confusion = Record<string, Record<string, number>>;

export interface Report {
  total: number;
  errors: number;
  category: number;
  severity: number;
  /** Both category and severity correct. */
  exact: number;
  /** Severity is ordinal, so "high vs medium" is a smaller miss than "high vs low". */
  severityWithinOne: number;
  /** Share of answered cases whose rationale is a single sentence. */
  oneSentence: number;
  /** confusion[expected][predicted] = count */
  categoryConfusion: Confusion;
  severityConfusion: Confusion;
  failures: CaseResult[];
}

/** Heuristic: no sentence-ending punctuation followed by more text. */
export function isOneSentence(text: string): boolean {
  const t = text.trim();
  return t.length > 0 && !/[.!?]\s+\S/.test(t);
}

function emptyConfusion(labels: readonly string[]): Confusion {
  return Object.fromEntries(labels.map((e) => [e, Object.fromEntries([...labels, 'error'].map((p) => [p, 0]))]));
}

export function score(results: CaseResult[]): Report {
  const total = results.length;
  const categoryConfusion = emptyConfusion(CATEGORIES);
  const severityConfusion = emptyConfusion(SEVERITIES);
  let category = 0, severity = 0, exact = 0, severityWithinOne = 0, answered = 0, oneSentence = 0;
  const failures: CaseResult[] = [];

  for (const r of results) {
    const { expected } = r.case;
    const a = r.actual;
    categoryConfusion[expected.category]![a?.category ?? 'error']!++;
    severityConfusion[expected.severity]![a?.severity ?? 'error']!++;

    if (!a) {
      failures.push(r);
      continue;
    }
    answered++;
    const catOk = a.category === expected.category;
    const sevOk = a.severity === expected.severity;
    if (catOk) category++;
    if (sevOk) severity++;
    if (catOk && sevOk) exact++;
    else failures.push(r);
    if (Math.abs(SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(expected.severity)) <= 1) severityWithinOne++;
    if (isOneSentence(a.rationale)) oneSentence++;
  }

  const rate = (n: number, d: number) => (d === 0 ? 0 : n / d);
  return {
    total,
    errors: results.filter((r) => r.error).length,
    category: rate(category, total),
    severity: rate(severity, total),
    exact: rate(exact, total),
    severityWithinOne: rate(severityWithinOne, total),
    oneSentence: rate(oneSentence, answered),
    categoryConfusion,
    severityConfusion,
    failures,
  };
}
