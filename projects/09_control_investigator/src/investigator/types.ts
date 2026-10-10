export type Tool =
  | { name: "get_evidence"; args: { controlId: string } }
  | { name: "get_policy"; args: { controlId: string } };

export type EvidenceHit = { id: string; text: string; collectedAt: string };
export type Policy = { controlId: string; requirement: string };

export type Tools = {
  get_evidence(controlId: string): Promise<EvidenceHit[]>; // 0-3 hits
  get_policy(controlId: string): Promise<Policy | null>;
};

export type InvestigateInput = {
  controlId: string;
  question: string; // untrusted
};

export type Decision = {
  status: "pass" | "fail" | "insufficient";
  citations: string[]; // evidence ids actually used
  policyUsed: boolean;
  conflicts: string[]; // evidence ids that disagree with the decision
  rationale: string; // one sentence
};

export const TOOL_NAMES = ["get_evidence", "get_policy"] as const;
export type ToolName = (typeof TOOL_NAMES)[number];

export const LABELS = ["indicates_pass", "indicates_fail", "irrelevant"] as const;
export type Label = (typeof LABELS)[number];

export class InvestigationError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "InvestigationError";
  }
}
