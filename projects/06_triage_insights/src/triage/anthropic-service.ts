import Anthropic from '@anthropic-ai/sdk';
import { zodOutputFormat } from '@anthropic-ai/sdk/helpers/zod';
import { SYSTEM_PROMPT, formatTicket } from './prompt.js';
import { triageInsightSchema, type TriageInsight, type TriageRequest } from './schema.js';
import { TriageUnavailableError, type TriageService } from './service.js';

export class AnthropicTriageService implements TriageService {
  constructor(
    private readonly client: Anthropic = new Anthropic(),
    private readonly model: string = process.env.TRIAGE_MODEL ?? 'claude-opus-5-5',
  ) {}

  async triage(ticket: TriageRequest): Promise<TriageInsight> {
    const response = await this.client.messages.parse({
      model: this.model,
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
      messages: [{ role: 'user', content: formatTicket(ticket) }],
      output_config: {
        effort: 'low',
        format: zodOutputFormat(triageInsightSchema),
      },
    });

    if (response.stop_reason === 'refusal') {
      throw new TriageUnavailableError('Model declined to classify this ticket');
    }
    if (response.stop_reason === 'max_tokens' || !response.parsed_output) {
      throw new TriageUnavailableError('Model did not return a usable classification');
    }
    return response.parsed_output;
  }
}
