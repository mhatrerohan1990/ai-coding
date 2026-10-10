# fastify-ts-app

TypeScript project with Fastify and the `src/gap` evidence-gap modules.

## Requirements

- Node.js 22+
- npm

## Setup

```sh
npm install
```

## Run

Dev server (watch mode, port 3000):

```sh
npm run dev
```

Check it:

```sh
curl http://localhost:3000/health
```

Build and run the compiled output:

```sh
npm run build
npm start
```

## Test

```sh
npx vitest run
```

## Typecheck

```sh
npx tsc --noEmit
```

## Flow

`explainGap(input, model, now?)` in `src/gap/explainGap.ts`:

1. `computeFailureReason(input, now)` picks `failureReason`: `integration_error`, `missing_evidence`, `stale_evidence` (older than 24h or unparseable timestamp), otherwise `requirement_not_met`.
2. `redactPayload` drops secret-like keys and truncates long strings. `collectSecretValues` gathers the secret values from the raw payload for the leak check.
3. `computeNeedsHuman(reason, redacted)` decides `needsHuman` from the redacted payload.
4. `buildGapPrompt` builds the prompt from the control, the reason and the redacted payload inside `<evidence_payload>` tags.
5. The model is called with `maxTokens: 200` and an 8000ms timeout. A timeout throws `timeout` immediately.
6. `parseModelOutput` validates the reply (JSON, both fields non-empty, length and sentence limits).
7. `findLeaks` checks `customerMessage` and `nextStep` against the collected secrets.
8. If parsing fails or a secret leaked, steps 5 to 7 run once more with the error added to the prompt (never the secret). A second failure throws `invalid_output` or `secret_leak`.
9. The result is `{ failureReason, customerMessage, nextStep, needsHuman }`. The first two model fields come from the reply, and the other two come from code.

```
input
  |
  +--> computeFailureReason --------------------------+
  |                                                   |
  +--> redactPayload --+--> computeNeedsHuman --------+
  |                    |                              |
  |                    +--> buildGapPrompt            |
  |                              |                    |
  +--> collectSecretValues       v                    |
            |            model.complete (8s timeout)  |
            |                    |                    |
            |            parseModelOutput             |
            |                    |                    |
            +-------------> findLeaks                 |
                                 | ok (one retry on failure)
                                 v                    |
                       customerMessage, nextStep      |
                                 |                    |
                                 +----> GapExplanation <--+
```

## Design decisions

- **Code decides, the model only writes words.** `failureReason` (`reason.ts`) and `needsHuman` (`needsHuman.ts`) are computed in code. The model writes only `customerMessage` and `nextStep`; any other keys in its reply are ignored and never copied into the result.
- **Evidence payload is untrusted.** It is redacted (`redact.ts`) before the model sees it, and the raw payload is never passed to the model. The payload sits inside `<evidence_payload>` tags, and any tag-like text inside it is escaped so it can't break out of the block.
- **`needsHuman` uses the redacted payload.** A signal that only exists under a secret-like key (for example `apiKeyValid: true`) doesn't count.
- **The reply is checked for leaks.** Secret values collected from the raw payload are searched for in the model's reply (`leak.ts`). A parse failure or a leak triggers one retry; the retry prompt never contains the secret. A second failure throws `GapExplainError` (`invalid_output` or `secret_leak`).
- **Timeouts don't retry.** Each model call is raced against an 8000ms timeout and an abort signal, so a client that ignores the signal still times out. A timeout throws `GapExplainError` (`timeout`) immediately. Other model client errors throw `model_error` with the original error as `cause`.
- **The model client is swappable.** `explainGap(input, model)` takes any `ModelClient` (`model.ts`). `OllamaModelClient` talks to a local Llama; tests use `FakeModelClient`.
