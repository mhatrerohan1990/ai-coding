import { mkdirSync, writeFileSync } from 'node:fs';
import { runTriage } from '../src/triage/pipeline.js';
import { createTriageService } from '../src/triage/factory.js';
import { DATASET } from './dataset.js';
import { score, type CaseResult, type Report } from './score.js';

// Regression guards: set a little below the measured baseline, raise as the prompt improves.
const THRESHOLDS = { category: 0.8, severity: 0.7, oneSentence: 0.9 } as const;

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

function printConfusion(title: string, m: Report['categoryConfusion']) {
  console.log(`\n${title} (rows = expected, columns = predicted)`);
  console.table(m);
}

const service = createTriageService();
const results: CaseResult[] = [];

for (const c of DATASET) {
  try {
    results.push({ case: c, actual: (await runTriage(service, c.ticket)).insight });
  } catch (err) {
    results.push({ case: c, error: err instanceof Error ? err.message : String(err) });
  }
  process.stdout.write(results.at(-1)!.actual ? '.' : 'E');
}

const report = score(results);

console.log(`\n\nProvider: ${process.env.TRIAGE_PROVIDER ?? 'ollama'}   Model: ${process.env.TRIAGE_MODEL ?? 'default'}   Cases: ${report.total}`);
console.log(`category        ${pct(report.category)}`);
console.log(`severity        ${pct(report.severity)}   (within one level: ${pct(report.severityWithinOne)})`);
console.log(`both correct    ${pct(report.exact)}`);
console.log(`one-sentence    ${pct(report.oneSentence)}`);
console.log(`errors          ${report.errors}`);

printConfusion('Category', report.categoryConfusion);
printConfusion('Severity', report.severityConfusion);

if (report.failures.length) {
  console.log('\nFailures');
  for (const f of report.failures) {
    const { expected } = f.case;
    const got = f.actual ? `${f.actual.category}/${f.actual.severity}` : `ERROR ${f.error}`;
    console.log(`- ${f.case.id}: expected ${expected.category}/${expected.severity}, got ${got}`);
    if (f.actual) console.log(`    ${f.actual.rationale}`);
  }
}

// Save every run so prompt changes can be compared over time.
mkdirSync('evals/results', { recursive: true });
const file = `evals/results/${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
writeFileSync(file, JSON.stringify({ report, results }, null, 2));
console.log(`\nSaved ${file}`);

const failed = (Object.keys(THRESHOLDS) as (keyof typeof THRESHOLDS)[]).filter((k) => report[k] < THRESHOLDS[k]);
if (failed.length) {
  console.error(`\nBelow threshold: ${failed.map((k) => `${k} ${pct(report[k])} < ${pct(THRESHOLDS[k])}`).join(', ')}`);
  process.exit(1);
}
