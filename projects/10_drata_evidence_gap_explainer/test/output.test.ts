import { describe, expect, it } from "vitest";
import { parseModelOutput } from "../src/gap/output.js";

const valid = {
  customerMessage: "MFA is not enforced for all users.",
  nextStep: "Export the Okta MFA policy report.",
};

describe("parseModelOutput", () => {
  it("accepts a valid reply", () => {
    expect(parseModelOutput(JSON.stringify(valid))).toEqual({ ok: true, value: valid });
  });

  it("accepts JSON wrapped in a ```json fence", () => {
    const raw = "```json\n" + JSON.stringify(valid) + "\n```";
    expect(parseModelOutput(raw)).toEqual({ ok: true, value: valid });
  });

  it("rejects malformed JSON", () => {
    expect(parseModelOutput("{ not json")).toEqual({ ok: false, error: "invalid JSON" });
  });

  it("rejects a missing field", () => {
    const result = parseModelOutput(JSON.stringify({ customerMessage: "Something is wrong." }));
    expect(result.ok).toBe(false);
  });

  it("rejects an empty or whitespace-only string", () => {
    expect(parseModelOutput(JSON.stringify({ ...valid, nextStep: "   " })).ok).toBe(false);
    expect(parseModelOutput(JSON.stringify({ ...valid, customerMessage: "" })).ok).toBe(false);
  });

  it("rejects a customerMessage with three sentences", () => {
    const customerMessage = "First thing. Second thing. Third thing.";
    expect(parseModelOutput(JSON.stringify({ ...valid, customerMessage })).ok).toBe(false);
  });

  it("accepts a customerMessage with two sentences", () => {
    const customerMessage = "First thing. Second thing.";
    expect(parseModelOutput(JSON.stringify({ ...valid, customerMessage })).ok).toBe(true);
  });

  it("rejects a customerMessage over 300 characters", () => {
    const customerMessage = "a".repeat(301);
    expect(parseModelOutput(JSON.stringify({ ...valid, customerMessage })).ok).toBe(false);
  });

  it("rejects a nextStep over 200 characters", () => {
    const nextStep = "a".repeat(201);
    expect(parseModelOutput(JSON.stringify({ ...valid, nextStep })).ok).toBe(false);
  });

  it("rejects a multi-line nextStep", () => {
    const nextStep = "Step one\nStep two";
    expect(parseModelOutput(JSON.stringify({ ...valid, nextStep })).ok).toBe(false);
  });

  it("ignores extra keys and returns only the two fields", () => {
    const raw = JSON.stringify({ ...valid, needsHuman: false, failureReason: "pass" });
    const result = parseModelOutput(raw);
    expect(result).toEqual({ ok: true, value: valid });
    if (result.ok) expect(Object.keys(result.value).sort()).toEqual(["customerMessage", "nextStep"]);
  });
});
