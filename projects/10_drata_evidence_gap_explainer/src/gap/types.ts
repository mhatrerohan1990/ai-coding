export type Evidence = {
  source: "aws" | "okta" | "github" | "manual";
  collectedAt: string; // ISO
  payload: Record<string, unknown>; // raw vendor shape, untrusted
};

export type GapInput = {
  control: { id: string; name: string; requirement: string };
  evidence: Evidence | null; // null means the integration returned nothing
  integrationStatus: "ok" | "stale" | "error";
};

export type GapExplanation = {
  failureReason: "missing_evidence" | "stale_evidence" | "requirement_not_met" | "integration_error";
  customerMessage: string; // 1-2 sentences
  nextStep: string; // one concrete action
  needsHuman: boolean;
};

export class GapExplainError extends Error {
  readonly code: string;

  constructor(code: string, message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "GapExplainError";
    this.code = code;
  }
}
