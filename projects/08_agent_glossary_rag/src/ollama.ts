const OLLAMA = process.env.OLLAMA_URL ?? "http://localhost:11434";
export const EMBED_MODEL = process.env.EMBED_MODEL ?? "nomic-embed-text";
export const CHAT_MODEL = process.env.CHAT_MODEL ?? "llama3.1:8b";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${OLLAMA}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Ollama ${path} failed: ${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

/** Text -> vector. This is the "embedding" step. */
export async function embed(text: string): Promise<number[]> {
  const out = await post<{ embeddings: number[][] }>("/api/embed", {
    model: EMBED_MODEL,
    input: text,
  });
  return out.embeddings[0];
}

/** Prompt -> text. temperature 0 keeps answers as repeatable as possible (good for evals). */
export async function generate(system: string, user: string): Promise<string> {
  const out = await post<{ message: { content: string } }>("/api/chat", {
    model: CHAT_MODEL,
    stream: false,
    options: { temperature: 0 },
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
  });
  return out.message.content.trim();
}
