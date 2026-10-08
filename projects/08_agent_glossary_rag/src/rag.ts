import { generate } from "./ollama.js";
import type { VectorStore, Hit } from "./vectorStore.js";

// Below this similarity we say "I don't know" WITHOUT calling the LLM.
// Tune it using the evals: too high = refuses valid questions, too low = lets off-topic through.
export const MIN_SCORE = Number(process.env.MIN_SCORE ?? 0.5);
export const NO_ANSWER = "I don't have that in my glossary.";

const SYSTEM = `You answer questions about AI agent terminology using ONLY the CONTEXT provided.
Rules:
- Use nothing from your own knowledge. If the CONTEXT does not contain the answer, reply exactly: "${NO_ANSWER}"
- Be concise (max 4 sentences).
- Do not mention the word "context" in your answer.`;

export interface RagResult {
  answer: string;
  grounded: boolean; // false = we refused
  sources: { id: string; term: string; score: number }[];
}

export async function ask(store: VectorStore, question: string): Promise<RagResult> {
  // 1. RETRIEVE: embed the question, find nearest glossary entries.
  const hits = await store.search(question, 3);
  const sources = hits.map((h) => ({ id: h.doc.id, term: h.doc.term, score: round(h.score) }));

  // 2. GUARDRAIL #1: nothing relevant retrieved -> refuse, no LLM call at all.
  const relevant = hits.filter((h) => h.score >= MIN_SCORE);
  if (relevant.length === 0) return { answer: NO_ANSWER, grounded: false, sources };

  // 3. AUGMENT + GENERATE: stuff retrieved text into the prompt.
  //    GUARDRAIL #2: the system prompt forbids using outside knowledge.
  const answer = await generate(SYSTEM, buildPrompt(question, relevant));
  return { answer, grounded: !answer.includes(NO_ANSWER), sources };
}

function buildPrompt(question: string, hits: Hit[]): string {
  const context = hits.map((h) => `[${h.doc.term}] ${h.doc.definition}`).join("\n\n");
  return `CONTEXT:\n${context}\n\nQUESTION: ${question}`;
}

const round = (n: number) => Math.round(n * 1000) / 1000;
