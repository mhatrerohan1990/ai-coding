import { AnthropicTriageService } from './anthropic-service.js';
import { OllamaTriageService } from './ollama-service.js';
import type { TriageService } from './service.js';

/** TRIAGE_PROVIDER=ollama (default) | anthropic */
export function createTriageService(provider = process.env.TRIAGE_PROVIDER ?? 'ollama'): TriageService {
  switch (provider) {
    case 'ollama':
      return new OllamaTriageService();
    case 'anthropic':
      return new AnthropicTriageService();
    default:
      throw new Error(`Unknown TRIAGE_PROVIDER "${provider}" (expected "ollama" or "anthropic")`);
  }
}
