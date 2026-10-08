import { glossary } from "./glossary.js";
import { VectorStore } from "./vectorStore.js";
import { ask, NO_ANSWER, MIN_SCORE } from "./rag.js";

// Three kinds of checks, from cheapest/most deterministic to fuzziest:
//  1. retrieval  - did the right glossary entry come back? (tests the vector DB, no LLM)
//  2. answer     - does the answer mention facts that are in the source? (keyword check)
//  3. refusal    - for out-of-scope questions, did we refuse instead of making stuff up?
interface Case {
  question: string;
  expectTerm?: string; // glossary id that must be in the top 3 results
  mustInclude?: string[]; // answer must contain at least one of these (case-insensitive)
  shouldRefuse?: boolean;
}

const cases: Case[] = [
  { question: "How does RAG work?", expectTerm: "rag", mustInclude: ["retrieve", "vector"] },
  { question: "What is an embedding?", expectTerm: "embedding", mustInclude: ["vector", "numbers"] },
  { question: "Why do we split documents into pieces?", expectTerm: "chunking", mustInclude: ["chunk", "split"] },
  { question: "How do I test whether my AI system got worse after a prompt change?", expectTerm: "eval", mustInclude: ["eval", "regression"] },
  { question: "When a model makes up false facts, what is that called?", expectTerm: "hallucination", mustInclude: ["hallucination"] },
  { question: "How can a model call my functions?", expectTerm: "tool", mustInclude: ["function", "tool"] },
  { question: "What does top-k mean in vector search?", expectTerm: "top-k", mustInclude: ["closest", "nearest"] },
  { question: "How is similarity between two vectors scored?", expectTerm: "cosine", mustInclude: ["angle", "cosine", "-1 to 1"] },
  { question: "Why is HNSW fast?", expectTerm: "hnsw", mustInclude: ["graph", "layer"] },
  { question: "How do I stop one customer seeing another customer's documents in search?", expectTerm: "metadata-filter", mustInclude: ["filter", "tenant"] },
  // Out of scope: not in our data, must refuse (even though llama knows the answers!)
  { question: "What is the capital of France?", shouldRefuse: true },
  { question: "How do I bake sourdough bread?", shouldRefuse: true },
  { question: "What is the difference between supervised and unsupervised learning?", shouldRefuse: true },
];

const store = new VectorStore();
await store.add(glossary);

console.log(`MIN_SCORE=${MIN_SCORE}\n`);
let passed = 0;

for (const c of cases) {
  const r = await ask(store, c.question);
  const failures: string[] = [];

  if (c.expectTerm && !r.sources.some((s) => s.id === c.expectTerm)) {
    failures.push(`retrieval: expected "${c.expectTerm}" in top 3, got [${r.sources.map((s) => s.id)}]`);
  }
  if (c.mustInclude && !c.mustInclude.some((k) => r.answer.toLowerCase().includes(k))) {
    failures.push(`answer: expected one of [${c.mustInclude}]`);
  }
  if (c.shouldRefuse && r.answer !== NO_ANSWER) {
    failures.push(`refusal: should have refused but answered: "${r.answer.slice(0, 80)}..."`);
  }
  if (!c.shouldRefuse && r.answer === NO_ANSWER) {
    failures.push("refusal: refused a question that is in the glossary");
  }

  const ok = failures.length === 0;
  if (ok) passed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${c.question}  (top: ${r.sources[0].id} ${r.sources[0].score})`);
  failures.forEach((f) => console.log(`        - ${f}`));
}

console.log(`\n${passed}/${cases.length} passed`);
process.exit(passed === cases.length ? 0 : 1);
