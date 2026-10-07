import type { TriageInsight, TriageRequest } from './schema.js';

export interface TriageService {
  triage(ticket: TriageRequest): Promise<TriageInsight>;
}

/** The model could not produce a usable classification (refusal, truncation, bad output). */
export class TriageUnavailableError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = 'TriageUnavailableError';
  }
}
