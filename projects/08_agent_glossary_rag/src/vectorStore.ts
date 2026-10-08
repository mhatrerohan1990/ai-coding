import { embed } from "./ollama.js";
import type { Term } from "./glossary.js";

interface Entry {
  doc: Term;
  vector: number[];
}

export interface Hit {
  doc: Term;
  score: number; // cosine similarity, higher = more similar
}

// A vector DB at its simplest: an array of (vector, payload) and a similarity search.
// Real ones (pgvector, Qdrant, ...) do the same thing, plus indexes (HNSW) to make it fast at scale.
export class VectorStore {
  private entries: Entry[] = [];

  async add(docs: Term[]): Promise<void> {
    for (const doc of docs) {
      // Embed term + definition together so searching by either name or meaning works.
      const vector = await embed(`${doc.term}: ${doc.definition}`);
      this.entries.push({ doc, vector });
    }
  }

  async search(query: string, topK = 3): Promise<Hit[]> {
    const q = await embed(query);
    return this.entries
      .map((e) => ({ doc: e.doc, score: cosine(q, e.vector) }))
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
  }

  get size() {
    return this.entries.length;
  }
}

function cosine(a: number[], b: number[]): number {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}
