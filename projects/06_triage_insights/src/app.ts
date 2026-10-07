import Fastify, { type FastifyInstance } from 'fastify';
import {
  serializerCompiler,
  validatorCompiler,
  type ZodTypeProvider,
} from 'fastify-type-provider-zod';
import { healthRoutes } from './routes/health.js';
import { triageRoutes } from './routes/triage.js';
import type { TriageService } from './triage/service.js';

export interface AppOptions {
  logger?: boolean;
  triageService: TriageService;
}

export function buildApp(opts: AppOptions): FastifyInstance {
  const app = Fastify({ logger: opts.logger ?? false }).withTypeProvider<ZodTypeProvider>();

  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);

  app.register(healthRoutes);
  app.register(triageRoutes, { triageService: opts.triageService });

  return app;
}
