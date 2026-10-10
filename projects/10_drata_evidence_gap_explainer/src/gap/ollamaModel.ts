import type { ModelClient } from "./model.js";

export class OllamaModelClient implements ModelClient {
  constructor(
    private readonly model: string,
    private readonly baseUrl = "http://localhost:11434",
  ) {}

  async complete(args: Parameters<ModelClient["complete"]>[0]): Promise<string> {
    const response = await fetch(`${this.baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model: this.model,
        stream: false,
        messages: [
          { role: "system", content: args.system },
          { role: "user", content: args.prompt },
        ],
        options: { num_predict: args.maxTokens },
      }),
      signal: args.signal,
    });

    if (!response.ok) {
      throw new Error(`Ollama request failed: ${response.status} ${response.statusText}`);
    }

    const data = (await response.json()) as { message?: { content?: unknown } };
    const content = data.message?.content;
    if (typeof content !== "string") throw new Error("Ollama response missing message.content");
    return content;
  }
}
