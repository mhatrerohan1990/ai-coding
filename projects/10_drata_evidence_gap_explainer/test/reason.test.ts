import { describe, expect, it } from "vitest";
import { computeFailureReason } from "../src/gap/reason.js";
import type { Evidence, GapInput } from "../src/gap/types.js";

const now = new Date("2026-01-02T12:00:00.000Z");
const HOUR = 60 * 60 * 1000;

const control = { id: "c1", name: "MFA enforced", requirement: "MFA on all users" };

function evidenceAt(collectedAt: string): Evidence {
  return { source: "okta", collectedAt, payload: {} };
}

function ageHours(hours: number): string {
  return new Date(now.getTime() - hours * HOUR).toISOString();
}

function input(overrides: Partial<GapInput>): GapInput {
  return { control, evidence: evidenceAt(ageHours(1)), integrationStatus: "ok", ...overrides };
}

describe("computeFailureReason", () => {
  it("returns integration_error when status is error and evidence is null", () => {
    expect(computeFailureReason(input({ integrationStatus: "error", evidence: null }), now)).toBe(
      "integration_error",
    );
  });

  it("returns integration_error when status is error even with non-null fresh evidence", () => {
    expect(computeFailureReason(input({ integrationStatus: "error" }), now)).toBe("integration_error");
  });

  it("returns missing_evidence when evidence is null and status is ok", () => {
    expect(computeFailureReason(input({ evidence: null }), now)).toBe("missing_evidence");
  });

  it("returns missing_evidence when evidence is null and status is stale", () => {
    expect(computeFailureReason(input({ evidence: null, integrationStatus: "stale" }), now)).toBe(
      "missing_evidence",
    );
  });

  it("returns stale_evidence when collectedAt is older than 24 hours", () => {
    expect(computeFailureReason(input({ evidence: evidenceAt(ageHours(25)) }), now)).toBe("stale_evidence");
  });

  it("returns stale_evidence just past the 24 hour boundary", () => {
    const justOver = new Date(now.getTime() - 24 * HOUR - 1).toISOString();
    expect(computeFailureReason(input({ evidence: evidenceAt(justOver) }), now)).toBe("stale_evidence");
  });

  it("does not treat exactly 24 hours old as stale", () => {
    expect(computeFailureReason(input({ evidence: evidenceAt(ageHours(24)) }), now)).toBe(
      "requirement_not_met",
    );
  });

  it("ignores integrationStatus stale when the timestamp is fresh", () => {
    expect(computeFailureReason(input({ integrationStatus: "stale" }), now)).toBe("requirement_not_met");
  });

  it("returns stale_evidence for an unparseable collectedAt", () => {
    expect(computeFailureReason(input({ evidence: evidenceAt("not-a-date") }), now)).toBe("stale_evidence");
  });

  it("returns requirement_not_met for fresh evidence and ok status", () => {
    expect(computeFailureReason(input({}), now)).toBe("requirement_not_met");
  });
});
