export interface ModelClient {
  complete(args: {
    system: string;
    prompt: string;
    maxTokens: number;
    signal?: AbortSignal;
  }): Promise<string>;
}
