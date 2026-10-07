import { buildApp } from './app.js';
import { createTriageService } from './triage/factory.js';

const port = Number(process.env.PORT ?? 3000);
const app = buildApp({ logger: true, triageService: createTriageService() });

try {
  await app.listen({ port, host: '0.0.0.0' });
} catch (err) {
  app.log.error(err);
  process.exit(1);
}
