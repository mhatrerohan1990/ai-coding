import { readFile } from "node:fs/promises";
import Fastify from "fastify";
import { glossary } from "./glossary.js";
import { VectorStore } from "./vectorStore.js";
import { ask } from "./rag.js";

const app = Fastify({ logger: { level: "info" } });
const store = new VectorStore();

const page = await readFile(new URL("../public/index.html", import.meta.url), "utf8");
app.get("/", async (_req, reply) => reply.type("text/html").send(page));

app.get("/health", async () => ({ ok: true, indexed: store.size }));

app.post<{ Body: { question: string } }>(
  "/ask",
  {
    schema: {
      body: {
        type: "object",
        required: ["question"],
        properties: { question: { type: "string", minLength: 3 } },
      },
    },
  },
  async (req) => ask(store, req.body.question),
);

// Index the glossary once at startup (12 docs -> a couple of seconds).
app.log.info("Embedding glossary...");
await store.add(glossary);
app.log.info(`Indexed ${store.size} terms`);

await app.listen({ port: Number(process.env.PORT ?? 3000), host: "127.0.0.1" });
