import type { FastifyError, FastifyReply, FastifyRequest } from "fastify";

export function errorHandler(err: FastifyError, req: FastifyRequest, reply: FastifyReply) {
  // Bad input from the caller (e.g. too many excerpts).
  if (err instanceof RangeError) {
    return reply.status(400).send({ statusCode: 400, error: "Bad Request", message: err.message });
  }

  // Fastify's own client errors (malformed request, etc.) keep their 4xx status.
  if (err.statusCode && err.statusCode >= 400 && err.statusCode < 500) {
    return reply.status(err.statusCode).send({
      statusCode: err.statusCode,
      error: err.name,
      message: err.message,
    });
  }

  // Everything else (timeouts, LLM failures, invalid model output): log details, hide them from the client.
  req.log.error(err);
  return reply
    .status(500)
    .send({ statusCode: 500, error: "Internal Server Error", message: "Failed to generate an answer." });
}
