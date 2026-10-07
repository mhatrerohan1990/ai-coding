import Anthropic from '@anthropic-ai/sdk';
import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod';
import { z } from 'zod';
import { triageInsightSchema, triageRequestSchema } from '../triage/schema.js';
import { runTriage } from '../triage/pipeline.js';
import { TriageUnavailableError, type TriageService } from '../triage/service.js';

const errorSchema = z.object({ error: z.string(), message: z.string() });

export const triageRoutes: FastifyPluginAsyncZod<{ triageService: TriageService }> = async (
  app,
  { triageService },
) => {
  app.post(
    '/triage/v1/insights',
    { schema: { body: triageRequestSchema, response: { 200: triageInsightSchema, 502: errorSchema } } },
    async (request, reply) => {
      try {
        const { insight, flags, modelSeverity } = await runTriage(triageService, request.body);
        if (flags.length) {
          request.log.warn({ ticketId: request.body.id, flags }, 'triage input was sanitized');
          reply.header('x-triage-flags', flags.join(','));
        }
        if (modelSeverity !== insight.severity) {
          request.log.info({ ticketId: request.body.id, plan: request.body.customerPlan, modelSeverity }, 'severity adjusted for plan');
          reply.header('x-triage-model-severity', modelSeverity);
        }
        return insight;
      } catch (err) {
        if (err instanceof TriageUnavailableError) {
          request.log.warn({ err }, 'triage produced no usable result');
          return reply.code(502).send({ error: 'triage_unavailable', message: err.message });
        }
        if (err instanceof Anthropic.APIError) {
          request.log.error({ err }, 'upstream LLM error');
          return reply.code(502).send({ error: 'upstream_error', message: 'LLM provider error' });
        }
        throw err;
      }
    },
  );
};
