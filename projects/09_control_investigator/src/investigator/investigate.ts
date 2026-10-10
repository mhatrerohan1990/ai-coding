import { computeConflicts } from "./conflicts";
import type { ModelClient } from "./model";
import {
  buildDecidePrompt,
  buildPlanPrompt,
  buildRetryPrompt,
  DECIDE_SYSTEM,
  PLAN_SYSTEM,
} from "./prompts";
import { parsePlan, validateDecision } from "./schemas";
import {
  InvestigationError,
  type Decision,
  type EvidenceHit,
  type InvestigateInput,
  type Policy,
  type Tools,
} from "./types";

const PER_CALL_MS = 8_000;
const TOTAL_MS = 20_000;
const MAX_TOKENS = 300;

// Runs fn with an abort signal and rejects with InvestigationError if `ms` elapses.
async function within<T>(
  ms: number,
  what: string,
  fn: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(new InvestigationError(`${what} timed out`));
    }, ms);
  });
  try {
    return await Promise.race([fn(controller.signal), timeout]);
  } catch (err) {
    if (err instanceof InvestigationError) throw err;
    throw new InvestigationError(`${what} failed`, { cause: err });
  } finally {
    clearTimeout(timer);
  }
}

export async function investigate(
  input: InvestigateInput,
  tools: Tools,
  model: ModelClient,
): Promise<Decision> {
  const deadline = Date.now() + TOTAL_MS;
  const remaining = (what: string): number => {
    const left = deadline - Date.now();
    if (left <= 0) throw new InvestigationError(`${what}: investigation deadline exceeded`);
    return left;
  };
  const callModel = (what: string, system: string, prompt: string): Promise<string> =>
    within(Math.min(PER_CALL_MS, remaining(what)), what, (signal) =>
      model.complete({ system, prompt, maxTokens: MAX_TOKENS, signal }),
    );

  // 1. Plan. An invalid plan means no tools are called.
  const planRaw = await callModel("plan call", PLAN_SYSTEM, buildPlanPrompt(input));
  const planned = parsePlan(planRaw);

  // 2. Execute tools; controlId always comes from input.
  const [evidence, policy] = await within(
    remaining("tool calls"),
    "tool calls",
    (): Promise<[EvidenceHit[], Policy | null]> =>
      Promise.all([
        planned.includes("get_evidence") ? tools.get_evidence(input.controlId) : [],
        planned.includes("get_policy") ? tools.get_policy(input.controlId) : null,
      ]),
  );

  const policyUsed = policy !== null;

  // 3. Short-circuit on empty evidence.
  if (evidence.length === 0) {
    return {
      status: "insufficient",
      citations: [],
      policyUsed,
      conflicts: [],
      rationale: "No evidence was available to evaluate the control.",
    };
  }

  // 4. Decide: one call, one retry on validation error.
  const evidenceIds = evidence.map((hit) => hit.id);
  const prompt = buildDecidePrompt(input, evidence, policy);
  let lastError = "";
  for (let attempt = 0; attempt < 2; attempt++) {
    const reply = await callModel(
      "decide call",
      DECIDE_SYSTEM,
      attempt === 0 ? prompt : buildRetryPrompt(prompt, lastError),
    );
    const result = validateDecision(reply, evidenceIds);
    if (result.ok) {
      const { labels, rationale } = result.value;
      let { status, citations } = result.value;
      const labelValues = Object.values(labels);
      if (
        policy === null &&
        labelValues.includes("indicates_pass") &&
        labelValues.includes("indicates_fail")
      ) {
        status = "insufficient";
        citations = [];
      }
      return {
        status,
        citations,
        policyUsed,
        conflicts: computeConflicts(status, labels),
        rationale,
      };
    }
    lastError = result.error;
  }
  throw new InvestigationError(`model output failed validation after retry: ${lastError}`);
}
