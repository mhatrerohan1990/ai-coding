# Agent Glossary RAG

A small Fastify + TypeScript project for seeing embeddings, a vector store, RAG, and evals work end to end. It answers questions about AI agent terminology using **only** a built-in glossary, and refuses everything else. Embeddings and answers both come from a local Ollama.

## Prerequisites

- Node 20+ (developed on 22)
- [Ollama](https://ollama.com) running locally with two models:

```bash
ollama pull nomic-embed-text   # embeddings
ollama pull llama3.1:8b        # answer generation
```

Check Ollama is up: `curl localhost:11434/api/tags`

## Run

```bash
npm install
npm start          # http://localhost:3000
```

Startup embeds the 22 glossary terms (a few seconds), then serves:

| Route | What |
|---|---|
| `GET /` | Web UI |
| `POST /ask` | `{"question": "..."}` returns the answer, a `grounded` flag, and the retrieved sources with scores |
| `GET /health` | Number of indexed terms |

```bash
curl localhost:3000/ask -H 'content-type: application/json' \
  -d '{"question":"how does rag work?"}'
```

## Evals

```bash
npm run eval       # exits non-zero if any case fails
```

Cases in `src/evals.ts` check three things: the right glossary entry is retrieved (vector search), the answer contains expected facts (keyword check), and out-of-scope questions are refused.

## How it works

```
question -> embed -> top-k search -> score >= MIN_SCORE? -> prompt with chunks -> llama -> answer
                                          |
                                          no -> "I don't have that in my glossary." (no LLM call)
```

| File | Role |
|---|---|
| `src/glossary.ts` | The knowledge base. Add or edit terms here. |
| `src/ollama.ts` | `embed()` and `generate()` calls to Ollama |
| `src/vectorStore.ts` | In-memory vector store: cosine similarity, top-k search |
| `src/rag.ts` | Retrieve, apply the threshold, build the prompt, generate |
| `src/server.ts` | Fastify routes |
| `src/evals.ts` | Eval runner |
| `public/index.html` | UI (no build step) |

Strict grounding has two guardrails: a similarity threshold that skips the LLM when nothing relevant is retrieved, and a system prompt that forbids outside knowledge.

## Configuration

Environment variables, all optional:

| Var | Default | Notes |
|---|---|---|
| `PORT` | `3000` | |
| `OLLAMA_URL` | `http://localhost:11434` | |
| `EMBED_MODEL` | `nomic-embed-text` | Changing it requires re-embedding, which happens on every start anyway |
| `CHAT_MODEL` | `llama3.1:8b` | |
| `MIN_SCORE` | `0.5` | Similarity threshold. If you change it, update `THRESHOLD` in `public/index.html` so the grey bars match. |

Example: `MIN_SCORE=0.7 npm run eval`

## Things to try

- Remove the "ONLY the CONTEXT" rule in `src/rag.ts` and run the evals. The refusal cases should start failing.
- Raise `MIN_SCORE` until valid questions get refused, then lower it until off-topic ones get through.
- Add a term to the glossary, add an eval case for it, and run `npm run eval`.

## Limitations

- The vector store is in memory and exact (brute force). That is fine for dozens of documents. Use pgvector or Qdrant for more.
- Answer checks are keyword-based, so they can reject a correct answer that is worded differently. An LLM-as-judge check is the usual next step.
