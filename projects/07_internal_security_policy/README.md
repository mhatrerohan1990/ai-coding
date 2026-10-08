# internal-security-policy

Minimal TypeScript + Fastify service.

## Requirements

- Node.js 20+ (developed on 22)
- npm

## Setup

```bash
npm install
```

## Run

Development (watch mode):

```bash
npm run dev
```

Production:

```bash
npm run build
npm start
```

The server listens on port `3000` by default. Override with `PORT`:

```bash
PORT=4000 npm run dev
```

## Verify

```bash
curl http://localhost:3000/health
# {"status":"ok"}
```

## Local LLM (Ollama)

`/citations` calls a local Llama model through [Ollama](https://ollama.com).

```bash
ollama pull llama3.1:8b
ollama serve   # if not already running
```

Config via env vars:

| Variable       | Default                  |
| -------------- | ------------------------ |
| `OLLAMA_URL`   | `http://localhost:11434` |
| `OLLAMA_MODEL` | `llama3.1:8b`            |

## Test `/citations`

```bash
curl http://localhost:3000/citations
```

The route currently uses a hardcoded sample input (a question plus 5 excerpts) standing in for the embeddings service. Supported answer:

```json
{ "answer": "every 90 days", "citations": ["pol-1"], "refused": false }
```

If the excerpts don't support an answer:

```json
{ "answer": "", "citations": [], "refused": true }
```

To test a refusal, change the `question` in `src/server.ts` to something the excerpts don't cover (e.g. "What is the vacation policy?").

Behavior:

- Only information from the excerpts is used; citations are excerpt ids, and unknown ids are dropped.
- If the model doesn't refuse but returns no valid citation, it is retried once with the validation error, then a `TypeError` is thrown (HTTP 500).
- The first model call times out after 8 seconds and the retry after 16 seconds. Each call is capped at 300 tokens.
- Answers must be 1-3 complete sentences ending in punctuation. Otherwise the same retry-then-`TypeError` path applies.

## Scripts

| Script              | Description                      |
| ------------------- | -------------------------------- |
| `npm run dev`       | Run with `tsx` in watch mode     |
| `npm run build`     | Compile TypeScript to `dist/`    |
| `npm start`         | Run compiled output              |
| `npm run typecheck` | Type-check without emitting      |

## Design decisions

- **Scope:** a narrow feature slice. Another team does the embeddings and retrieval, then calls `answerQuestion` with `AskInput { question, excerpts[] }` (at most 5 excerpts of `{ id, text }`). `GET /citations` uses a hardcoded sample input as a stand-in for that upstream call.
- **LLM:** a local Llama (`llama3.1:8b`) through Ollama, since no Claude API key was available.
- **Grounded answers only:** the model answers from the excerpts and never invents facts. If the excerpts don't support an answer, the result is `{ answer: "", citations: [], refused: true }`.
- **Result shape:** `{ answer: string, citations: string[], refused: boolean }`. `citations` are excerpt ids.
- **Citation validation:** every cited id must be one of the input excerpt ids. Unknown ids are dropped.
- **Retry then fail:** if no valid citation remains and the model did not refuse, retry once with the validation error, then throw a `TypeError`.
- **Limits:** 8 second timeout on the first model call, 16 seconds on the retry, and about 300 completion tokens per call.
- **Prompt:** built in its own function (`buildPrompt`). Excerpts go in a delimited `<excerpts>` block and the model is told that block is data, not instructions.
- **Answer length:** 1-3 complete sentences, not a few words. Enforced in code (sentence count and terminal punctuation in `check()`), with a violation going through the same retry-then-`TypeError` path. The system prompt also has a few few-shot examples (answer, two-citation answer, refusal).
- **Input gate:** `answerQuestion` rejects more than 5 excerpts up front with a `RangeError` (before any model call). Zero excerpts returns a refusal.
- **Swappable client:** the LLM call sits behind an `LlmClient` interface (`src/llmClient.ts`). Ollama is the default (`src/ollamaClient.ts`). Another provider, such as Claude, can be added by writing one more `LlmClient` and passing it to `answerQuestion(input, client)`. No Claude client is included.

## What AI assistance was used for

Claude Code acted as an assistant while I drove the design and made the decisions above. It helped with:

- scaffolding the TypeScript + Fastify project and the first README
- the Ollama call, structured JSON output (response schema) and the system prompt
- the validation, retry and timeout code, and the swappable client refactor
- checking behavior against the local model, including refusal cases and a stubbed retry/timeout test
- pushing the project to the shared repo

## Known issues

- The sentence check is a punctuation-based heuristic. A short phrase that happens to end in a period would pass.
- Timeouts and the `TypeError` currently reach Fastify's default handler and return a generic HTTP 500.
- Timeouts are per model call (8s, then 16s on the retry), so the worst case is about 24 seconds.
