export type ModelRequest = {
  system: string;
  prompt: string;
  maxTokens: number;
  signal: AbortSignal;
};

export interface ModelClient {
  complete(request: ModelRequest): Promise<string>;
}
