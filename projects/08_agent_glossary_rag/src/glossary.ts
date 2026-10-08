// Our entire "knowledge base". The bot may ONLY answer from these entries.
export interface Term {
  id: string;
  term: string;
  definition: string;
}

export const glossary: Term[] = [
  {
    id: "agent",
    term: "AI Agent",
    definition:
      "An AI agent is a system where an LLM decides which actions to take to reach a goal. It runs in a loop: observe the situation, choose a tool or action, execute it, look at the result, and repeat until the goal is met or it gives up.",
  },
  {
    id: "llm",
    term: "LLM",
    definition:
      "A Large Language Model is a neural network trained on large amounts of text that predicts the next token. It generates text, but it only knows what was in its training data and the prompt it is given.",
  },
  {
    id: "embedding",
    term: "Embedding",
    definition:
      "An embedding is a list of numbers (a vector) that represents the meaning of a piece of text. Texts with similar meaning get vectors that point in similar directions, which makes semantic comparison possible.",
  },
  {
    id: "vector-db",
    term: "Vector Database",
    definition:
      "A vector database stores embeddings and answers nearest-neighbor queries: given a query vector, it returns the stored items whose vectors are most similar, usually measured with cosine similarity. It enables search by meaning instead of by keyword.",
  },
  {
    id: "rag",
    term: "RAG",
    definition:
      "Retrieval-Augmented Generation works in three steps. First, embed the user's question. Second, retrieve the most similar chunks from a vector database. Third, put those chunks into the LLM prompt and instruct it to answer only from them. This grounds answers in your own data and reduces hallucination.",
  },
  {
    id: "chunking",
    term: "Chunking",
    definition:
      "Chunking is splitting source documents into smaller pieces before embedding them. Chunks that are too large blur meaning and waste prompt space; chunks that are too small lose context. Overlap between chunks helps preserve context at the edges.",
  },
  {
    id: "hallucination",
    term: "Hallucination",
    definition:
      "A hallucination is when an LLM produces confident but false or unsupported information. RAG, strict prompting, and evals that check answers against source data are common ways to reduce and detect it.",
  },
  {
    id: "grounding",
    term: "Grounding",
    definition:
      "Grounding means tying an LLM's answer to trusted source material, so every claim can be traced back to retrieved data rather than to the model's memory.",
  },
  {
    id: "tool",
    term: "Tool Use",
    definition:
      "Tool use (or function calling) lets an LLM request that your code run a function, such as searching a database or calling an API. The model outputs a structured call, your code executes it, and the result is fed back to the model.",
  },
  {
    id: "eval",
    term: "Evals",
    definition:
      "Evals are repeatable tests for AI systems. You write a dataset of questions with expected outcomes, run the system, and score the results. They catch regressions when you change prompts, models, or retrieval settings, because LLM output is non-deterministic and cannot be checked by eyeballing alone.",
  },
  {
    id: "llm-judge",
    term: "LLM-as-Judge",
    definition:
      "LLM-as-judge is an eval technique where a second LLM call grades an answer against criteria, such as whether it is faithful to the retrieved context. It scales better than human review but must itself be validated.",
  },
  {
    id: "top-k",
    term: "Top-K Nearest Neighbors",
    definition:
      "Top-k nearest neighbors means returning the k stored vectors closest to the query vector. For example, with k=3 a search for 'how does RAG work' returns the 3 most similar glossary entries, ranked from best to worst. K controls how much context you retrieve: a small k may miss the answer, a large k adds noise and uses up prompt space.",
  },
  {
    id: "cosine",
    term: "Cosine Similarity",
    definition:
      "Cosine similarity measures how similar two vectors are by the angle between them, giving a score from -1 to 1. A score near 1 means the vectors point the same way and the texts have similar meaning; a score near 0 means they are unrelated. It ignores vector length and compares direction only.",
  },
  {
    id: "similarity-threshold",
    term: "Similarity Threshold",
    definition:
      "A similarity threshold is a minimum score a retrieved result must reach to be used. Top-k always returns k results even when none are relevant, so the threshold filters out weak matches. If nothing passes, the system can say it does not know instead of guessing.",
  },
  {
    id: "exact-search",
    term: "Exact Search",
    definition:
      "Exact search, also called brute force or flat search, compares the query vector against every stored vector and returns the true nearest ones. It is always accurate but its cost grows linearly with the number of vectors, so it suits small collections of up to tens of thousands.",
  },
  {
    id: "ann",
    term: "Approximate Nearest Neighbor",
    definition:
      "Approximate nearest neighbor (ANN) search finds vectors that are very likely among the closest without checking every one. It uses an index structure such as HNSW or IVF to be much faster at large scale, in exchange for occasionally missing a true neighbor. This speed versus accuracy trade-off is called recall.",
  },
  {
    id: "hnsw",
    term: "HNSW",
    definition:
      "HNSW (Hierarchical Navigable Small World) is a popular ANN index. It builds a layered graph where each vector links to nearby vectors. A search starts at a coarse top layer and hops through neighbors toward the query, getting closer at each layer. It is fast but usually kept in memory.",
  },
  {
    id: "metadata-filter",
    term: "Metadata Filtering",
    definition:
      "Metadata filtering restricts a vector search using structured fields stored with each vector, such as tenant ID, document type, or date. For example, a search can be limited to one customer's documents. In multi-tenant SaaS it is essential for keeping one customer's data from appearing in another customer's results.",
  },
  {
    id: "hybrid-search",
    term: "Hybrid Search",
    definition:
      "Hybrid search combines vector search, which matches meaning, with keyword search such as BM25, which matches exact words. Keyword search is better for names, IDs, and rare terms, while vector search is better for paraphrases. Results from both are merged into one ranked list.",
  },
  {
    id: "reranking",
    term: "Reranking",
    definition:
      "Reranking is a second pass after retrieval. First retrieve a larger set, say the top 20, quickly with vector search. Then a more accurate but slower model scores each result against the question and reorders them, and only the best few go into the prompt.",
  },
  {
    id: "context-window",
    term: "Context Window",
    definition:
      "The context window is the maximum amount of text, measured in tokens, an LLM can read in one request, including the system prompt, retrieved chunks, and the question. Retrieved context must fit inside it, which is one reason RAG retrieves only the top-k most relevant chunks instead of everything.",
  },
  {
    id: "prompt",
    term: "System Prompt",
    definition:
      "A system prompt is the instruction block given to an LLM before the user's message. It sets the role, rules, and constraints, for example telling the model to answer only from the provided context.",
  },
];
