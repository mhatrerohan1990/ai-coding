import type { ModelClient, ModelRequest } from "./model";

export type ScriptedResponse = string | Error | ((request: ModelRequest) => string);

// Returns queued responses in order and records every request it receives.
export class FakeModelClient implements ModelClient {
  readonly calls: ModelRequest[] = [];
  private readonly script: ScriptedResponse[];

  constructor(script: ScriptedResponse[]) {
    this.script = [...script];
  }

  async complete(request: ModelRequest): Promise<string> {
    this.calls.push(request);
    const next = this.script.shift();
    if (next === undefined) {
      throw new Error("FakeModelClient: script exhausted");
    }
    if (next instanceof Error) throw next;
    return typeof next === "function" ? next(request) : next;
  }
}
