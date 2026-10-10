import type { ModelClient } from "./model.js";

type CompleteArgs = Parameters<ModelClient["complete"]>[0];

export class FakeModelClient implements ModelClient {
  readonly calls: CompleteArgs[] = [];
  private readonly queue: string[];

  constructor(replies: string[] = []) {
    this.queue = [...replies];
  }

  async complete(args: CompleteArgs): Promise<string> {
    this.calls.push(args);
    const reply = this.queue.shift();
    if (reply === undefined) throw new Error("FakeModelClient: reply queue is empty");
    return reply;
  }
}
