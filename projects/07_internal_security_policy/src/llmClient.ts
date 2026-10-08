export type Message = { role: "system" | "user" | "assistant"; content: string };

export interface LlmRequest {
  messages: Message[];
  /** JSON schema the reply must match (use if the provider supports structured output). */
  schema: Record<string, unknown>;
  timeoutMs: number;
  maxTokens: number;
}

/** Sends the request to an LLM and returns the raw text of the reply (a JSON string). */
export type LlmClient = (req: LlmRequest) => Promise<string>;
