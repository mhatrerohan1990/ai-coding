# Control Investigator

Given a reviewer's question about a control, `investigate` gathers facts through a fixed tool surface and returns a `Decision` (`pass | fail | insufficient`). Code owns the loop; the model only plans and labels.

## Setup

Requires Node 22+.

```bash
npm install
```

## Run the tests

Tests use the scripted `FakeModelClient`, so no llama is needed.

```bash
npm test
```

## Typecheck / build

```bash
npx tsc --noEmit   # typecheck only
npm run build      # emit to dist/
```

## Use with the local llama

The default client talks to [Ollama](https://ollama.com) at `http://localhost:11434` using `llama3.1:8b`.

```bash
ollama serve                 # if not already running
ollama pull llama3.1:8b
```

Override with env vars if needed: `LLAMA_URL`, `LLAMA_MODEL`.

```ts
import { investigate, LlamaClient, type Tools } from "./src/investigator";

const tools: Tools = {
  get_evidence: async (controlId) => [/* 0-3 EvidenceHit */],
  get_policy: async (controlId) => null,
};

const decision = await investigate(
  { controlId: "ctrl-1", question: "Is MFA enforced?" },
  tools,
  new LlamaClient(),
);
```

To run without llama, swap in the fake:

```ts
import { FakeModelClient } from "./src/investigator";

const model = new FakeModelClient([
  JSON.stringify({ tools: ["get_evidence"] }),
  JSON.stringify({
    status: "pass",
    citations: ["e1"],
    labels: { e1: "indicates_pass" },
    rationale: "The evidence shows MFA is enforced.",
  }),
]);
```

## How it works

1. **Plan call**: model returns up to 2 tool names as JSON. Code drops unknown names, dedups, caps, and always uses `input.controlId`. An invalid plan means no tools are called.
2. **Execute tools**: `get_evidence` / `get_policy`.
3. **Short-circuit**: no evidence returns `insufficient` without a decide call.
4. **Decide call**: model labels every evidence id `indicates_pass | indicates_fail | irrelevant` and picks a status with citations.
5. **Validate**: zod schema, all ids labeled, unknown citations dropped, `pass`/`fail` needs at least one citation and each citation's label must match the verdict, rationale is one sentence. One retry with the error fed back, then `InvestigationError`.
6. **Conflicts** are computed in code from the labels, never reported by the model.

Limits: 8s and 300 tokens per model call, 20s total (tool calls included). Untrusted text (question, evidence, policy) is escaped and wrapped in tags.

## Layout

```
src/investigator/
  types.ts        types, labels, InvestigationError
  model.ts        ModelClient interface
  llamaClient.ts  Ollama client
  fakeModel.ts    scripted fake
  schemas.ts      zod + decision validation
  conflicts.ts    conflict computation
  prompts.ts      prompt builders + escaping
  investigate.ts  the loop
test/investigate.test.ts
```
