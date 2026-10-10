const SENSITIVE_KEY = /secret|token|password|key|credential/i;
const MAX_STRING_LENGTH = 200;
const UNSAFE_KEYS = new Set(["__proto__", "constructor", "prototype"]);

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function redactValue(value: unknown): unknown {
  if (typeof value === "string") return value.slice(0, MAX_STRING_LENGTH);
  if (Array.isArray(value)) return value.map(redactValue);
  if (isPlainObject(value)) return redactPayload(value);
  return value;
}

export function redactPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (UNSAFE_KEYS.has(key) || SENSITIVE_KEY.test(key)) continue;
    result[key] = redactValue(value);
  }
  return result;
}

function collectStrings(value: unknown, out: string[]): void {
  if (typeof value === "string") out.push(value);
  else if (Array.isArray(value)) value.forEach((item) => collectStrings(item, out));
  else if (isPlainObject(value)) Object.values(value).forEach((item) => collectStrings(item, out));
}

function collectSecrets(value: unknown, out: string[]): void {
  if (Array.isArray(value)) {
    value.forEach((item) => collectSecrets(item, out));
  } else if (isPlainObject(value)) {
    for (const [key, child] of Object.entries(value)) {
      if (SENSITIVE_KEY.test(key)) collectStrings(child, out);
      else collectSecrets(child, out);
    }
  }
}

export function collectSecretValues(payload: Record<string, unknown>): string[] {
  const out: string[] = [];
  collectSecrets(payload, out);
  return out;
}
