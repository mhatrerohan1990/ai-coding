import { findLeaks } from "./leak.js";
import type { ModelClient } from "./model.js";
import { computeNeedsHuman } from "./needsHuman.js";
import { parseModelOutput } from "./output.js";
import { buildGapPrompt, GAP_SYSTEM } from "./prompts.js";
import { computeFailureReason } from "./reason.js";
import { collectSecretValues, redactPayload } from "./redact.js";
import { GapExplainError, type GapExplanation, type GapInput } from "./types.js";

const MAX_TOKENS = 200;
const TIMEOUT_MS = 8000;

type Attempt =
  | { ok: true; customerMessage: string; nextStep: string }
  | { ok: false; code: "invalid_output" | "secret_leak"; message: string; feedback: string };

async function callModel(model: ModelClient, prompt: string): Promise<string> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;

  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new GapExplainError("timeout", `model did not respond within ${TIMEOUT_MS}ms`));
      controller.abort();
    }, TIMEOUT_MS);
  });

  try {
    return await Promise.race([
      model.complete({ system: GAP_SYSTEM, prompt, maxTokens: MAX_TOKENS, signal: controller.signal }),
      timeout,
    ]);
  } catch (error) {
    if (error instanceof GapExplainError) throw error;
    throw new GapExplainError("model_error", "model request failed", { cause: error });
  } finally {
    clearTimeout(timer);
  }
}

async function attempt(model: ModelClient, prompt: string, secrets: string[]): Promise<Attempt> {
  const raw = await callModel(model, prompt);

  const parsed = parseModelOutput(raw);
  if (!parsed.ok) {
    return {
      ok: false,
      code: "invalid_output",
      message: `model output was invalid: ${parsed.error}`,
      feedback: `Your previous reply was rejected: ${parsed.error}. Reply again with only the JSON object.`,
    };
  }

  const { customerMessage, nextStep } = parsed.value;
  if (findLeaks(`${customerMessage}\n${nextStep}`, secrets).length > 0) {
    return {
      ok: false,
      code: "secret_leak",
      message: "model output repeated a secret value from the evidence",
      feedback:
        "Your previous reply repeated a secret value from the evidence. Do not repeat secret values. Reply again with only the JSON object.",
    };
  }

  return { ok: true, customerMessage, nextStep };
}

export async function explainGap(
  input: GapInput,
  model: ModelClient,
  now: Date = new Date(),
): Promise<GapExplanation> {
  const failureReason = computeFailureReason(input, now);

  const rawPayload = input.evidence?.payload ?? {};
  const redacted = redactPayload(rawPayload);
  const secrets = collectSecretValues(rawPayload);

  const needsHuman = computeNeedsHuman(failureReason, redacted);
  const prompt = buildGapPrompt(input.control, failureReason, redacted);

  let result = await attempt(model, prompt, secrets);
  if (!result.ok) {
    result = await attempt(model, `${prompt}\n\n${result.feedback}`, secrets);
  }
  if (!result.ok) throw new GapExplainError(result.code, result.message);

  return {
    failureReason,
    customerMessage: result.customerMessage,
    nextStep: result.nextStep,
    needsHuman,
  };
}
