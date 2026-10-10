import type { ModelClient, ModelRequest } from "./model";

export type LlamaClientOptions = {
  baseUrl?: string;
  model?: string;
};

// Local llama served by Ollama (/api/chat).
export class LlamaClient implements ModelClient {
  private readonly baseUrl: string;
  private readonly model: string;

  constructor(options: LlamaClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? process.env.LLAMA_URL ?? "http://localhost:11434";
    this.model = options.model ?? process.env.LLAMA_MODEL ?? "llama3.1:8b";
  }

  async complete({ system, prompt, maxTokens, signal }: ModelRequest): Promise<string> {
    const res = await fetch(`${this.baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal,
      body: JSON.stringify({
        model: this.model,
        stream: false,
        format: "json",
        options: { num_predict: maxTokens, temperature: 0 },
        messages: [
          { role: "system", content: system },
          { role: "user", content: prompt },
        ],
      }),
    });
    if (!res.ok) {
      throw new Error(`llama request failed: ${res.status} ${res.statusText}`);
    }
    const body = (await res.json()) as { message?: { content?: string } };
    return body.message?.content ?? "";
  }
}
