import type { GapExplanation } from "./types.js";

const STATUS_KEY = /status|state|enabled|compliant|result/i;

function hasSignal(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(hasSignal);
  if (typeof value !== "object" || value === null) return false;

  return Object.entries(value).some(([key, child]) => {
    if (typeof child === "boolean") return true;
    if (STATUS_KEY.test(key) && (typeof child === "string" || typeof child === "number")) return true;
    return hasSignal(child);
  });
}

export function computeNeedsHuman(
  reason: GapExplanation["failureReason"],
  payload: Record<string, unknown>,
): boolean {
  if (reason !== "requirement_not_met") return false;
  return !hasSignal(payload);
}
