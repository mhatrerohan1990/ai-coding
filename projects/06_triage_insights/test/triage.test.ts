import { afterAll, describe, expect, it, vi } from 'vitest';
import { buildApp } from '../src/app.js';
import { AnthropicTriageService } from '../src/triage/anthropic-service.js';
import { OllamaTriageService } from '../src/triage/ollama-service.js';
import { EXAMPLES, RUBRIC, SYSTEM_PROMPT, formatTicket } from '../src/triage/prompt.js';
import { CATEGORIES, SEVERITIES, triageInsightSchema, triageRequestSchema, type TriageInsight } from '../src/triage/schema.js';
import { TriageUnavailableError, type TriageService } from '../src/triage/service.js';

const ticket = { id: 'T-100', subject: 'VPN down', body: 'Nobody in the Berlin office can connect since 9am.', customerPlan: 'pro' as const };
const insight: TriageInsight = {
  category: 'bug',
  severity: 'high',
  rationale: 'Whole office is blocked with no workaround.',
};

function appWith(service: TriageService) {
  return buildApp({ triageService: service });
}

describe('POST /triage/v1/insights', () => {
  it('returns category, severity and rationale from the service', async () => {
    const triage = vi.fn().mockResolvedValue(insight);
    const app = appWith({ triage });
    const res = await app.inject({ method: 'POST', url: '/triage/v1/insights', payload: ticket });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual(insight);
    expect(triage).toHaveBeenCalledWith(ticket);
    await app.close();
  });

  it.each([
    ['missing body', { id: 'T-1', subject: 'x', customerPlan: 'pro' }],
    ['missing id', { subject: 'x', body: 'y', customerPlan: 'pro' }],
    ['unknown plan', { id: 'T-1', subject: 'x', body: 'y', customerPlan: 'gold' }],
    ['empty subject', { id: 'T-1', subject: '  ', body: 'y', customerPlan: 'pro' }],
    ['body too long', { id: 'T-1', subject: 'x', body: 'a'.repeat(10_001), customerPlan: 'pro' }],
  ])('rejects invalid input: %s', async (_name, payload) => {
    const triage = vi.fn();
    const app = appWith({ triage });
    const res = await app.inject({ method: 'POST', url: '/triage/v1/insights', payload });
    expect(res.statusCode).toBe(400);
    expect(triage).not.toHaveBeenCalled();
    await app.close();
  });

  it('returns 502 when the model cannot produce a classification', async () => {
    const app = appWith({ triage: async () => { throw new TriageUnavailableError('declined'); } });
    const res = await app.inject({ method: 'POST', url: '/triage/v1/insights', payload: ticket });
    expect(res.statusCode).toBe(502);
    expect(res.json().error).toBe('triage_unavailable');
    await app.close();
  });
});

describe('AnthropicTriageService', () => {
  const fakeClient = (message: object) =>
    ({ messages: { parse: vi.fn().mockResolvedValue(message) } }) as never;

  it('returns parsed output', async () => {
    const svc = new AnthropicTriageService(fakeClient({ stop_reason: 'end_turn', parsed_output: insight }), 'm');
    await expect(svc.triage(ticket)).resolves.toEqual(insight);
  });

  it.each([
    ['refusal', { stop_reason: 'refusal', parsed_output: null }],
    ['truncation', { stop_reason: 'max_tokens', parsed_output: null }],
    ['unparseable output', { stop_reason: 'end_turn', parsed_output: null }],
  ])('throws TriageUnavailableError on %s', async (_n, message) => {
    const svc = new AnthropicTriageService(fakeClient(message), 'm');
    await expect(svc.triage(ticket)).rejects.toBeInstanceOf(TriageUnavailableError);
  });

  it('wraps the ticket in tags so it is treated as data', () => {
    const out = formatTicket(ticket);
    expect(out).toContain('<ticket>');
    expect(out).toContain('<subject>VPN down</subject>');
  });
});

describe('OllamaTriageService', () => {
  const reply = (body: unknown, status = 200) =>
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  const chat = (content: string) => ({ message: { role: 'assistant', content } });

  it('parses a schema-valid response and sends the schema as format', async () => {
    const fetch = reply(chat(JSON.stringify(insight)));
    const svc = new OllamaTriageService({ fetch, baseUrl: 'http://x', model: 'm' });
    await expect(svc.triage(ticket)).resolves.toEqual(insight);
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe('http://x/api/chat');
    const sent = JSON.parse(init.body);
    expect(sent.model).toBe('m');
    expect(sent.format.properties.severity.enum).toEqual(['low', 'medium', 'high']);
  });

  it.each([
    ['HTTP error', reply({}, 500)],
    ['non-JSON content', reply(chat('not json'))],
    ['schema violation', reply(chat(JSON.stringify({ ...insight, severity: 'critical' })))],
    ['network failure', vi.fn().mockRejectedValue(new TypeError('fetch failed'))],
  ])('throws TriageUnavailableError on %s', async (_n, fetch) => {
    const svc = new OllamaTriageService({ fetch });
    await expect(svc.triage(ticket)).rejects.toBeInstanceOf(TriageUnavailableError);
  });
});

describe('SYSTEM_PROMPT', () => {
  it('embeds the classification rubric covering every category and severity', () => {
    expect(SYSTEM_PROMPT).toContain(RUBRIC);
    for (const value of [...CATEGORIES, ...SEVERITIES]) expect(RUBRIC).toContain(`- ${value}:`);
  });

  it('includes every few-shot example with schema-valid output', () => {
    expect(EXAMPLES.length).toBeGreaterThanOrEqual(2);
    for (const { ticket, output } of EXAMPLES) {
      expect(triageRequestSchema.safeParse(ticket).success).toBe(true);
      expect(triageInsightSchema.safeParse(output).success).toBe(true);
      expect(SYSTEM_PROMPT).toContain(JSON.stringify(output));
    }
  });
});
