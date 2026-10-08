import Fastify from "fastify";
import { answerQuestion } from "./answerQuestion.js";
import { errorHandler } from "./errorHandler.js";
import type { AskInput } from "./types.js";

const app = Fastify({ logger: true });
app.setErrorHandler(errorHandler);

app.get("/health", async () => ({ status: "ok" }));

app.get("/citations", async () => {
  // Stand-in for the embeddings team's output (question + up to 5 excerpts).
  const input: AskInput = {
    question: "what is password requirements and mfa rules?",
    excerpts: [
      { id: "pol-1", text: "Passwords must be changed every 90 days and must be at least 12 characters." },
      { id: "pol-2", text: "Laptops must use full-disk encryption." },
      { id: "pol-3", text: "Multi-factor authentication is required for all access to production systems." },
      { id: "pol-4", text: "Security incidents must be reported to the security team within 24 hours of discovery." },
      { id: "pol-5", text: "Employees must complete security awareness training annually." },
    ],
  };
  return answerQuestion(input);
});

const port = Number(process.env.PORT ?? 3000);

try {
  await app.listen({ port, host: "0.0.0.0" });
} catch (err) {
  app.log.error(err);
  process.exit(1);
}
