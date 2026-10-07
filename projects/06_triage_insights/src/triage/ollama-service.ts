import { z } from 'zod';
import { SYSTEM_PROMPT, formatTicket } from './prompt.js';
import { triageInsightSchema, type TriageInsight, type TriageRequest } from './schema.js';
import { TriageUnavailableError, type TriageService } from './service.js';

const chatResponseSchema = z.object({ message: z.object({ content: z.string() }) });

export interface OllamaOptions {
  baseUrl?: string;
  model?: string;
  timeoutMs?: number;
  fetch?: typeof fetch;
}

export class OllamaTriageService implements TriageService {
  private readonly baseUrl: string;
  private readonly model: string;
  private readonly timeoutMs: number;
  private readonly fetchFn: typeof fetch;

  constructor(opts: OllamaOptions = {}) {
    this.baseUrl = opts.baseUrl ?? process.env.OLLAMA_URL ?? 'http://127.0.0.1:11434';
    this.model = opts.model ?? process.env.TRIAGE_MODEL ?? 'llama3.1:8b';
    this.timeoutMs = opts.timeoutMs ?? 60_000;
    this.fetchFn = opts.fetch ?? fetch;
  }

  async triage(ticket: TriageRequest): Promise<TriageInsight> {
    let res: Response;
    try {
      res = await this.fetchFn(`${this.baseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        signal: AbortSignal.timeout(this.timeoutMs),
        body: JSON.stringify({
          model: this.model,
          stream: false,
          // Constrains decoding to our schema, so small local models still emit valid JSON.
          format: z.toJSONSchema(triageInsightSchema),
          options: { temperature: 0 },
          messages: [
            { role: 'system', content: SYSTEM_PROMPT },
            { role: 'user', content: formatTicket(ticket) },
          ],
        }),
      });
    } catch (err) {
      throw new TriageUnavailableError('Could not reach the local LLM', { cause: err });
    }

    if (!res.ok) {
      throw new TriageUnavailableError(`Local LLM returned HTTP ${res.status}`);
    }

    try {
      const { message } = chatResponseSchema.parse(await res.json());
      return triageInsightSchema.parse(JSON.parse(message.content));
    } catch (err) {
      throw new TriageUnavailableError('Local LLM returned an unusable classification', { cause: err });
    }
  }
}
