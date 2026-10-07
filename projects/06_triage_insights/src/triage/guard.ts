import type { TriageInsight, TriageRequest } from './schema.js';
import { TriageUnavailableError } from './service.js';

/**
 * Deterministic guards around the LLM. They are defense in depth, not a proof of safety:
 * a paraphrased attack can slip past the patterns, so log the flags and keep the prompt guard too.
 */

const HIDDEN_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F​-‏‪-‮⁠﻿]/g;
const FAKE_TAGS = /<\/?\s*(ticket|subject|body|system|assistant|user)\b[^>]*>/gi;

const INJECTION_PATTERNS: RegExp[] = [
  /\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|your|the|all)\b.{0,20}\b(instructions?|rules?|prompt|guidelines?)\b/i,
  /\b(system|admin(istrator)?|developer|operator)\s*(notice|override|message|instructions?|prompt|note)\b/i,
  /\bnew\s+instructions?\b/i,
  /^\s*(assistant|system|user|ai)\s*:/i,
  /\b(classify|categori[sz]e|mark|rate|label|treat)\b.{0,40}\b(this|the|it)\b.{0,40}\b(as|with)\b.{0,30}\b(low|medium|high|critical|bug|billing|access|how_to|other|severity|priority)\b/i,
  /\b(respond|reply|output|answer)\b.{0,30}\b(with|exactly)\b.{0,60}(\{|\bcategory\b|\bseverity\b)/i,
];

export interface SanitizedTicket {
  ticket: TriageRequest;
  /** Machine-readable reasons the input was altered; empty when it was clean. */
  flags: string[];
}

function sanitizeText(input: string, flags: Set<string>): string {
  let text = input.normalize('NFKC');

  const noHidden = text.replace(HIDDEN_CHARS, '');
  if (noHidden !== text) flags.add('hidden_characters');
  text = noHidden;

  const noTags = text.replace(FAKE_TAGS, ' ');
  if (noTags !== text) flags.add('delimiter_breakout');
  text = noTags;

  // Drop whole sentences or lines that read as instructions to the model, keep the rest.
  const kept = text.split(/(?<=[.!?])\s+|\n+/).filter((segment) => {
    const injected = INJECTION_PATTERNS.some((p) => p.test(segment));
    if (injected) flags.add('prompt_injection');
    return !injected;
  });
  return kept.join(' ').replace(/\s+/g, ' ').trim();
}

export function sanitizeTicket(ticket: TriageRequest): SanitizedTicket {
  const flags = new Set<string>();
  const sanitized: TriageRequest = {
    ...ticket,
    subject: sanitizeText(ticket.subject, flags) || '(untitled)',
    body: sanitizeText(ticket.body, flags) || '(no details left after removing instructions)',
  };
  return { ticket: sanitized, flags: [...flags] };
}

const MAX_RATIONALE = 300;

/** Enforce the response contract: one trimmed sentence of bounded length. */
export function finalizeInsight(insight: TriageInsight): TriageInsight {
  const text = insight.rationale.replace(/\s+/g, ' ').trim();
  const firstSentence = text.match(/^.+?[.!?](?=\s|$)/)?.[0] ?? text;
  let rationale = firstSentence.slice(0, MAX_RATIONALE).trim();
  if (!rationale) throw new TriageUnavailableError('Model returned an empty rationale');
  if (!/[.!?]$/.test(rationale)) rationale += '.';
  return { ...insight, rationale };
}
