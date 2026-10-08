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
- Each model call times out after 8 seconds and is capped at 300 tokens.

## Scripts

| Script              | Description                      |
| ------------------- | -------------------------------- |
| `npm run dev`       | Run with `tsx` in watch mode     |
| `npm run build`     | Compile TypeScript to `dist/`    |
| `npm start`         | Run compiled output              |
| `npm run typecheck` | Type-check without emitting      |
