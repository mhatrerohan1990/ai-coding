import { describe, expect, it } from "vitest";
import { computeNeedsHuman } from "../src/gap/needsHuman.js";
import { redactPayload } from "../src/gap/redact.js";

describe("computeNeedsHuman", () => {
  it("is false when the payload has a boolean value", () => {
    expect(computeNeedsHuman("requirement_not_met", { mfaEnabled: false })).toBe(false);
  });

  it("is true when the payload has no boolean or status-like field", () => {
    expect(computeNeedsHuman("requirement_not_met", { note: "see console" })).toBe(true);
  });

  it("is true for an empty payload", () => {
    expect(computeNeedsHuman("requirement_not_met", {})).toBe(true);
  });

  it("is false when a nested object has a boolean", () => {
    expect(computeNeedsHuman("requirement_not_met", { policy: { rules: { enforced: true } } })).toBe(false);
  });

  it("is false when a status-like key has a string value", () => {
    expect(computeNeedsHuman("requirement_not_met", { status: "inactive" })).toBe(false);
  });

  it("is false when a status-like key has a number value", () => {
    expect(computeNeedsHuman("requirement_not_met", { result: 0 })).toBe(false);
  });

  it("is true when a status-like key holds a non-primitive value", () => {
    expect(computeNeedsHuman("requirement_not_met", { status: null, state: { detail: "x" } })).toBe(true);
  });

  it.each(["missing_evidence", "stale_evidence", "integration_error"] as const)(
    "is false for %s even with an empty payload",
    (reason) => {
      expect(computeNeedsHuman(reason, {})).toBe(false);
    },
  );
});

it("treats a payload whose only signal sits under a secret-like key as vague", () => {
  const redacted = redactPayload({ apiKeyValid: true });
  expect(computeNeedsHuman("requirement_not_met", redacted)).toBe(true);
});

it("still sees a visible signal next to a dropped secret key", () => {
  const redacted = redactPayload({ apiKey: "abc", mfaEnabled: false });
  expect(computeNeedsHuman("requirement_not_met", redacted)).toBe(false);
});
