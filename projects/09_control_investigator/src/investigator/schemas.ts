import { z } from "zod";
import { LABELS, TOOL_NAMES, type Label, type ToolName } from "./types";

export const PlanSchema = z.object({
  tools: z.array(z.string()),
});

const DecisionResponseSchema = z.object({
  status: z.enum(["pass", "fail", "insufficient"]),
  citations: z.array(z.string()),
  labels: z.record(z.string(), z.enum(LABELS)),
  rationale: z.string(),
});

const MAX_PLANNED_TOOLS = 2;

// Filters unknown names, dedups, caps. Returns [] when the plan is invalid.
export function parsePlan(raw: string): ToolName[] {
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return [];
  }
  const parsed = PlanSchema.safeParse(json);
  if (!parsed.success) return [];
  const known = new Set<string>(TOOL_NAMES);
  const picked: ToolName[] = [];
  for (const name of parsed.data.tools) {
    if (known.has(name) && !picked.includes(name as ToolName)) {
      picked.push(name as ToolName);
    }
    if (picked.length === MAX_PLANNED_TOOLS) break;
  }
  return picked;
}

function isSingleSentence(text: string): boolean {
  if (text.length === 0 || text.length > 400) return false;
  if (/[\r\n]/.test(text)) return false;
  const terminators = [...text.matchAll(/[.!?]+(\s|$)/g)];
  if (terminators.length === 0) return true;
  return terminators.length === 1 && text.endsWith(terminators[0][0].trimEnd());
}

export type ValidDecision = {
  status: "pass" | "fail" | "insufficient";
  citations: string[];
  labels: Record<string, Label>;
  rationale: string;
};

export type ValidationResult =
  | { ok: true; value: ValidDecision }
  | { ok: false; error: string };

export function validateDecision(raw: string, evidenceIds: string[]): ValidationResult {
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return { ok: false, error: "reply was not valid JSON" };
  }
  const parsed = DecisionResponseSchema.safeParse(json);
  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`)
      .join("; ");
    return { ok: false, error: `schema validation failed: ${issues}` };
  }
  const { status, labels, rationale } = parsed.data;

  const missing = evidenceIds.filter((id) => !Object.hasOwn(labels, id));
  if (missing.length > 0) {
    return { ok: false, error: `missing labels for evidence ids: ${missing.join(", ")}` };
  }

  const known = new Set(evidenceIds);
  const citations = [...new Set(parsed.data.citations)].filter((id) => known.has(id));

  const trimmed = rationale.trim();
  if (!isSingleSentence(trimmed)) {
    return { ok: false, error: "rationale must be a single sentence" };
  }

  if (status !== "insufficient") {
    if (citations.length === 0) {
      return { ok: false, error: `status ${status} requires at least one valid citation` };
    }
    const required: Label = status === "pass" ? "indicates_pass" : "indicates_fail";
    const wrong = citations.filter((id) => labels[id] !== required);
    if (wrong.length > 0) {
      return {
        ok: false,
        error: `status ${status} cited evidence not labeled ${required}: ${wrong.join(", ")}`,
      };
    }
  }

  const kept: Record<string, Label> = {};
  for (const id of evidenceIds) kept[id] = labels[id];
  return { ok: true, value: { status, citations, labels: kept, rationale: trimmed } };
}
