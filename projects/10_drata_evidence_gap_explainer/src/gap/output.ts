export type ParsedModelOutput =
  | { ok: true; value: { customerMessage: string; nextStep: string } }
  | { ok: false; error: string };

const MAX_MESSAGE_LENGTH = 300;
const MAX_MESSAGE_SENTENCES = 2;
const MAX_NEXT_STEP_LENGTH = 200;

function stripFence(raw: string): string {
  const trimmed = raw.trim();
  const match = /^```(?:json)?\s*([\s\S]*?)\s*```$/i.exec(trimmed);
  return match ? match[1]! : trimmed;
}

function countSentences(text: string): number {
  return text.split(/(?<=[.!?])\s+/).filter((part) => part.length > 0).length;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function parseModelOutput(raw: string): ParsedModelOutput {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stripFence(raw));
  } catch {
    return { ok: false, error: "invalid JSON" };
  }

  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { ok: false, error: "output must be a JSON object" };
  }

  const record = parsed as Record<string, unknown>;
  const customerMessage = nonEmptyString(record.customerMessage);
  const nextStep = nonEmptyString(record.nextStep);

  if (customerMessage === null) return { ok: false, error: "customerMessage must be a non-empty string" };
  if (nextStep === null) return { ok: false, error: "nextStep must be a non-empty string" };

  if (customerMessage.length > MAX_MESSAGE_LENGTH) {
    return { ok: false, error: `customerMessage exceeds ${MAX_MESSAGE_LENGTH} characters` };
  }
  if (countSentences(customerMessage) > MAX_MESSAGE_SENTENCES) {
    return { ok: false, error: `customerMessage exceeds ${MAX_MESSAGE_SENTENCES} sentences` };
  }
  if (nextStep.length > MAX_NEXT_STEP_LENGTH) {
    return { ok: false, error: `nextStep exceeds ${MAX_NEXT_STEP_LENGTH} characters` };
  }
  if (/[\r\n]/.test(nextStep)) return { ok: false, error: "nextStep must be a single line" };

  return { ok: true, value: { customerMessage, nextStep } };
}
