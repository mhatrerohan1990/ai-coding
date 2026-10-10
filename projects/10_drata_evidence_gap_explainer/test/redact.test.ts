import { describe, expect, it } from "vitest";
import { collectSecretValues, redactPayload } from "../src/gap/redact.js";

describe("redactPayload", () => {
  it("drops a top-level sensitive key", () => {
    expect(redactPayload({ user: "ann", password: "hunter2" })).toEqual({ user: "ann" });
  });

  it("drops a nested sensitive key", () => {
    expect(redactPayload({ config: { region: "us-east-1", secret: "s3" } })).toEqual({
      config: { region: "us-east-1" },
    });
  });

  it("drops a sensitive key inside an array of objects", () => {
    const result = redactPayload({
      users: [
        { name: "ann", token: "t1" },
        { name: "bob", token: "t2" },
      ],
    });
    expect(result).toEqual({ users: [{ name: "ann" }, { name: "bob" }] });
  });

  it("truncates strings over 200 characters", () => {
    const result = redactPayload({ note: "a".repeat(500), short: "ok" });
    expect(result.note).toBe("a".repeat(200));
    expect(result.short).toBe("ok");
  });

  it("matches key names case-insensitively (apiKey, API_TOKEN)", () => {
    expect(redactPayload({ apiKey: "k", API_TOKEN: "t", name: "ann" })).toEqual({ name: "ann" });
  });

  it("skips __proto__, constructor and prototype keys without polluting the prototype", () => {
    const payload = JSON.parse(
      '{"__proto__": {"x": 1}, "constructor": {"y": 2}, "prototype": {"z": 3}, "a": 1}',
    ) as Record<string, unknown>;
    const result = redactPayload(payload);

    expect(Object.keys(result)).toEqual(["a"]);
    expect(Object.getPrototypeOf(result)).toBe(Object.prototype);
    expect((result as { x?: unknown }).x).toBeUndefined();
    expect(({} as { x?: unknown }).x).toBeUndefined();
  });

  it("does not mutate the original object", () => {
    const original = {
      name: "ann",
      password: "hunter2",
      nested: { token: "t", note: "a".repeat(300) },
      list: [{ key: "k", id: 1 }],
    };
    const snapshot = structuredClone(original);
    redactPayload(original);
    expect(original).toEqual(snapshot);
  });
});

describe("collectSecretValues", () => {
  it("collects string values for sensitive keys at any depth, including arrays", () => {
    const payload = {
      password: "p1",
      nested: { apiKey: "k1", name: "ann" },
      list: [{ API_TOKEN: "t1" }, { id: "x" }],
    };
    expect(collectSecretValues(payload).sort()).toEqual(["k1", "p1", "t1"]);
  });

  it("returns the full untruncated value", () => {
    const long = "s".repeat(300);
    expect(collectSecretValues({ secret: long })).toEqual([long]);
  });

  it("ignores non-string values and returns [] when none match", () => {
    expect(collectSecretValues({ token: 123, name: "ann" })).toEqual([]);
  });
});
